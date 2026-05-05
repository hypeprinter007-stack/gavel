# Counsel — Decision Integrity Layer for Institutional AI Agents

**EasyA Consensus 2026 · Miami · Multi-chain on Base + Solana**

Counsel is a compliance infrastructure layer for institutional AI agents. Pay in Base USDC or Solana USDC via x402, get a tamper-evident audit trail anchored on **both** chains every single call, and let a human officer sign off with **Metamask or Phantom**. Genuinely chain-neutral end-to-end.

---

## The Problem

AI agents are moving into institutional workflows: trade approvals, vendor onboarding, compliance screening. But there's no standard way to:

1. **Pay for compliance data** at query time (current: annual licenses, manual integrations)
2. **Prove** the AI saw what it claims to have seen before recommending APPROVE
3. **Give a compliance officer** a reviewable, signable record anchored to a block

Counsel solves all three.

---

## How It Works

```
Client Agent ──$0.05 USDC x402 (Base OR Solana)──►  Counsel API (AWS Lambda)
                                                          │
                                          ┌───────────────┼───────────────┐
                                          ▼               ▼               ▼
                                    MRU SENTINEL    Orbis Trade     Orbis Embedded
                                    Travel Rule     Finance Risk    Finance Score
                                   (x402 $0.005)  (x402 $0.005)   (x402 $0.005)
                                          │               │               │
                                          └───────────────┴───────────────┘
                                                          │
                                              Bedrock Claude synthesis
                                                          │
                                       Merkle root over evidence + synthesis
                                                          │
                                  ┌───────────────────────┴───────────────────────┐
                                  ▼                                               ▼
                           Base mainnet                                    Solana mainnet
                          (calldata tx)                                   (Memo program)
                                  │                                               │
                                  └───────────────────────┬───────────────────────┘
                                                          │
                              Officer signs Merkle root: Metamask (EIP-191) OR Phantom (Ed25519)
                                                          │
                                       Server detects scheme, verifies, returns signer
```

1. **Client pays $0.05 USDC** via x402 — Base or Solana, their choice. CDP facilitator settles on whichever chain the client signed for.
2. **Counsel pays compliance APIs** in parallel via x402 (live: MRU Travel Rule on Base; Solana providers registered, integration pending)
3. **Claude Haiku synthesizes** the evidence into a structured recommendation
4. **Merkle root** is computed over all evidence + synthesis hashes
5. **The same Merkle root is anchored to Base AND Solana in parallel** — EIP-1559 calldata on Base, Memo program on Solana. Two independent L1s every call.
6. **Compliance officer signs the Merkle root** with whatever wallet they have. Server inspects the request: with `signer_pubkey` it verifies an Ed25519 signature against the Solana pubkey; without, it ECDSA-recovers the EVM address from the EIP-191 personal_sign.

Forging an approval requires breaking SHA256 *and* the officer's private key (secp256k1 or Ed25519). Reverting the audit trail requires reorging two independent L1s.

---

## Live Demo

**API:** `https://ki55wa4a21.execute-api.us-east-1.amazonaws.com`

```bash
pip install requests 'x402[evm,svm]' eth-account solders base58
export CLIENT_PRIVATE_KEY=0x...        # EVM payer (for Base USDC)
export SOLANA_CLIENT_KEY=...           # base58 Solana keypair (for Solana USDC)
export OFFICER_PRIVATE_KEY=0x...       # optional, only for the EVM officer path

# Default: pay in Base, sign with EVM officer
python test_e2e.py

# Pay in Solana USDC, sign with a Phantom-style Solana wallet
python test_e2e.py --solana-pay --solana-sign
```

**Sample response:**

