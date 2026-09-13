# Security

TrustEscrow's contracts hold other people's money. Please report problems privately.

This policy covers every TrustEscrow repository: the contracts, the backend, the frontend and this documentation. For how the system is protected, see [THREAT_MODEL.md](THREAT_MODEL.md) and [ARCHITECTURE.md](ARCHITECTURE.md).

## Reporting a vulnerability

Use GitHub's **private vulnerability reporting** on the affected repository: the **Security** tab, then **Report a vulnerability**. If you are not sure which repository is affected, report it on [trustedescrow-contract](https://github.com/TrustedEscrow/trustedescrow-contract/security).

Do not open a public issue, pull request or discussion, or post in any chat, for anything that could put funds or user data at risk.

A good report includes:

- the repository and component affected, and the contract function or API endpoint involved;
- the sequence of calls or requests that triggers the problem;
- what you expected to happen, and what happened instead;
- the impact as you understand it.

A failing test is the most useful report there is.

## What happens next

- We aim to acknowledge a report within three working days, and to share an initial assessment within ten.
- We fix the problem in a private security advisory and publish the advisory once the fix is released. We credit you in it unless you prefer otherwise.
- Please give us reasonable time to fix a problem before disclosing it. We will agree a disclosure date with you.

Good-faith research is welcome. Test against your own local or testnet deployment. Do not interact with escrows that belong to other people, attempt social engineering, or run denial-of-service tests against hosted services.

## Supported versions

| Version | Supported |
|---|---|
| `main` of each repository | Yes |
| The latest published testnet deployment | Yes |
| Older testnet deployments | No. Escrows are never migrated between deployments |

There is no mainnet deployment. The contracts **have not been audited**, and must not hold real value until an external review has been completed and published.

## What counts as a vulnerability

### Contracts

Anything that breaks one of these properties:

1. **Conservation.** On release, `payout + fee == amount`. On refund, the buyer receives exactly `amount`. A finished escrow holds no tokens.
2. **Destination.** Principal only ever goes to the buyer or the seller. The fee goes only to the fee recipient, and only on release.
3. **Two-sided release.** The seller is paid only with seller proof on-chain plus the buyer's delivery code or signature, or by the arbitrator's ruling. No timeout pays the seller.
4. **Arbitrator bounds.** `resolve` works only in `Disputed`, only for the arbitrator, only before the arbitration deadline, and only chooses release or refund.
5. **No stuck funds.** Every open state has a permissionless exit.
6. **Immutability.** Proof, the terms hash and the delivery-code hash cannot change once written. Factory configuration changes never reach existing escrows.
7. **Terminality.** `Released`, `Refunded` and `Cancelled` accept no further transitions.

### Backend

- A plaintext delivery code reaching the server, its logs or its database.
- Bypassing sign-in, two-factor authentication, or the step-up on an endpoint that requires it.
- Reading or changing another user's drafts, messages, evidence or vault envelopes.
- The vault accepting an envelope below the key-derivation floors, or one that contains the code.
- The API process gaining access to a signing key, or the keeper doing anything beyond permissionless calls.
- An escrow's detail view showing state that did not come from contract storage.

### Frontend and SDK

- A delivery code leaving the buyer's device in plaintext.
- Code generation with less than 80 bits of entropy, or from a non-cryptographic random source.
- The factory id, escrow WASM hash or network being overridable by the backend, a URL or user input.
- Creating or funding an escrow whose WASM hash does not match the pinned hash.
- A transaction whose contents differ from what the app showed the user before signing.
- Any client producing a different code hash from the shared test vectors for the same input.

## Known limitations (not vulnerabilities)

These are documented design trade-offs. [THREAT_MODEL.md](THREAT_MODEL.md) explains each one.

- The arbitrator can decide a dispute in bad faith. It cannot steal, or act after its deadline.
- If the arbitrator never rules, the buyer is refunded, even if they received the goods and withheld the code. The seller carries this risk by design.
- A seller or courier can demand the delivery code before handing over the goods. No contract can prevent this; the app warns the buyer.
- The delivery code's security rests on its 80 bits of entropy. A client that generated shorter codes would make them brute-forceable from the public hash.
- The escrow trusts its token contract. The factory's allowlist is the defence against hostile tokens.
- Collusion between a buyer and a seller, for example to launder funds, is out of scope for v1.
