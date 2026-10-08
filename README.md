# TrustEscrow

TrustEscrow is a peer-to-peer escrow for online trade on Stellar, built on Soroban smart contracts. It lets a buyer and a seller who have never met trade safely. The buyer's payment is locked in a contract and released to the seller only once both sides have given evidence that the goods arrived.

This repository is the documentation hub for the project. The code lives in three separate repositories, described below.

## Why two-sided escrow

Trade between strangers has a first-mover problem. If the buyer pays first, they are trusting the seller to ship. If the seller ships first, they are trusting the buyer to pay. Across much of online commerce, from sellers on Instagram and WhatsApp to goods sent by waybill between cities, one side simply takes the risk. Fraud in both directions is common enough that many trades never happen at all.

Escrow services exist, but they usually swap one trusted party for another: a company holds the money and decides who gets it. And escrow is only as good as its evidence. A tracking number shows that a parcel moved, not that the buyer received what they paid for.

TrustEscrow removes the middleman from custody and asks both sides for evidence. The funds sit in a contract that nobody, including the operator, can redirect. The seller commits proof of delivery on-chain. The buyer confirms receipt by handing over a one-time delivery code once the goods are in their hands. The contract pays the seller only when it has both. Neither party is paid on their own word.

Common uses:

- **Social-commerce purchases:** buying from a seller found on Instagram, WhatsApp or a marketplace listing.
- **Waybill and courier deliveries:** goods shipped between cities, where buyer and seller never meet.
- **In-person handovers:** phones, laptops and second-hand goods exchanged in person, paid out the moment the buyer checks the item.
- **Digital goods and freelance work:** files and deliverables whose content hash is committed on-chain and can be checked by the buyer.

## How an escrow works

An escrow is a contract created for one trade. It holds the agreed amount and a set of deadlines:

- **Agree and deposit.** The buyer and seller agree terms, and the buyer deposits the amount into a new escrow. The terms are fingerprinted on-chain, so nobody can change them later.
- **Deliver and prove.** The seller delivers and submits proof on-chain: a tracking reference, a content hash, or an attestation for in-person trades. Proof can't be edited once submitted.
- **Receive and release.** When the goods are in hand and checked, the buyer gives the seller their delivery code, or confirms in the app. The contract pays the seller, less a small platform fee.
- **Dispute if needed.** If the two disagree, either can open a dispute, and an arbitrator chooses release or refund. The arbitrator can't take the funds, invent another outcome, or sit on the case forever.
- **Deadlines keep nobody stuck.** If the seller never delivers, the buyer is refunded. If the buyer goes silent after delivery, the escrow goes to the arbitrator. If the arbitrator doesn't rule in time, the buyer is refunded. **No deadline ever pays the seller.**

The platform fee is charged only when the seller is paid. A buyer whose trade fails gets back exactly what they deposited.

See [ARCHITECTURE.md](ARCHITECTURE.md) for the precise model and the system design.

## Repositories