```json
{
  "session_id": "6707f47b-ce61-4faf-9fa7-aef629adbff5",
  "vendor": "Northstar Crypto Capital",
  "merkle_root": "ab0898397c86fbf97c99c6f8b29e55ab697315705777ee1d106e2dcb9bd686b3",
  "anchors": {
    "base": {
      "tx": "0x7fb4d10770b74014d16d92d6349697c30dca1eabd6bbd85e93b2095444e9b263",
      "explorer_url": "https://basescan.org/tx/0x7fb4d10770b74014d16d92d6349697c30dca1eabd6bbd85e93b2095444e9b263"
    },
    "solana": {
      "tx": "sXsqoM2nuizMvjXn5VjynmUT1RWzE6jvvJxzhqHu8RabMeBenXqjVsFBDNYECVcBFa9EsBkfvzcoKep61WNLoxx",
      "explorer_url": "https://solscan.io/tx/sXsqoM2nuizMvjXn5VjynmUT1RWzE6jvvJxzhqHu8RabMeBenXqjVsFBDNYECVcBFa9EsBkfvzcoKep61WNLoxx"
    }
  },
  "synthesis": {
    "risk_level": "low",
    "recommendation": "APPROVE",
    "summary": "Northstar Crypto Capital presents a low-risk profile across all compliance dimensions...",
    "key_findings": [...]
  },
  "officer_url": "/v1/officer/6707f47b-ce61-4faf-9fa7-aef629adbff5"
}
```

---

## API

### `POST /v1/diligence` — x402 gated ($0.05 USDC, Base **or** Solana)

The route advertises two `accepts` payment options. Clients pick the chain by signing for the corresponding scheme.

```json
{
  "vendor_name": "Northstar Crypto Capital",
  "vendor_country": "AE",
  "vendor_wallet": "0x...",
  "amount_usd": 50000
}
```

Returns: `session_id`, `evidence`, `synthesis`, `merkle_root`, `anchors.base`, `anchors.solana`, `officer_url`

### `GET /v1/officer/{session_id}`

Returns the officer review view: session metadata, `merkle_root`, both `anchors`, `sign_url`.

### `POST /v1/officer/{session_id}/sign`

The officer signs the `merkle_root` with whatever wallet they have. Two schemes supported:

**EVM (Metamask) — EIP-191 `personal_sign`:**
```json
{
  "decision": "APPROVED",
  "signature": "0x<personal_sign(merkle_root)>",
  "notes": "Travel rule clear."
}
```
Server ECDSA-recovers the signer address.

**Solana (Phantom) — Ed25519:**
```json
{
  "decision": "APPROVED",
  "signature": "<base58 Ed25519 signature over merkle_root>",
  "signer_pubkey": "<base58 Solana pubkey>",
  "notes": "Travel rule clear."
}
```
Server verifies the signature against the supplied pubkey.

Returns: `decision`, `signer`, `signature_scheme` (`"eip191"` or `"ed25519"`), `merkle_root`, both `anchors`

---

## The Integrity Chain

```
evidence_hash_1 ─┐
evidence_hash_2 ─┼─► merkle_root ──┬─► Base tx (calldata)        ──┐
synthesis_hash  ─┘                 └─► Solana tx (Memo program)   ─┤
                                                                    └─► officer.sign(merkle_root)
                                                                                │
                                                                          signer_address
                                                                    (cryptographically bound)
```

Every Counsel decision carries:
- A **content hash** of every data source the AI touched
- **Two on-chain timestamps** (Base + Solana) proving when it happened
- A **wallet signature** from the human officer tied to that exact evidence set

---

## Multi-Chain via `gavel_toolkit`

`gavel_toolkit` is the provider-agnostic discovery layer — a JSON registry mapping compliance intents to x402 endpoints across multiple chains. Forkable, no Python changes needed to add a provider.

```python
from gavel_toolkit.discovery import resolve, list_intents

list_intents()
# ['embedded_finance_compliance', 'kyc_attestation', 'trade_finance_risk',
#  'travel_rule_compliance', 'wallet_screening']

# resolve() is chain-agnostic — same call returns providers across networks
resolve("wallet_screening")
# [{"id": "solana_aml_checker",   "network": "solana:5eykt4Us...", "price_usd": 0.001},
#  {"id": "scorechain_solana_aml","network": "solana:5eykt4Us...", "price_usd": 0.01}]
```

**Built-in providers:**

