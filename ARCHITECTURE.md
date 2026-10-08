# Architecture

This document describes how TrustEscrow is put together: the three tiers, how data flows between them, the release rule the whole system is built around, and the design decisions that shaped it. It ends with the standards every repository follows and the roadmap.

The system lives in three repositories:

- [trustedescrow-contract](https://github.com/TrustedEscrow/trustedescrow-contract): the factory and escrow contracts (Rust, Soroban).
- [trustedescrow-backend](https://github.com/TrustedEscrow/trustedescrow-backend): the API and its background workers (TypeScript, PostgreSQL).
- [trustedescrow-frontend](https://github.com/TrustedEscrow/trustedescrow-frontend): the web app, the arbitrator console and the Escrow SDK (Next.js).

Security properties and known limits are covered separately in [THREAT_MODEL.md](THREAT_MODEL.md).

## Overview

TrustEscrow is a peer-to-peer escrow for online trade between strangers. A buyer deposits into a contract made for that one trade. The seller proves delivery on-chain, the buyer proves receipt, and only then is the seller paid. If the two disagree, or one goes silent, an arbitrator chooses between release and refund.

The system has three tiers, each at a different level of trust. The ordering matters: every tier is authoritative for everything above it.

```
        +------------------------------------------+
        |  Frontend (Next.js web app, arbitrator   |   reads API, writes to chain
        |  console, Escrow SDK, Freighter wallet)  |
        +--------------------+---------------------+
                             |
          read path          |          write path
   (HTTP to API: drafts,     |     (RPC, SDK-built calls,
    chat, vault, lists)      |       wallet-signed)
                             |
     +-----------------------+-----------------------+
     |                                               |
     v                                               v
+--------------------------------+       +-----------------------+
|  Backend (API + workers)       |       |   Soroban RPC node    |
|  drafts, chat, evidence,       |       |                       |
|  ciphertext vault, read cache  |       |                       |
+---------------+----------------+       +-----------+-----------+
                |                                    |
   polls events, reads state,                  submits txs
   calls permissionless timeouts                     |
                |                                    |
                v                                    v
        +----------------------------------------------------+
        |   Factory + escrow contracts (Soroban, on-chain)   |
        |  one escrow per trade, holds funds, enforces rules |
        +----------------------------------------------------+
```

- **The contracts are the source of truth.** Every trade gets its own escrow contract, which holds the funds and enforces every rule. Nothing above it can move funds in a way the contract does not allow.
- **The backend holds everything that happens off-chain.** That means negotiation, chat, dispute evidence, notification schedules and a read cache. It also stores the buyer's delivery code, encrypted under a key the backend does not have. It never holds funds, and its API never holds a signing key. If the backend is wrong or offline, no escrow is affected: every escrow can still be completed, disputed or timed out from a CLI.
- **The frontend is a convenience.** Reads go through the backend for speed. Writes bypass the backend entirely and go straight to the chain. The SDK builds each call and the user's wallet signs it.

This separation keeps the trust-critical surface small: the contracts, plus the one secret outside them, the delivery code. The code exists in plaintext only on the buyer's device.

## The escrow model

Every component reasons about the same rule, so it is worth stating precisely.

An escrow holds an amount `A` of a token for a buyer and a seller. At creation it also records an arbitrator and a fee rate `f` in basis points (at most 1,000), both copied from the factory. It has one absolute funding deadline and three windows (delivery, receipt and arbitration), each between one hour and 365 days. Times are Unix seconds. Amounts are integers in the token's smallest unit.

There are two pieces of evidence, one from each side:

- **Proof** is the seller's evidence of delivery, submitted on-chain exactly once. It carries a kind (`Tracking`, `Content` or `Attestation`), a URI, and the sha256 of the content it refers to.
- **Receipt** is the buyer's evidence. It is either a delivery code whose sha256 matches the hash committed at creation, or the buyer's own signature on `confirm`.

The seller can be paid only in these cases:

```
release is allowed when:
    proof is on-chain  AND  receipt is given  AND  no dispute is open
    OR
    the escrow is Disputed  AND  the arbitrator signs Release  AND  t < dispute.deadline

otherwise, never
```

The money splits like this:

```
on release:   fee    = A * f / 10000      (integer division, rounding down)
              payout = A - fee            -> seller
              fee                         -> fee_recipient
on refund:    A                           -> buyer    (no fee)
```

Each deadline, once passed, opens a permissionless exit:

```
t >= funding_deadline     and still Created     ->  anyone may cancel
t >= delivery_deadline    and still Funded      ->  anyone may refund the buyer
t >= receipt_deadline     and still Delivered   ->  anyone may escalate to Disputed
t >= dispute.deadline     and still Disputed    ->  anyone may refund the buyer
```

Every comparison is `t >= deadline`. At exactly the deadline, the before-deadline action is rejected and the after-deadline action is accepted.

Four consequences worth noting:

- **Time never pays the seller.** A deadline can only refund the buyer or send the escrow to arbitration. If the buyer goes silent after proof, the escrow escalates to the arbitrator. The seller cannot be paid just by waiting.
- **Neither side is paid on their own word.** Tracking shows that a parcel moved, not that the buyer has it. A code shows the buyer is satisfied, but without the seller's delivery record the arbitrator would have nothing from the seller if the buyer later claimed coercion. Release needs both. A refund returns funds to where they started, so it needs less.
- **Rounding never strands tokens.** The fee rounds down and the seller receives the rest, so `payout + fee == A` exactly, and a finished escrow holds nothing.
- **Nobody can be stuck.** Every open state has an exit that does not need the counterparty's cooperation.

The lifecycle as a set of paths:

```
happy path:       Created --fund--> Funded --submit_proof--> Delivered --code or confirm--> Released
in person:        Funded --submit_proof_with_code--> Released
never funded:     Created --cancel--> Cancelled
never delivered:  Funded --delivery deadline passes--> Refunded
dispute:          Funded or Delivered --dispute--> Disputed --resolve--> Released or Refunded
silent buyer:     Delivered --receipt deadline passes, escalate--> Disputed
silent arbiter:   Disputed --arbitration deadline passes--> Refunded
seller concedes:  Funded, Delivered or Disputed --seller_refund--> Refunded
```

The contract is authoritative for all of this. The SDK mirrors the contract's guards (`src/sdk/actions.ts`), so the UI only offers calls the contract would accept at that moment. Delivery-code handling is implemented three times: in Rust (`crates/code`), in the frontend and in the backend. All three pass the same shared test vectors, so they agree byte for byte.

## The contracts

`trustedescrow-contract` is a Cargo workspace with two contracts and two supporting crates:

| Crate | Role |
|---|---|
| `contracts/factory` | Deploys escrows; holds operator configuration for new ones |
| `contracts/escrow` | One instance per trade; holds funds and enforces the lifecycle |
| `crates/types` | Types shared by both contracts |
| `crates/code` | Reference implementation of the delivery code, and the source of the shared test vectors |

### Factory

The factory holds the admin address, the escrow WASM hash, the arbitrator, the fee recipient, the fee rate and a token allowlist.

- `create(order, salt) -> address` requires the buyer's authorisation and an allowlisted token. It deploys a new escrow from the configured WASM hash and copies the arbitrator and fee settings into it. The address is derived from the buyer and the salt, so it is known before submission (`escrow_address`) and nobody else can claim it.
- `create_and_fund(order, salt) -> address` deploys and funds the new escrow in a single atomic transaction and signature, eliminating the risk of abandoned unfunded instances.
- `set_config` and `allow_token` require the admin. They affect only escrows created afterwards. No factory function can reach an existing escrow.
- `propose_admin`, `accept_admin` and `cancel_admin_transfer` hand the admin role over in two steps. Nothing changes until the new address accepts, so a mistyped address can never lock the factory.

### Escrow storage

Each escrow's whole record lives in its own instance storage. The record holds the buyer, seller, arbitrator, token, amount, fee rate and recipient, and the terms hash. It also holds the delivery-code hash, the state, every deadline, the proof, any dispute (including committed `statement_hash` and `ruling_hash`), any `unswept_fee`, the deployment `salt` for factory provenance, and the settlement path. Every state-changing call extends the instance's time-to-live to 120 days whenever fewer than 30 remain, so an active escrow cannot expire. `bump` does the same and is public.

### Entry points

- `fund` requires the buyer's authorisation. It pulls `A` tokens into the contract before the funding deadline and starts the delivery window.
- `cancel` works only on an unfunded escrow. Either party may call it at any time; anyone may call it after the funding deadline.
- `submit_proof(kind, uri, hash)` requires the seller's authorisation. It records the proof before the delivery deadline and starts the receipt window. It can be called once; proof can never be overwritten.
- `submit_proof_with_code(kind, uri, hash, code)` requires the seller's authorisation. It records the proof and verifies the buyer's code in one transaction, and releases. This is the in-person path. It is accepted even after the delivery deadline, because a buyer who hands over the code has accepted late delivery.
- `release_with_code(code)` can be called by anyone once proof exists. The code itself is the authorisation.
- `confirm` requires the buyer's authorisation once proof exists, and releases.
- `extend_delivery(new_deadline)` requires the buyer's authorisation. Pushes `delivery_deadline` later (never earlier), accepting delayed delivery without forfeiting escrow guarantees.
- `extend_receipt(new_deadline)` requires the seller's authorisation. Pushes `receipt_deadline` later (never earlier), granting the buyer additional inspection time.
- `dispute(caller, statement_hash)` requires the buyer's or the seller's authorisation, permanently committing the sha256 hash of their off-chain statement. From `Funded` it closes at the delivery deadline, so a seller who never shipped cannot use it to block the buyer's refund.
- `escalate` can be called by anyone after the receipt deadline. It opens a dispute with origin `ReceiptTimeout` and a zero statement hash.
- `resolve(outcome, ruling_hash)` requires the arbitrator's authorisation, and only works in `Disputed` before the arbitration deadline, committing the sha256 of the written arbitrator ruling.
- `refund_after_delivery_timeout` and `refund_after_arbitration_timeout` can be called by anyone once their deadline has passed. They always pay the buyer.
- `seller_refund` requires the seller's authorisation. It returns the full amount to the buyer from any open, funded state.
- `sweep_fee` can be called by anyone if a fee transfer previously failed (e.g., fee recipient temporarily lacking a trustline), retrying payout of `unswept_fee` strictly to the configured `fee_recipient`.
- `get` and `bump` require no authorisation.

### The delivery code

The buyer's client generates the code, and the escrow stores only `sha256(code)`. Because that hash is public, the code's length is its only defence against brute force. It is 80 bits of entropy, written as 16 Crockford base32 characters and shown as `K7M2-9XQF-4TBN-R3WD`. Clients normalise input before hashing: they strip spaces and hyphens, uppercase, and map `I`/`L` to `1` and `O` to `0`.

The code has no salt, because a salt would have to travel with it. It also has no rotation. If the buyer could change the code, they could hand it over and then invalidate it before the seller's transaction confirmed. The code counts only alongside seller proof. Once a dispute is open, a code no longer releases anything; it becomes evidence for the arbitrator to weigh.

### Proof

The contract stores proof but never evaluates it. `ProofKind` exists so the UI and the arbitrator can apply the right standard. Shipped goods need `Tracking` with a carrier reference. Digital goods use `Content`, which the buyer can check by hashing what they received. In-person trades and services use `Attestation`, the weakest tier, which gets its weight from the buyer's code arriving in the same transaction.

A proof URI is at most 256 bytes and must use `https://`, `ipfs://` or `ar://`. The URI may go dead, but the hash still proves what was submitted, and when.

### Events

The factory emits `escrow` when it deploys, with the buyer and seller as topics. It also emits `config`, `token`, `adm_prop` and `adm_xfer` for its admin actions. Each escrow emits `created`, `funded`, `proof`, `disputed`, `released`, `refunded` and `cancelled`. These events are the backbone of the indexer.

### Safety properties

- The full amount is escrowed at funding. When a release is due, the funds are guaranteed to be there.
- Principal only ever goes to the buyer or the seller, and the fee only to the fee recipient, only on release.
- State is written before tokens move, so a malicious token cannot re-enter and pay out twice.
- Terminal states (`Released`, `Refunded`, `Cancelled`) accept no further calls.
- An escrow has no admin, no upgrade path and no setter. What is agreed at creation is what runs.
- Release builds keep `overflow-checks` on, because a silent arithmetic wrap in a contract that moves money is a vulnerability.

Each property has dedicated tests. A seeded, randomised state-machine test also drives escrows through random call sequences and checks conservation, terminality and the release rule after every step.

## The backend

The backend runs four processes against one PostgreSQL database. Only the keeper holds a key, and that key can only pay fees.

| Process | What it does |
|---|---|
| API | HTTP API for the web app and the arbitrator console |
| Indexer | Mirrors escrow state into PostgreSQL and schedules notifications |
| Notifier | Delivers due notifications in-app and by email |
| Keeper | Calls the permissionless timeouts and `bump` so users don't have to |

### Indexer

The indexer polls contract events over Soroban RPC, starting from a saved cursor. For each event it learns which escrow changed. It then reads that escrow's full state with a `get` simulation and upserts it.

Reading full state rather than trusting event payloads is deliberate. The mirror is always correct regardless of which event fired, and re-processing an event is harmless, so the indexer can crash and resume from its cursor without corrupting data. If the cursor falls out of the RPC's event retention window, the indexer stops and waits for an operator to reconcile. It never skips ahead silently.

```
 RPC getEvents (from cursor)
        |
        v
 decode event -> (escrow address, kind)
        |
        v
 get() simulation -> full escrow state
        |
        v
 upsert into Postgres, re-plan notifications
        |
        v
 save cursor
```

The cache only answers "which escrows involve this address". The API labels list results `source: "cache"`. An escrow's detail view always reads contract storage.

### API

- **Sign-in.** The wallet signs a [SEP-53](https://github.com/stellar/stellar-protocol/blob/master/ecosystem/sep-0053.md) message bound to the site and the network. The API issues an opaque session and stores only its hash.
- **Drafts.** An escrow is negotiated before it exists on-chain. Each proposal is stored as a new revision and never edited. When both parties accept the same revision, its terms are frozen and `terms_hash = sha256(canonical_json(terms))` is fixed (RFC 8785). The buyer commits that hash in `create`. A draft is linked to its escrow only if every field committed on-chain matches the agreed terms.
- **Chat and evidence.** Messages, photos and statements are too large and too private for the chain. Anything containing the escrow's delivery code is refused before it is stored. Blobs go to local disk or to any S3-compatible object store, chosen by `EVIDENCE_STORAGE_DRIVER`. Local disk is for development only: it does not survive a redeploy and cannot be shared across instances, so anything long-lived needs the object store.
- **Two-factor authentication.** TOTP with backup codes. Sensitive backend actions need a recent step-up: signing in from a new device, changing the payout address, reading the code vault, and filing a dispute statement. 2FA cannot gate on-chain calls, because anyone holding their key can call the contract directly, and the product does not pretend otherwise. A step-up also covers `POST /me/sessions/revoke-all`, which ends every other session at once — the payout-address-changed notice tells a user to do exactly that if the change wasn't theirs, and one call is the difference between acting on that warning and deleting sessions one by one.
- **Rate limits.** Beyond the global per-IP limit, the routes that cost someone else something are limited individually: messages, evidence uploads, the vault, and `POST /drafts`, which inserts rows and notifies a named counterparty, so any authenticated account could otherwise spam proposals at a stranger.
- **Arbitration.** For configured arbitrators the API serves open disputes ordered by deadline. Each comes with a case file: live contract state, the agreed terms with the hash re-checked, chat, statements and evidence. It also serves two health figures: the share of releases that were two-sided, and the escalation rate.

### The encrypted code vault

This is the most security-critical part of the backend, because a code plus the seller's proof can release an escrow.

1. The buyer's client generates the code and commits its hash in `create`.
2. The client derives a key from the buyer's own credential: a passkey (WebAuthn PRF, then HKDF), or a password (PBKDF2-SHA256, at least 600,000 iterations) that never leaves the device.
3. The client encrypts the code with AES-256-GCM and uploads the ciphertext only.
4. The server stores the envelope but cannot decrypt it. It refuses envelopes with a weak key-derivation setting, or with anything that hashes to the committed code.
5. Reading the envelope needs a step-up and is audit-logged. Recovery on a new device needs the buyer's credential.

A full database compromise yields encrypted blobs and chat logs, not the ability to release escrows. Codes are never sent by SMS or email. If a buyer loses both device and credential, they can still sign `confirm` with their wallet, or the escrow goes to arbitration. A code the operator could recover would mean an operator who could steal.

### Notifications and keeper

Notifications are planned from each fresh contract snapshot and cancelled when the state moves on. The buyer is reminded 24 hours before the funding deadline, and again 24 hours before the receipt deadline. The seller is reminded 24 hours before the delivery deadline. Both parties are notified 72 hours before an arbitration deadline. Arbitrators are reminded at 72 and 24 hours.

The funding reminder matters as much as the others: an unfunded escrow is cancellable by anyone once its deadline passes, so a buyer who created one and forgot is the one person who can still act.

A send that fails is retried rather than dropped. The dispatcher records the attempt and the error, backs off exponentially, and gives up after five tries — at which point the notification is still visible in the app, because email was only ever the second channel.

The keeper watches for passed deadlines, escrows near expiry, and escrows holding a fee that failed to reach `fee_recipient` on release. It calls `cancel`, `refund_after_delivery_timeout`, `escalate`, `refund_after_arbitration_timeout`, `sweep_fee` and `bump`. Every one of those calls is open to anyone, and the contract decides where the funds go. The keeper runs as its own process so that the API never holds a key. If it stops, nobody is stranded.

## The frontend

The frontend is a Next.js app with a clean split between reading and writing, built to remain fully functional even if an off-chain backend service is unavailable.

- **Read path.** Drafts, chat, lists and notifications come from the backend API. An escrow's page reads live contract storage through the SDK over Soroban RPC and works without signing in.
- **Write path.** Funding, proof, release, confirmation, disputes and rulings bypass the backend entirely. The SDK builds the contract call, simulates it (restoring archived state if needed), asks Freighter to sign, submits it, and polls until it is confirmed. A call that would fail is explained before the user pays for it.
- **Direct On-Chain Mode (`/escrow`).** A dedicated contract lookup and action interface operating purely over Soroban RPC. Users and counterparties can paste any escrow contract address (`C...`), inspect live on-chain balances, state, participants, proof records, and dispute status, and execute actions (`Fund`, `Confirm`, `Release with Code`, `Dispute`, `Timeout Refund`) directly without requiring an account or off-chain API connectivity.

The frontend never holds a private key. It takes its trust anchors from its own build, never from the backend: the factory id, the audited escrow WASM hash, the network passphrase and the RPC URL. It refuses to create escrows through a factory configured with a different WASM hash, and refuses to fund an instance running one. A compromised backend therefore cannot redirect users to a different contract.

**The Escrow SDK** lives in `src/sdk`. It has no React or backend dependency and works against Soroban RPC alone. It holds the contract ABI, transaction handling, WASM pinning, rail readiness, delivery-code handling, vault crypto and canonical JSON.

**The arbitrator console** lives under `/arbitrator` and shows the case file. It checks the terms hash and any `Content` proof on the device. If a seller claims to hold a valid code, the console hashes it locally, so the code never reaches the server. Irrevocable dispute rulings (`Release` or `Refund`) require explicit confirmation via a safety modal verifying the payout recipient before signing.

**Key UI & Security Features:**
- **TOTP 2FA Step-Up:** Sensitive profile and payout address changes require a verified TOTP code challenge before updating.
- **Canonical Terms JSON Export:** Both parties can download RFC 8785 canonical JSON order terms and cryptographic verification hashes for independent audit.
- **Rail Token Customization:** Terms form and order views dynamically reflect custom rail token symbols, decimals, and allowlists.
- **Accessibility & Themes:** Comprehensive ARIA attributes, keyboard navigation, and a persistent dark / light / high-contrast theme switcher.
- **Brand System & Design:** Modernized landing page and responsive layout with cohesive TrustEscrow visual branding.

## Data flow by action

### Negotiate and create

```
buyer and seller exchange revisions -> both accept one -> API freezes terms, returns canonical bytes
   -> buyer's client hashes terms, generates code, uploads encrypted code to the vault
   -> SDK checks the factory's WASM hash against its pin -> wallet signs create
   -> factory deploys escrow, emits escrow -> indexer links it to the draft
```

### Fund

```
buyer clicks Fund -> SDK checks trustline, balance and the instance's WASM hash
   -> wallet signs fund -> contract pulls A tokens, emits funded
   -> indexer updates Postgres, schedules the seller's delivery reminder
```

### In-person handover

```
buyer inspects the item, shows the code (QR or read aloud)
   -> seller signs submit_proof_with_code(Attestation, "", hash, code)
   -> contract checks the code, pays seller A - fee and fee_recipient fee, emits released
```

### Shipped goods

```
seller ships -> signs submit_proof(Tracking, uri, hash) -> contract emits proof, starts receipt window
   -> parcel arrives, buyer checks it and gives the code to the courier or seller
   -> anyone calls release_with_code(code), or the buyer signs confirm
   -> contract pays out, emits released
```

### Dispute

```
either party signs dispute, or anyone calls escalate after the receipt deadline
   -> contract emits disputed, starts arbitration window
   -> arbitrator reviews the case file, checks terms hash, proof and carrier
   -> arbitrator signs resolve(Release | Refund)
   -> or, if the deadline passes first, anyone (usually the keeper) refunds the buyer
```

### Timeouts

```
keeper sees a passed deadline -> calls the matching permissionless function
   -> contract sends funds to the predetermined party -> indexer updates Postgres
```

## Design decisions

- **One contract per trade, deployed from a factory.** Each escrow's state is isolated, auditing is simpler, and storage expiry is contained per escrow. The trade-off is a deploy fee per order. This is the hardest decision to reverse, because reversing it means rewriting the contract and the SDK together.
- **Two-sided evidence for release.** The seller is paid only on their proof plus the buyer's receipt, or on a ruling. In person this costs nothing extra, because `submit_proof_with_code` records both in one transaction.
- **No timeout pays the seller.** A fake tracking number can never become a payout just by waiting. The cost is that every silent buyer becomes arbitration work. The escalation rate is tracked as the product's main health metric.
- **A bounded arbitrator.** It chooses release or refund, never a split, and never after its deadline. If it does not rule in time, the buyer is refunded, because the burden of proof sits with the party asking to be paid. That means the seller carries the risk of an absent arbitrator.
- **A buyer-held code as the main receipt.** It is one action at handover, and it works over the phone for waybill trade. The price is an attack no cryptography can stop, where a seller or courier demands the code first. The app warns against that at the moment the code is shown.
- **Proof on-chain and single-shot.** The arbitrator needs no backend to see the seller's evidence, and revisable proof is not proof.
- **Mirror, don't trust, the events.** The indexer treats events only as a signal that something changed and reads state from the chain. That trades a little RPC traffic for correctness and idempotency.
- **A backend that holds no authority.** Drafts, chat, 2FA and notifications are real needs. So the backend exists, but its API holds no key and its vault holds only ciphertext.
- **Configuration reaches the future, never the present.** Factory config applies to new escrows only, and escrows have no admin or upgrade path. Clients pin the audited WASM hash.
- **The contract is currency-blind.** It accepts any allowlisted SEP-41 token. Settling in naira will be an integration change, not a contract rewrite.
- **Fee on release only.** A buyer whose trade failed gets back exactly what they paid in.

## Standards

Every TrustEscrow repository follows these rules. For setup and the day-to-day workflow, see [CONTRIBUTING.md](CONTRIBUTING.md).

### Repository baseline

- Each repository has a `README.md` (what it is, how to run and test it), a `LICENSE`, a `SECURITY.md` pointing to GitHub private vulnerability reporting, a committed lockfile and a pinned toolchain.
- CI runs on every push to `main` and every pull request, and must pass before merging.
- Environment variables are documented in `.env.example`. Secrets are never committed.

### Commits and review

- Changes land on `main` through pull requests, reviewed by someone other than the author. Changes to the contracts, the code vault, authentication or code handling should get two reviewers.
- Commits use Conventional Commits with a scope, for example `feat(escrow): add seller refund` or `test(vault): reject weak KDF params`. Each commit should be one logical change that builds and passes on its own.

### Testing

- **Contracts.** Every transition, every deadline boundary and every safety property has a test. CI runs `cargo fmt --check`, the release WASM build, clippy with warnings denied, and `cargo test`.
- **TypeScript.** CI runs `typecheck` and `test` (Vitest); the frontend also runs `lint`. Backend tests use in-memory PostgreSQL and need no external services.
- **Bug fixes.** Every fix comes with a test that fails without it.

### Shared artefacts

Some things must match byte for byte across repositories. Each has one source of truth, and changing it means updating every consumer in the same release.

| Artefact | Source of truth | Consumers |
|---|---|---|
| Delivery-code encoding, normalisation, hash | `crates/code` and `test-vectors/delivery-codes.json` in the contract repo | Frontend `src/sdk/code.ts`, backend `src/lib/delivery-code.ts` |
| Canonical JSON (RFC 8785) for the terms hash | The RFC | Backend and frontend implementations, which must produce identical bytes |
| Contract types and ABI | `crates/types` | Frontend `src/sdk`, backend `src/chain` |
| Window bounds, URI rules, fee cap | Escrow contract constants | Frontend `src/sdk/terms.ts` and `proof.ts`, backend `src/modules/drafts/terms.ts` |
| Settlement rails | Factory token allowlist | Backend `RAILS`, frontend `NEXT_PUBLIC_RAILS` |

### Security rules

These are never relaxed:

1. A plaintext delivery code never leaves the buyer's device, and is never logged or stored by a server.
2. Codes are never sent by SMS or email.
3. The API never holds a signing key. The keeper's key only pays fees.
4. The frontend takes its trust anchors from its build, never from the backend.
5. Every contract call is simulated before the user is asked to sign.

### Releases

- Each repository is versioned independently with SemVer and tagged `vX.Y.Z`.
- A contract release is identified by the sha256 of the escrow WASM, which appears in its release notes. The frontend pins that hash, so a new contract build is a breaking change until the pin is updated.
- Testnet deployments use `scripts/deploy-testnet.sh`. The factory id and WASM hash are published in this repository.

### Testnet deployment

| What | Id |
|---|---|
| Factory | `CDBD65SK43MNCD5JW7HXXV3EMG2OH2UJ3FKJ2O6OEQINV7NJZOIUQMRP` |
| Escrow WASM hash | `2589c9a9876bd2940b8f4dc8ce2b13aa2c654601a066d27f58f254d6b45473aa` |
| Settlement token, testnet USDC SAC | `CBIELTK6YBZJU5UP2WWQEUCYKLPU6AUNZ2BQ4WWFEIE3USCIHMXQDAMA` |

The contract repository holds the same values in `deployments/testnet.env`, and the full history of factory ids this network has had (see its README "Factory upgrades") in `deployments/testnet-factories.json`. Clients pin the WASM hash above and must refuse to fund an escrow instance running anything else.

Redeployed 2026-10-07, replacing an earlier deployment that predated `salt`/factory-provenance, `unswept_fee`, the dispute/ruling hash commitments, `extend_delivery`/`extend_receipt` and `create_and_fund`. No end-to-end trade has been run against this deployment yet; the previous version of this section described one against the superseded deployment. Run one and update this section once the backend/frontend point at these ids. The confirmation, dispute and timeout paths still need the same treatment before v1.0.

### What is actually running

The architecture above describes four backend processes. The current testnet deployment runs **only the API**. Render's free tier does not run background workers, so the indexer, notifier and keeper are built and tested but not deployed. That is a deployment limit, not a design change, and it is worth stating plainly because several things the documents promise do not happen on the live demo:

| Process | Deployed | What is missing without it |
|---|---|---|
| API | yes | — |
| Indexer | no | The read cache is never refreshed, so list views can show a state the chain has already moved past. Escrow detail pages are unaffected: they read the contract directly. |
| Notifier | no | No reminder or alert emails are sent. Notifications are still created and visible in the app. |
| Keeper | no | No automatic timeouts, TTL bumps or fee sweeps. Every one of those calls is permissionless, so anyone — either party included — can still make them from a CLI or the app. |

Nothing here puts funds at risk: all four processes are conveniences, and the contract enforces the rules either way. The honest summary is that the live demo shows the trade path, not the unattended operation of it.

Two further limits of the free tier: the API sleeps after roughly 15 minutes idle and takes around 23 seconds to answer the first request after that, and the managed Postgres instance expires 30 days after creation.

### Current status and gaps

- **CI workflows & Security policies:** Implemented across all repositories (`trustedescrow-contract`, `trustedescrow-backend`, `trustedescrow-frontend`, `trustedescrow-docs`). Each has an automated CI workflow, and the code repositories publish a `SECURITY.md`.
- **Auditing:** The contracts have not undergone an independent external audit. No mainnet funds should be held until complete.
- **End-to-end:** No full trade has been run against the current testnet deployment yet.
- **Seller trustlines:** The app prompts the buyer to add a settlement-asset trustline before depositing, but never prompts the seller. A seller without one cannot receive the payout, and the release reverts. Until that is fixed, a seller has to add the trustline themselves.

## Roadmap

**Where things stand.** The contracts, backend, and web app are implemented and run on testnet. The frontend is live in production on Vercel (`https://trustedescrow-frontend-eta.vercel.app`) with Direct On-Chain Escrow Explorer (`/escrow`). The contracts have full test coverage, including the randomised state-machine test, but **have not been audited**. Nothing should hold real value until they are.

**v1.0: Testnet MVP (in progress).**
- **Scope:** the full two-sided lifecycle, the backend, the web app and arbitrator console, and a USDC rail.
- **Done when:**
  - [x] all three repositories pass CI and meet the baseline above;
  - [x] security policies (`SECURITY.md`) and governance guidelines are published;
  - [x] testnet factory id, WASM hash and live web app are deployed and accessible;
  - an end-to-end run covers the in-person, shipped, dispute and timeout paths;
  - the question of integrating an existing Soroban escrow such as Trustless Work, rather than maintaining our own, has been settled and written down.

**v1.1: Usability.**
- **Scope:**
  - sponsored trustline reserves and fee bumps, so a first-time buyer needs no XLM (v1 users pay their own);
  - the SDK extracted into a standalone, versioned package;
  - hosted proof storage for digital goods;
  - dashboards for the two-sided release share and the escalation rate;
  - passkey smart wallets alongside Freighter.

**v1.2: Trust and assurance.**
- **Scope:** an arbitrator multisig, a factory admin multisig, public dispute statistics, an external audit of the contracts, and a bug bounty.

**Mainnet (USDC).** Only when all of these are true:
- the audit is published and every critical and high finding is fixed;
- the audited WASM hash is pinned in the production build;
- the arbitrator and factory admin are multisigs;
- the keeper and indexer are monitored;
- a guide to completing or exiting an escrow from the CLI is published;
- the custody model has had a legal review for the launch market.

**v2.0: Naira settlement.**
- **Scope:** a naira rail through a licensed partner, with SEP-24 deposits and withdrawals and local-currency display. **The contract does not change.**
- **Open questions:**
  - Which NGN asset will it use? cNGN is not confirmed live on Stellar.
  - Which anchors have real liquidity?
  - Which licensed partner will hold customer funds? Under CBN rules, this project cannot.

**v2.1: Milestones and reputation.**
- **Scope:** milestone trades, built as a factory feature that spawns one escrow per milestone. Reputation that counts escalations for silence against buyers who repeatedly go quiet.

**Not planned for v1:** fiat ramps, mobile apps, multi-arbitrator panels, split dispute outcomes, KYC tiers, cross-asset path payments, automated proof verification, and courier API integrations. One thing is excluded by design, not just deferred: **any release to the seller on a timeout**.