| Repository | Description |
|---|---|
| [trustedescrow-contract](https://github.com/TrustedEscrow/trustedescrow-contract) | The Soroban factory and escrow contracts, in Rust. Holds funds and enforces the release rule, one escrow per trade. The source of truth. |
| [trustedescrow-backend](https://github.com/TrustedEscrow/trustedescrow-backend) | The API and background workers, in TypeScript. Handles negotiation, chat, notifications, the encrypted delivery-code vault, and a read cache of on-chain escrow state. Holds no authority over funds. |
| [trustedescrow-frontend](https://github.com/TrustedEscrow/trustedescrow-frontend) | The web app and arbitrator console, in Next.js, plus the Escrow SDK. Connects a Freighter wallet, walks buyers and sellers through each trade, and signs every contract call in the user's wallet. |
| [trustedescrow-docs](https://github.com/TrustedEscrow/trustedescrow-docs) | This repository: architecture, threat model and contributor guide. |

The three code repositories are independent and can be developed and deployed separately. The contracts are the only component that holds funds or enforces rules; the backend and frontend are conveniences built around them. Every escrow can still be completed, disputed or timed out from a CLI with neither of them running.

## Live Deployments

| Component | Network / Host | URL / Contract ID |
|---|---|---|
| **Production Frontend** | Vercel (Production) | [trustedescrow-frontend-eta.vercel.app](https://trustedescrow-frontend-eta.vercel.app) |
| **Direct On-Chain Explorer** | Vercel | [trustedescrow-frontend-eta.vercel.app/escrow](https://trustedescrow-frontend-eta.vercel.app/escrow) |
| **Factory Contract** | Stellar Testnet | [`CDBD65SK43MNCD5JW7HXXV3EMG2OH2UJ3FKJ2O6OEQINV7NJZOIUQMRP`](https://stellar.expert/explorer/testnet/contract/CDBD65SK43MNCD5JW7HXXV3EMG2OH2UJ3FKJ2O6OEQINV7NJZOIUQMRP) |
| **Escrow WASM Hash** | Stellar Testnet | `2589c9a9876bd2940b8f4dc8ce2b13aa2c654601a066d27f58f254d6b45473aa` |
| **Settlement Rail** | Stellar Testnet USDC SAC | [`CBIELTK6YBZJU5UP2WWQEUCYKLPU6AUNZ2BQ4WWFEIE3USCIHMXQDAMA`](https://stellar.expert/explorer/testnet/contract/CBIELTK6YBZJU5UP2WWQEUCYKLPU6AUNZ2BQ4WWFEIE3USCIHMXQDAMA) |

## Quickstart

Each repository has its own setup instructions in its README. End to end:

1. **Deploy the contracts** (`trustedescrow-contract`) to testnet with `scripts/deploy-testnet.sh`. Note the factory id and escrow WASM hash it writes to `deployments/testnet.env`.
2. **Run the backend** (`trustedescrow-backend`) pointed at that factory id. It indexes escrow events into PostgreSQL and serves the API.
3. **Run or visit the frontend** (`trustedescrow-frontend`): test online at [trustedescrow-frontend-eta.vercel.app](https://trustedescrow-frontend-eta.vercel.app) or run locally pointed at the factory id and the escrow WASM hash. Connect Freighter on testnet and create or inspect an escrow.

[CONTRIBUTING.md](CONTRIBUTING.md) walks through all three steps in detail, including which value goes where.

## Documentation

- [ARCHITECTURE.md](ARCHITECTURE.md): system design, data flow, the escrow model, standards and roadmap.
- [SECURITY.md](SECURITY.md): security properties and how to report a vulnerability.
- [THREAT_MODEL.md](THREAT_MODEL.md): what is trustless, what requires trust, threats and mitigations.
- [CONTRIBUTING.md](CONTRIBUTING.md): how to set up, build, test and contribute across the repositories.
- [GOVERNANCE.md](GOVERNANCE.md): maintainer roles, decision-making, merge rules, and deployment key custody.

## Status

v1 is implemented and runs live on Stellar testnet. The frontend is deployed in production on Vercel at [trustedescrow-frontend-eta.vercel.app](https://trustedescrow-frontend-eta.vercel.app), featuring:
- A brand redesign and interactive marketing landing page (`/`).
- Direct On-Chain Escrow Explorer (`/escrow`) allowing anyone to inspect, fund, and manage contracts directly on-chain via Soroban RPC without requiring an off-chain server.
- Web app and arbitrator console (`/arbitrator`) with confirmation modals preventing accidental irreversible rulings.
- Enhanced security with TOTP 2FA step-up prompts for payout address updates.
- Downloadable cryptographic terms JSON proofs (RFC 8785) with committed terms hashes.
- Comprehensive accessibility with ARIA attributes and focus management.
- Dynamic theme switcher supporting light, dark, and system preference detection.

The smart contracts **have not been audited**. Do not use them to hold real value until an external review has been completed and published. See the roadmap in [ARCHITECTURE.md](ARCHITECTURE.md#roadmap).

## License

This documentation is MIT. See [LICENSE](LICENSE).

Each code repository carries its own license: [Apache-2.0](https://github.com/TrustedEscrow/trustedescrow-contract) for the contracts, and MIT for the [backend](https://github.com/TrustedEscrow/trustedescrow-backend/blob/main/LICENSE) and [frontend](https://github.com/TrustedEscrow/trustedescrow-frontend/blob/main/LICENSE).