| Provider | Intent | Network | Price |
|----------|--------|---------|-------|
| MRU SENTINEL Travel Rule | `travel_rule_compliance` | `eip155:8453` | $0.005 |
| Orbis Trade Finance Risk | `trade_finance_risk` | `eip155:8453` | $0.005 |
| Orbis Embedded Finance Score | `embedded_finance_compliance` | `eip155:8453` | $0.005 |
| Scorechain Solana AML | `wallet_screening` | `solana:5eykt4Us...` | $0.01 |
| Solana Attestation Service | `kyc_attestation` | `solana:5eykt4Us...` | $0.005 |
| SOLANA AML Checker | `wallet_screening` | `solana:5eykt4Us...` | $0.001 |

See [gavel_toolkit/README.md](gavel_toolkit/README.md) for the full registry schema.

---

## Tech Stack

| Layer | Tech |
|-------|------|
| Payment rail (inbound) | [x402](https://github.com/coinbase/x402) `[evm,svm,fastapi]` — accepts Base USDC **or** Solana USDC |
| Facilitator | Coinbase Developer Platform (EdDSA JWT auth, settles on both chains) |
| Base anchor | Base mainnet — Merkle root as EIP-1559 calldata (`web3.py`) |
| Solana anchor | Solana mainnet — Memo program (`solders` + raw RPC) |
| Officer signing | EIP-712 typed data (secp256k1, `eth-account`) **or** Ed25519 over domain-prefixed bytes (`solders.signature`) — auto-detected |
| Officer authorization | Allowlist registry in DynamoDB; admin-gated `/v1/admin/officers` enrollment with HMAC bearer auth |
| Idempotency | `Idempotency-Key` header → 24h-TTL request cache; replays return `Idempotent-Replayed: true` without re-charging x402 |
| Evidence vault | S3 with Object Lock COMPLIANCE mode, 7-year retention; DynamoDB stores hash + S3 URI only |
| API | FastAPI + AWS Lambda (Mangum) |
| AI | Amazon Bedrock — Claude Haiku 4.5 |
| Compliance data | MRU SENTINEL, Orbis (live on Base); Scorechain / SAS / SOLANA-AML-Checker (registered, pending) |
| Discovery | `gavel_toolkit` — chain-agnostic JSON registry, CAIP-2 networks |

---

## Security Posture

Counsel was built with institutional review in mind. The following are **shipped today**:

- **Domain-separated officer signatures.** EVM officers sign EIP-712 typed data with `domain={Counsel, v1, chainId 8453}` and `Approval={session_id, merkle_root, decision}`. Solana officers sign Ed25519 over `Counsel/v1\nchain=solana\nsession_id=...\nmerkle_root=...\ndecision=...`. Kills cross-session replay, cross-app phishing, and decision-flip attacks.
- **Officer allowlist registry.** A valid signature is necessary but not sufficient — recovered signers must be enrolled in the per-tenant allowlist. Unauthorized signers receive 403 even with mathematically valid signatures.
- **Admin-gated registry mutations.** `/v1/admin/officers` POST/DELETE/GET require a bearer token verified with `hmac.compare_digest`. Fail-closed: missing `ADMIN_API_KEY` returns 503.
- **WORM evidence vault.** Raw provider responses + Bedrock outputs are written to S3 with Object Lock COMPLIANCE mode and 7-year retention. DynamoDB stores only the SHA-256 hash + `s3://` URI + version-id + ETag. An operator with table-write perms cannot rewrite the underlying evidence — the locked S3 object is immutable for the retention window even to root.
- **Atomic officer claim.** `record_approval` uses DynamoDB `ConditionExpression` "status = pending" so two concurrent signers cannot both succeed; the loser receives a clean 409.
- **Idempotency.** `Idempotency-Key` header + payload-hash binding. Replays return cached responses without re-charging x402 or re-running outbound compliance calls. Different payload + same key returns 409.
- **Dependency lockfile.** `src/requirements.txt` is autogenerated from `requirements.in` via `uv pip compile`; every transitive package is pinned. Supply-chain drift is caught at compile time.
- **Scoped Bedrock IAM.** Lambda execution role can invoke only the Claude Haiku family of foundation models + cross-region inference profiles in this account, not the entire Bedrock service.
- **AWS Secrets Manager for runtime secrets.** Treasury wallet keys (EVM + Solana), CDP API key secret, and the admin bearer token live in a single composite secret (`counsel/runtime`). Lambda env vars carry only the secret ARN; values are fetched at cold-start via `services/secrets.py` and cached in process memory. Lambda IAM is scoped to `secretsmanager:GetSecretValue` on that specific ARN; CloudTrail logs every access. Secrets can be rotated via `aws secretsmanager update-secret` without a stack redeploy.

The following are **planned / production-track**:

| Item | Status | Approach |
|------|--------|----------|
| Customer-managed KMS key (CMK) for the secret + S3 vault | Roadmap | Replace AWS-managed encryption with a customer-controlled CMK; key policy separates Lambda read role from operator-write role. |
| Multi-sig treasury (Safe on Base, Squads on Solana) | Roadmap | Treasury becomes a 2-of-3 multi-sig with daily spend caps and 24h timelock for treasury changes. Anchor txs become signed proposals. |
| WAF + per-tenant rate limiting | Roadmap | API Gateway in front of Lambda with WAF rate-based rules; per-customer usage plans gated by API key. |
| Lambda in VPC with PrivateLink endpoints | Roadmap | Bedrock + DynamoDB + S3 via VPC endpoints; outbound HTTPS via NAT-pinned IPs for IP allowlisting on partner APIs. |
| Customer authentication on `/v1/diligence` | Roadmap | Per-tenant API keys identifying the requesting institution; the `originator` field on travel-rule calls reflects the actual customer rather than `ORIGINATOR_NAME`. |
| Anomaly detection | Roadmap | CloudWatch alarms on REJECT spike, unusual jurisdictions, officer signing volume; SIEM integration. |
| Right-to-Erasure path | Roadmap | DynamoDB TTL on session rows; PII-anonymization endpoint that nulls personal fields while preserving hash + signer. |

The architecture (stateless Lambda, hash-only DynamoDB, WORM S3, allowlisted officers, multi-chain anchoring) is designed so that each roadmap item drops in without rewriting core logic.

---

## Why x402 + Base + Solana

x402 turns compliance APIs into pay-per-query infrastructure. Sub-cent micropayments make it economical to call multiple providers per decision — impossible with traditional rails (Stripe, ACH, wire). The Coinbase facilitator settles on-chain with no accounts, no invoices, no shared API keys.

Base mainnet provides cheap calldata (~$0.0006 per anchor) for production-volume per-decision anchoring. Solana adds a second independent L1 with sub-second finality and ~$0.0008 Memo costs, doubling the integrity guarantee. CAIP-2 chain identifiers throughout the registry make multi-chain composability native, not bolted-on.

Counsel is genuinely chain-neutral at every layer that matters for institutional integrity: the client picks the payment chain, the officer picks the signature scheme, and the evidence chain anchors to both. The compliance providers themselves are registered cross-chain so that as the Solana x402 ecosystem matures, no Counsel code change is needed to route real calls there.

---

## Repository Structure

```
gavel/
├── src/
│   ├── app.py                  # FastAPI + x402 middleware + Mangum
│   ├── routes/
│   │   ├── diligence.py        # POST /v1/diligence
│   │   ├── officer.py          # GET/POST /v1/officer/{id}
│   │   └── stub.py             # Self-hosted Orbis stubs (demo determinism)
│   ├── services/
│   │   ├── bazaar_client.py    # Outbound x402 compliance calls
│   │   ├── bedrock_client.py   # Claude synthesis
│   │   ├── cdp_auth.py         # CDP EdDSA JWT auth
│   │   └── evidence_store.py   # DynamoDB + Merkle root + Base + Solana anchor
│   └── models.py
├── gavel_toolkit/
│   ├── discovery.py            # resolve() / resolve_and_call()
│   ├── providers/              # JSON provider registry (Base + Solana)
│   └── README.md
├── scripts/
│   └── test_solana_anchor.py   # Standalone Memo program smoke test
├── template.yaml               # AWS SAM
└── test_e2e.py                 # Live end-to-end test (pays real USDC)
```

---

## Built solo at EasyA Consensus 2026, Miami.
