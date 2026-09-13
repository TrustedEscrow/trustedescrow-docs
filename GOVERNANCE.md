# Governance

This document describes how the TrustEscrow project is run: who does what, how decisions are made, the rules for merging and releasing, and who holds the keys that operate the deployed contracts. It applies to every TrustEscrow repository.

## Roles

- **Contributors** are anyone who opens an issue or a pull request. [CONTRIBUTING.md](CONTRIBUTING.md) explains how.
- **Reviewers** are contributors trusted to review changes in areas they know well. Their approval counts towards the merge rules. Maintainers grant this role after a record of careful contributions.
- **Maintainers** have write access to the repositories. They merge pull requests, cut releases, triage security reports and administer the GitHub organisation.
- **Key holders** are maintainers designated to hold one of the signing keys that operate a deployment (see [Key custody](#key-custody)). Holding a key is a separate role from merging code. Being a maintainer does not make someone a key holder.

## Maintainers

<!-- Add each maintainer: GitHub handle, the areas they own, and any key-holder role. -->

| Maintainer | Areas | Key-holder role |
|---|---|---|
| _to be added_ | | |

A change to this list is made by pull request and needs approval from a majority of the current maintainers.

## How decisions are made

**Day-to-day changes** are decided in pull request review. A pull request is accepted when CI passes and it has the approvals the [merge rules](#merge-rules) require.

**Design changes** start as an issue in [trustedescrow-docs](https://github.com/TrustedEscrow/trustedescrow-docs). A design change is anything that:

- changes the release rule or the trust model;
- changes a contract's interface;
- changes an artefact shared between repositories;
- gives the operator a new power.

The issue states the problem, the proposed change, what it costs and what it would break. It stays open for comment for at least seven days; security fixes are the exception. Maintainers aim for consensus. If there is none, a majority of maintainers decides. The outcome is recorded in the design decisions in [ARCHITECTURE.md](ARCHITECTURE.md), and the issue is closed with a link to it.

**Fixed commitments.** These are the promises the system makes to its users:

- No timeout ever pays the seller.
- A plaintext delivery code never leaves the buyer's device.
- The backend never gains authority over funds.
- An existing escrow is never changed by an operator.

A proposal to change one must be discussed publicly in this repository and needs the approval of every maintainer.

## Merge rules

- All changes reach `main` through pull requests. Nobody pushes directly to `main` or force-pushes it.
- CI must pass.
- Every pull request needs one approval from someone other than its author.
- Security-critical changes need **two** approvals. That covers the contracts, the code vault, authentication, delivery-code handling, key handling, and CI or deployment scripts.
- Changes that span repositories are merged together by one maintainer, so `main` in every repository stays compatible with the others.
- Security fixes may be prepared in a private advisory and merged without public discussion, but they still need two approvals.
- Any maintainer may revert a change that breaks `main` or a [security rule](CONTRIBUTING.md#security-rules) without waiting for review. The revert is then discussed in the original pull request.

## Releases

- Each repository is versioned independently with Semantic Versioning, and maintainers tag releases `vX.Y.Z`.
- A contract release lists the sha256 of the escrow WASM and the factory WASM in its release notes. Anyone can rebuild them from the tagged source with the pinned toolchain.
- The frontend's pinned escrow WASM hash is updated only after the matching contract release has been published and reviewed.
- Any maintainer may deploy to testnet. Each deployment's factory id, escrow WASM hash and deployment ledger are recorded in this repository.
- Mainnet deployment requires every item in the mainnet gate in the [roadmap](ARCHITECTURE.md#roadmap), and a design decision recording that the gate was met.

## Key custody

A deployment is operated by a handful of keys. None of them can take escrowed funds, but each has real power, so custody is deliberate.

| Key | What it can do | What it cannot do | Custody |
|---|---|---|---|
| Factory admin | Set the escrow WASM hash, arbitrator, fee and fee recipient for **new** escrows; manage the token allowlist; propose a new admin | Touch any existing escrow | Testnet: a key holder. Mainnet: a multisig of key holders on hardware wallets |
| Arbitrator | Rule release or refund on every escrow that recorded it | Send funds anywhere but the buyer or seller; act after the deadline | Testnet: a key holder. Mainnet: a multisig |
| Fee recipient | Receive platform fees | Anything else | An address the project controls; a multisig on mainnet |
| Keeper | Pay fees for permissionless timeout and `bump` calls | Anything anyone else couldn't do | A hot key on the keeper host, holding only a small XLM balance |
| `SERVER_ENCRYPTION_KEY` | Decrypt TOTP seeds at rest | Decrypt delivery codes | The backend host's secret manager |

### Rules

- **Old arbitrator keys stay live.** The arbitrator and fee recipient are copied into each escrow at creation and never change for that escrow. Changing the factory's arbitrator does not move existing disputes. An arbitrator key must therefore stay available and under control until every escrow that recorded it has settled. Check that no open escrow references a key before retiring it.
- **Admin handover is two-step.** The new admin accepts from its own key before the old one is retired. `set_config` cannot change the admin.
- **Keys never enter a repository.** Mainnet keys never touch CI or a developer laptop; signing happens on hardware wallets. Only testnet keys may be used from scripts.
- **Holders are recorded, keys are not.** This document records who holds each key, never the keys themselves. A change of holder is recorded by pull request.

### If a key is compromised

- **Factory admin.** Propose a new admin at once. If the attacker has already moved the admin role, deploy a new factory, publish its id, and ship a frontend build pinned to it. Existing escrows are unaffected either way.
- **Arbitrator.** Point the factory at a new arbitrator for new escrows. Existing escrows still name the old key, and it can rule on their disputes until each deadline passes. Tell affected users, and track those disputes to their end.
- **Keeper.** Stop the keeper, move the remaining balance, and start it with a new key. Anyone can make the keeper's calls in the meantime, so nobody is stranded.
- **`SERVER_ENCRYPTION_KEY`.** Rotate it, revoke sessions, and ask users to re-enrol two-factor authentication. Delivery codes are not exposed.

## Incident response

The contracts have no pause, by design. During an incident the project can:

- take the web app offline or show a warning banner;
- remove a token from the allowlist, which stops new escrows in that token;
- point the factory at a new escrow WASM for new escrows;
- keep the keeper running so timeouts still fire.

The project cannot freeze, migrate or reverse an existing escrow. Every escrow still finishes by its own rules, and anyone can complete or exit one from a CLI.

Security reports follow [SECURITY.md](SECURITY.md). Once an incident is resolved, the project publishes an advisory covering what happened, who was affected and what changed.

## Changing this document

Changes to this document follow the design-change process above.
