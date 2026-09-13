# Threat Model

This document describes the security properties and known limitations of TrustEscrow across its contracts, backend and web app. Read it before deciding how much value to put through an escrow. For how the system is built, see [ARCHITECTURE.md](ARCHITECTURE.md). To report a vulnerability, see [SECURITY.md](SECURITY.md).

**Status:** v1 draft. The contracts **have not been audited**. Do not hold real value in them until an external review has been completed and published.

## What is trustless

- Funds are held by the escrow contract. No operator key can withdraw them to an arbitrary address.
- Principal only ever goes to the buyer or the seller. The fee goes only to the fee recipient, and only on release.
- **The seller cannot be paid without the buyer's code, the buyer's signature, or the arbitrator's ruling.** No timeout pays the seller.
- Every deadline, once passed, opens an exit that anyone can trigger. If the operator disappears, every escrow can still be finished from a CLI.
- Agreed terms, submitted proof and the delivery-code hash are committed on-chain. Nobody, including the operator, can revise them afterwards.
- The delivery code is known only to the buyer. The backend stores it encrypted under a key derived from the buyer's own credential, which the operator does not have.

## What requires trust

### The arbitrator

The operator controls the arbitrator address, so it could decide disputes in bad faith. It cannot steal, invent an outcome, or act once the arbitration deadline has passed. A multisig is planned for v1.2.

### Arbitrator availability

Because no timeout pays the seller, a seller whose buyer withholds the code depends on the arbitrator ruling in time. If the operator vanishes, disputed escrows refund the buyer once the arbitration deadline passes. A buyer who received the goods and withheld the code would then keep both the goods and the money.

**The seller carries this risk.** It is the direct cost of refusing to pay on the seller's evidence alone. A long arbitration window and an arbitrator multisig reduce the risk but do not remove it.

### The factory admin

The admin sets the escrow WASM hash, the arbitrator, the fee and the token allowlist, and all of these apply to **new** escrows only. An existing escrow has no admin, no upgrade path and no setter. A malicious WASM hash would therefore affect only escrows created after the change, which is why the web app pins the audited hash and refuses to fund anything else. Admin handover takes two steps, so a mistyped address cannot lock the factory.

### The web app

The web app is operated centrally. A compromised frontend could show misleading information before a user signs. Transaction summaries in the signing flow mitigate this but do not cure it. The app takes its factory id, WASM hash and network from its own build, so a compromised *backend* cannot redirect it.

### Proof hosting

Proof content at an external URI may disappear. The on-chain hash proves what was submitted, but it does not keep the content available.

### Code recovery

The backend lets a buyer who loses their device recover their code, gated on the buyer's own credential. The operator cannot recover a code on its own, but a phished credential can.

## Attacks the contract cannot prevent

**The seller or courier demands the code before handing over the goods.** No cryptography stops this. The app says, at the moment the code is revealed, that the code is the money and must never be given before the item is in hand and checked. Expect this to be a recurring source of support load.

**A buyer hands over the code after the delivery deadline.** The seller's `submit_proof_with_code` then races anyone's `refund_after_delivery_timeout`, and whichever lands first wins. The seller UI warns against handing over goods once the deadline has passed.

## Threats and mitigations

| Threat | Impact | Mitigation | Residual risk |
|---|---|---|---|
| Seller submits fake tracking; buyer unreachable | Seller paid for nothing | No timeout pays the seller; silence escalates to the arbitrator | Arbitration load |
| Buyer receives goods, withholds code | Seller unpaid | Tracking proof on-chain, escalation, arbitrator ruling | Seller carries arbitrator-availability risk |
| Buyer goes silent to force every trade into arbitration | Operational cost, slow payouts | Escalations recorded on-chain by origin; reputation planned | Watch the escalation rate |
| Full backend compromise | Chat and drafts exposed; misleading UI | API holds no key; vault holds only ciphertext | Attacker can read negotiation history and mislead users |
| Backend points the app at another factory or binary | Users fund an unaudited escrow | Trust anchors come from the build; WASM hash pinned | A compromised build pipeline |
| Keeper key stolen | Fee balance drained | The key can only make calls anyone could make | Timeouts delayed until someone else calls them |
| Code brute-forced from the public hash | Release without buyer consent | 80-bit code; release also needs seller proof | Total, if anyone ever shortens the code |
| Code intercepted by SIM swap | Early release | Codes never sent by SMS or email | Buyer sharing a screenshot |
| Vault recovery abused | Attacker learns a code | Recovery needs the buyer's credential; key-derivation floors enforced | Credential phishing |
| Buyer rotates the code after handover | Seller's release fails | No rotation exists | — |
| Arbitrator key stolen | Disputes decided by attacker | Outcome limited to release or refund, before the deadline | Can favour one side; cannot steal |
| Arbitrator absent | Disputes unresolved | Deadline refunds the buyer | Honest sellers in disputes lose |
| Seller disputes from `Funded` to block a refund | Buyer's refund delayed | `dispute` from `Funded` closes at the delivery deadline | Delay bounded to one arbitration window |
| Operator disappears | App offline | Every timeout permissionless; CLI path | Users must know the escape hatch exists |
| Malicious escrow WASM set in the factory | New escrows compromised | Config reaches new escrows only; clients pin the hash | Users on a frontend that skips the pin |
| Malicious or lookalike token | Accounting lies, re-entrancy | Factory allowlist; state written before transfers | Admin allowlisting a bad token |
| Proof content swapped or removed | Misleading or missing evidence | On-chain hash fixes the content | Arbitrator may lack the content itself |
| Seller overwrites proof | Evidence laundering | Proof is single-shot | — |
| Terms rewritten after funding | Unfair arbitration | On-chain terms hash, re-checked at review | Depends on canonical JSON being correct |
| Escrow archived by storage expiry | Escrow unusable | TTL extended on every call; public `bump`; keeper | SDK must offer the restore step |
| Indexer falls behind RPC retention | Escrow missing from lists | Stops loudly until an operator reconciles | Detail view unaffected |
| Contract bug | Unrecoverable loss | Invariant and randomised tests, small surface | Real. No mainnet without an audit |

## Out of scope

- **Collusion and money laundering.** A buyer and seller acting together can use the platform to move value. This is documented, not mitigated, in v1. KYC tiers are on the roadmap.
- **Token contract bugs.** The settlement token is an external contract. The allowlist limits which tokens are used but cannot fix a bug inside one.
- **Stellar network events.** Ledger upgrades, validator behaviour and protocol changes are outside the system's control.
- **Key compromise.** Anyone holding a party's key can act as that party.

## Summary

| Property | Value |
|---|---|
| Who holds funds | The escrow contract, one per trade |
| Release to the seller | Seller proof plus buyer receipt, or an arbitrator ruling |
| Release to the seller on a timeout | **Never** |
| Arbitrator powers | Release or refund, before its deadline only |
| Admin or upgrade on an existing escrow | **None** |
| Factory config changes | Apply to new escrows only |
| Backend authority over funds | **None**; API holds no key |
| Plaintext delivery codes off the buyer's device | **None** |
| Exit if the operator disappears | Every timeout is permissionless |
| Audit status | **Not audited** |
