# Secure Agent/Worker Registration — attested identity, no impersonation

Topical note for the steadfaste identity layer (closes B-S1.4 key lifecycle + B-S1.5 remote cryptographic identity). Purpose: let a Worker or foreign coding-agent prove **who it is and what it runs**, so the Model Reputation Library cannot be gamed by an imposter and remote identity is trustworthy. Local process-lineage trust breaks the moment a worker is remote, swappable, or a delegated CLI the core did not build.

## The three frauds this closes
1. **Impersonation** — a worker claims to be another agent or a high-reputation model to game the reputation library.
2. **Replay** — an old, previously-authorized handshake is replayed.
3. **MITM substitution** — a different worker is substituted between the core and the real one.
Plus the key-lifecycle hole (how keys are generated / recovered / rotated).

## Enrollment — Steward-orchestrated, not self-service
- Enrollment is a **Steward-orchestrated act**, recorded in the Ledger. Not a worker self-registering.
- A keypair is generated; the worker **proves possession** of the private key (challenge/response).

## The signed worker_credential
On successful enrollment the Constitution issues a `worker_credential` binding:
`worker_id` + public key + `agent_id` + a **`model_manifest_hash`** + `issued_ts` + `expiry`.

- The **`model_manifest_hash` is an ExecutableIdentity-style hash of the ACTUAL installed CLI/binary** (the thing that will run). This is what stops a worker claiming to *be* a high-reputation model: its asserted identity must hash-match what is actually installed. Same discipline as hashing the exact loaded binary (nono-style).
- Only the Constitution's private key can sign a credential → **no forgery** (nothing can forge the Constitution's key).

## Mutual authentication at every handshake
- Worker signs a fresh nonce (proves possession, defeats **replay**).
- Constitution signs a worker nonce (proves to the worker it is talking to the real core, defeats **MITM**).
- There is no unauthenticated path.

## Model/agent attestation
A worker's claimed identity is cryptographically bound to the attested binary + version + provider. It cannot choose to present a different identity than what its manifest hashes to.

## Trust-tier on-ramp
A new/unenrolled worker starts at **Tier 0**: dry-run only, human-in-the-loop, no authority. It EARNED higher tiers by ledgered evidence — never by claim. Enrollment gives identity; trust tiers gate authority; they are separate.

## Revocation — no re-entry of blacklisted workers
- De-listed / untrusted workers have credentials **revoked (a CRL checked at handshake)**, so a blacklisted model/agent cannot re-register under a fresh identity and re-enter.

## Key lifecycle (closes B-S1.4)
- **M-of-N / Steward-gated recovery**: the trust-root key cannot be a single lost point.
- **Rotation** with successor signing (so rotation doesn't orphan the credential set).
- Secrets + private keys live outside the worker sandbox (root-owned mode-600, env/pass/age), never in the Ledger, never in a Model Profile.

## Anti-fraud invariants (conformance-testable)
- No impersonation: credential binds to attested binary/version.
- No replay: fresh nonce per handshake.
- No forgery: only the Constitution's key signs; peers verify with the PUBLIC key only.
- No re-entry: CRL checked at handshake; revoked = gone.
- Trust-tier separation: enrollment ≠ authority; Tier-0 on-ramp is by design, higher tiers only prove out.

## Why it matters for coexistence
A second harness (e.g. hermes-cortex) talking to steadfaste must register as a governed worker through this same flow — it does not get to rely on process lineage. The registration is what ties a trusted identity to a trust tier, so the whole approval/reputation system rests on an unforgeable identity layer rather than self-reporting.
