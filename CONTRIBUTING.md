# Contributing to TrustEscrow

Thank you for your interest in contributing to TrustEscrow. This guide covers all three repositories: how to set them up together, the workflow and coding standards, how to test, and how to submit a pull request.

TrustEscrow holds other people's money. Before you start, read [ARCHITECTURE.md](ARCHITECTURE.md) for how the system fits together and [THREAT_MODEL.md](THREAT_MODEL.md) for what it protects against. Most review feedback comes back to one of those two documents.

## Contents

- [Before you start](#before-you-start)
- [Repositories and stack](#repositories-and-stack)
- [Getting started](#getting-started)
- [Project structure](#project-structure)
- [Development workflow](#development-workflow)
- [Coding standards](#coding-standards)
- [Testing](#testing)
- [Changes that span repositories](#changes-that-span-repositories)
- [Security rules](#security-rules)
- [Submitting a pull request](#submitting-a-pull-request)
- [Reporting a vulnerability](#reporting-a-vulnerability)
- [License](#license)

## Before you start

- **Find or open an issue first.** Open it in the repository the change belongs to. If the change affects the trust model, the contract interface, or more than one repository, open it here in `trustedescrow-docs` so the design can be agreed before any code is written.
- **Never report a vulnerability in a public issue or pull request.** See [Reporting a vulnerability](#reporting-a-vulnerability).
- **Know the one rule everything protects:** the seller is paid only on their own proof plus the buyer's receipt, or on an arbitrator's ruling. No timeout ever pays the seller. A pull request that weakens this will not be merged, however convenient it is.

## Repositories and stack

| Repository | What it is | Stack |
|---|---|---|
| [trustedescrow-contract](https://github.com/TrustedEscrow/trustedescrow-contract) | Factory and escrow contracts, delivery-code crate, test vectors | Rust (stable), [soroban-sdk](https://docs.rs/soroban-sdk) 27, `wasm32v1-none` target, [Stellar CLI](https://developers.stellar.org/docs/tools/cli) |
| [trustedescrow-backend](https://github.com/TrustedEscrow/trustedescrow-backend) | API, indexer, notifier and keeper | Node 22, TypeScript, [Fastify](https://fastify.dev/) 5, [Kysely](https://kysely.dev/), PostgreSQL 14+, [Zod](https://zod.dev/), [Vitest](https://vitest.dev/) with PGlite |
| [trustedescrow-frontend](https://github.com/TrustedEscrow/trustedescrow-frontend) | Web app, arbitrator console, Escrow SDK | Node 22, [Next.js](https://nextjs.org/) 16, React 19, TanStack Query, Tailwind CSS 4, `@stellar/stellar-sdk`, `@stellar/freighter-api`, Vitest |
| [trustedescrow-docs](https://github.com/TrustedEscrow/trustedescrow-docs) | Architecture, threat model and this guide | Markdown |

## Getting started

### Prerequisites

- **Rust**, installed with [rustup](https://rustup.rs/). The contract repository's `rust-toolchain.toml` pins the channel, the `wasm32v1-none` target, `rustfmt` and `clippy`; rustup installs them on first build.
- **Stellar CLI**, for deploying to testnet.
- **Node.js** `v22` or higher, with npm.
- **PostgreSQL** `14` or higher, for running the backend. The backend tests don't need it.
- **Freighter** browser extension, set to **Testnet**.
- **A funded testnet identity** for deploying: `stellar keys generate dev --network testnet --fund`.

### Clone the repositories side by side

The READMEs refer to each other by relative path, so keep all three repositories in one folder:

```bash
mkdir trustedescrow && cd trustedescrow
git clone https://github.com/<your-username>/trustedescrow-contract.git
git clone https://github.com/<your-username>/trustedescrow-backend.git
git clone https://github.com/<your-username>/trustedescrow-frontend.git
```

In each repository, add the upstream remote:

```bash
git remote add upstream https://github.com/TrustedEscrow/<repository>.git
```

### 1. Contracts

```bash
cd trustedescrow-contract
make build     # release WASM into target/wasm32v1-none/release/
make test      # builds the WASM first; the factory tests deploy the real escrow binary
make clippy
```

Plain `cargo test` fails to compile the factory tests if the escrow WASM hasn't been built yet, so use `make test`. The first build is slow because dependencies are compiled with optimisations even for tests. Later builds are quick.

To deploy your own factory to testnet:

```bash
SOURCE=dev ARBITRATOR=G... FEE_RECIPIENT=G... TOKEN=C... scripts/deploy-testnet.sh
```

`TOKEN` is the settlement token's contract id (the testnet USDC Stellar Asset Contract). `FEE_BPS` defaults to 150. The script writes `deployments/testnet.env`; the next two steps need the values in it.

### 2. Backend

```bash
cd trustedescrow-backend
npm install
cp .env.example .env
createdb trustescrow
npm run migrate
npm run dev                # API on http://localhost:3000
```

Set these in `.env` before running:

- `SERVER_ENCRYPTION_KEY`: 32 random bytes, base64-encoded. Generate them with `node -e "console.log(require('crypto').randomBytes(32).toString('base64'))"`.
- `DATABASE_URL`: your local PostgreSQL connection string.
- `FACTORY_CONTRACT_ID`, `RAILS`, `ARBITRATOR_ADDRESSES`: see [Where the values come from](#where-the-values-come-from).
- `PUBLIC_WEB_URL=http://localhost:3001`, so the API allows the web app's origin.

The workers run from the compiled build:

```bash
npm run build
npm run start:indexer
npm run start:notifier
KEEPER_DRY_RUN=true npm run start:keeper   # needs KEEPER_SECRET; dry-run first
```

### 3. Frontend

```bash
cd trustedescrow-frontend
npm install
cp .env.example .env.local
npm run dev                # http://localhost:3001
```

Set `NEXT_PUBLIC_FACTORY_CONTRACT_ID`, `NEXT_PUBLIC_ESCROW_WASM_HASH` and `NEXT_PUBLIC_RAILS` in `.env.local`. Every value in this file is compiled into the browser bundle, so never put a secret there.

### Where the values come from

| From `deployments/testnet.env` | Backend `.env` | Frontend `.env.local` |
|---|---|---|
| `FACTORY_ID` | `FACTORY_CONTRACT_ID` | `NEXT_PUBLIC_FACTORY_CONTRACT_ID` |
| `ESCROW_WASM_HASH` | — | `NEXT_PUBLIC_ESCROW_WASM_HASH` |
| `TOKEN` | `tokenAddress` in `RAILS` | `tokenAddress` in `NEXT_PUBLIC_RAILS` |
| `ARBITRATOR` | `ARBITRATOR_ADDRESSES` | — |

`RAILS` and `NEXT_PUBLIC_RAILS` must be identical. If the frontend's WASM hash doesn't match the factory's, the app refuses to create escrows. That is the pin working as intended, not a bug to work around.

## Project structure

### trustedescrow-contract

```text
crates/types/          Types shared by both contracts
crates/code/           Delivery code: encoding, normalisation, hash (reference implementation)
contracts/escrow/      One instance per trade: custody, lifecycle, payout
  src/test.rs            Unit, event and race tests
  src/test_invariants.rs Randomised state-machine test
contracts/factory/     Deploys escrows; allowlist, config, admin transfer
test-vectors/          Delivery-code vectors every client must pass
scripts/               Testnet deployment
```

### trustedescrow-backend

```text
src/server.ts          API entry point
src/app.ts             Application wiring
src/auth/              SEP-53 sign-in, sessions, TOTP, step-up
src/modules/           Drafts, messages, vault, evidence, escrows, arbitration, notifications
src/indexer/           Event indexer and escrow cache
src/keeper/            Permissionless timeouts and TTL bumps
src/workers/           Entry points for the indexer, notifier and keeper
src/chain/             Soroban RPC reads and decoding
src/db/                Schema and migrations
src/cli/reconcile.ts   Operator tool for indexer gaps
test/                  Vitest suites (in-memory PostgreSQL)
```

### trustedescrow-frontend

```text
src/sdk/               Escrow SDK: no React, no backend; works against Soroban RPC alone
src/lib/               App wiring: config, API client, wallet, auth, step-up, transactions
src/components/        UI components
src/app/               Next.js routes, including /arbitrator
test/                  Vitest suites and the shared delivery-code fixture
```

## Development workflow

### Branches

Branch from an up-to-date `main`, and name the branch after the kind of change:

```bash
git checkout main && git pull upstream main
git checkout -b feat/short-description
```

Use `feat/`, `fix/`, `test/`, `docs/`, `refactor/` or `build/`.

### Commit messages

Use [Conventional Commits](https://www.conventionalcommits.org/) with a scope, in the imperative mood and lower case:

```text
feat(factory): two-step admin transfer
fix(indexer): stop on a gap instead of skipping ahead
test(escrow): cover same-ledger races
docs: document the code crate and test vectors
```

| Type | For |
|---|---|
| `feat` | New behaviour |
| `fix` | Bug fixes |
| `test` | Tests only |
| `docs` | Documentation only |
| `refactor` | No change in behaviour |
| `build` | Build and dependencies |
| `ci` | CI workflows |
| `chore` | Anything else |

Use the scopes already in each repository's history:

| Repository | Scopes |
|---|---|
| contract | `escrow`, `factory`, `code`, `types`, `scripts` |
| backend | `api`, `auth`, `chain`, `db`, `drafts`, `messages`, `vault`, `disputes`, `indexer`, `keeper`, `notifications`, `workers`, `lib` |
| frontend | `sdk`, `orders`, `escrow`, `vault`, `disputes`, `arbitration`, `account`, `auth`, `ui`, `app`, `lib` |

Keep each commit to one logical change that builds and passes tests on its own.

### Checks before pushing

Run the same checks CI runs.

Contracts:

```bash
cargo fmt --all --check
make build
make clippy
make test
```

Backend:

```bash
npm run typecheck
npm test
```

Frontend:

```bash
npm run typecheck
npm run lint
npm test
```

## Coding standards

### Contracts (Rust)

- Code is formatted with `rustfmt`, and clippy warnings are errors.
- Fail with a typed contract error (`panic_with_error!`), never a bare `panic!` or `unwrap()` on input the caller controls.
- Write state before any token transfer.
- Use checked arithmetic on amounts, and never turn off `overflow-checks` in the release profile.
- Keep the contracts small. Anything that can live off-chain without holding authority belongs in the backend or the SDK.
- A new or changed entry point must state who may call it, from which states, and what happens at each deadline. Update the entry-point list in [ARCHITECTURE.md](ARCHITECTURE.md) in the same change.
- An escrow has no admin, no upgrade path and no setters. Don't add one.

### TypeScript (backend and frontend)

- Use strict mode and ES modules. Avoid `any`; use exact types, or `unknown` with a type guard.
- Token amounts are `bigint` in code and strings in JSON, never JavaScript `number`. The contract uses `i128`.
- **Backend:**
  - Validate every request at the route boundary with a Zod schema.
  - Return errors as `{"error": {"code", "message", "details?"}}`.
  - Routes that mediate sensitive actions require a recent step-up.
- **Frontend:**
  - `src/sdk` must not import React or anything from `src/lib` or the backend client. It has to stay extractable as a standalone package.
  - Put domain logic in `src/sdk` or `src/lib`, where it can be tested without rendering.
  - Simulate every contract call before asking the wallet to sign.

### Documentation

- Update the repository's README when you change how it is set up, run or tested.
- Update [ARCHITECTURE.md](ARCHITECTURE.md) when you change the design, and [THREAT_MODEL.md](THREAT_MODEL.md) when you change what the system protects against.
- Documentation uses British English spelling (`normalise`, `authorisation`), consistent with the codebase.

## Testing

- **Every bug fix comes with a test that fails without it.**
- **Contracts:**
  - Test every state transition.
  - Test every deadline at exactly `now == deadline`, and just before and after it.
  - Test same-ledger races, such as a code release against a dispute.
  - If you add a transition, extend the randomised state-machine test in `test_invariants.rs` so it can reach the new transition.
  - Test snapshots under `test_snapshots/` are ignored by git; don't commit them.
- **Backend:** tests run against in-memory PostgreSQL (PGlite) and must not need a network, a real database or a live RPC. Use the helpers in `test/helpers.ts`.
- **Frontend:** unit tests cover the SDK and pure logic. `test/fixtures/delivery-codes.json` is a copy of the contract repository's vectors and must stay byte-identical.

## Changes that span repositories

Some things must match byte for byte across repositories. Each has one source of truth:

| Artefact | Source of truth | Also update |
|---|---|---|
| Delivery code: encoding, normalisation, hash | Contract: `crates/code`, `test-vectors/delivery-codes.json` | Frontend `src/sdk/code.ts` and `test/fixtures/`, backend `src/lib/delivery-code.ts` |
| Contract types and ABI | Contract: `crates/types` | Frontend `src/sdk/chain.ts` and `decode.ts`, backend `src/chain/decode.ts` |
| Window bounds, URI rules, fee cap | Escrow contract constants | Frontend `src/sdk/terms.ts` and `proof.ts`, backend `src/modules/drafts/terms.ts` |
| Canonical JSON for the terms hash | RFC 8785 | Backend `src/lib/canonical-json.ts` and frontend `src/sdk/canonical-json.ts` together |

To make a change like this:

1. Open an issue in `trustedescrow-docs` describing the change and every repository it touches.
2. Change the source of truth first.
3. Open linked pull requests in each consumer. Reference the source pull request in each description.
4. Maintainers merge them together, so `main` in every repository stays compatible with `main` in the others.

To refresh the code vectors in the frontend:

```bash
cp ../trustedescrow-contract/test-vectors/delivery-codes.json test/fixtures/delivery-codes.json
```

Any change to the escrow contract produces a new WASM hash. Say so in the pull request, because the frontend's `NEXT_PUBLIC_ESCROW_WASM_HASH` has to change with it.

## Security rules

These are never relaxed. A pull request that breaks one will not be merged.

1. A plaintext delivery code never leaves the buyer's device. It is never sent to, logged by or stored on a server, including "temporarily" or for debugging.
2. Delivery codes are never sent by SMS or email.
3. The API process never holds a signing key. The keeper's key only pays fees.
4. The frontend takes the factory id, WASM hash and network from its own build, never from the backend.
5. No timeout ever pays the seller.
6. Secrets come from the environment. Never commit them, log them or return them in an error.

Changes to the contracts, the code vault, authentication or delivery-code handling need two approving reviews.

## Submitting a pull request

1. **Keep it focused.** One issue per pull request. Split unrelated changes, even small ones.
2. **Run the checks** for every repository you touched (see [Checks before pushing](#checks-before-pushing)).
3. **Push to your fork** and open a pull request against `main` in the upstream repository.
4. **Describe it** so a reviewer can follow without asking:
   - what changed and why;
   - how you tested it, including any testnet transaction hashes;
   - which other repositories are affected, with links to their pull requests;
   - for UI changes, before-and-after screenshots;
   - the issue it resolves, for example `Closes #42`.
5. **Respond to review** by pushing new commits. Keep the history readable; don't force-push over a review in progress.

A maintainer merges once CI passes and the required reviews are in. The full merge rules are in [GOVERNANCE.md](GOVERNANCE.md#merge-rules).

## Reporting a vulnerability

Report anything that could put funds at risk privately, using GitHub's private vulnerability reporting: the **Security** tab, then **Report a vulnerability**, on the affected repository. Include:

- the component and function affected;
- the sequence of calls or requests that triggers the problem;
- what you expected to happen instead.

A failing test is the most useful report there is. See [SECURITY.md](SECURITY.md) for what counts as a vulnerability and what happens after you report.

## License

By contributing, you agree that your contribution is licensed under the license of the repository you contribute to:

- [trustedescrow-contract](https://github.com/TrustedEscrow/trustedescrow-contract): Apache-2.0.
- [trustedescrow-backend](https://github.com/TrustedEscrow/trustedescrow-backend) and [trustedescrow-frontend](https://github.com/TrustedEscrow/trustedescrow-frontend): MIT.
- [trustedescrow-docs](https://github.com/TrustedEscrow/trustedescrow-docs): MIT.
