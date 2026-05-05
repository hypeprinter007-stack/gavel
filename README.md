# Counsel — Decision Integrity Layer for Institutional AI Agents

**EasyA Consensus 2026 · Miami · Built on Base**

Counsel is a compliance infrastructure layer that lets institutional AI agents make high-stakes vendor decisions with a tamper-evident, on-chain audit trail — paid for and anchored via x402 on Base.

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
Client Agent  ──$0.05 USDC x402──►  Counsel API (AWS Lambda)
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
                          Merkle root anchored to Base (calldata tx)
                                          │
                          Officer signs Merkle root with their wallet
                                          │
                               Signer address recovered on-chain
```

1. **Client pays $0.05 USDC** via x402 on Base to call `/v1/diligence`
2. **Counsel pays 3 compliance APIs** in parallel ($0.005 each) using x402
3. **Claude Haiku synthesizes** the evidence into a structured recommendation
4. **Merkle root** is computed over all evidence + synthesis hashes — tamper-evident
5. **Merkle root is posted to Base** as calldata — immutable, public, timestamped on-chain
6. **Compliance officer signs the Merkle root** with their wallet — `signer_address` cryptographically recovered server-side

Nobody can claim the AI was fed different data. Nobody can forge the approval. The full chain is verifiable on-chain.

---

## Live Demo

**API:** `https://ki55wa4a21.execute-api.us-east-1.amazonaws.com`

```bash
pip install requests eth-account x402
export CLIENT_PRIVATE_KEY=0x...
python test_e2e.py
```

**Sample response:**

```json
{
  "session_id": "a2d22579-a486-46fa-ad8e-a30efc653414",
  "vendor": "Northstar Crypto Capital",
  "merkle_root": "0c57ea45f8ea4a4469c2486e4e9c16bd55167ecf82b8da0493149a48abc58d5d",
  "anchor_tx": "0xfbcf13d3535b4f81904f1de9c1e7fdbb533b9e3cd6d4f2e8bd78e22eb94b838a",
  "basescan_url": "https://basescan.org/tx/0xfbcf13d3535b4f81904f1de9c1e7fdbb533b9e3cd6d4f2e8bd78e22eb94b838a",
  "synthesis": {
    "risk_level": "medium",
    "recommendation": "ENHANCED_DILIGENCE",
    "summary": "Travel Rule compliance verified. UAE jurisdiction monitored. Recommend enhanced due diligence before approval.",
    "key_findings": [...]
  },
  "officer_url": "/v1/officer/a2d22579-a486-46fa-ad8e-a30efc653414"
}
```

**Officer sign response:**

```json
{
  "decision": "APPROVED",
  "signer_address": "0xbe5b7f10E26E301e0639a2cCE2b8Ea73207884F1",
  "merkle_root": "0c57ea45f8ea4a4469c2486e4e9c16bd55167ecf82b8da0493149a48abc58d5d",
  "anchor_tx": "0xfbcf13d3535b4f81904f1de9c1e7fdbb533b9e3cd6d4f2e8bd78e22eb94b838a",
  "basescan_url": "https://basescan.org/tx/0xfbcf13d3535b4f81904f1de9c1e7fdbb533b9e3cd6d4f2e8bd78e22eb94b838a",
  "status": "recorded"
}
```

---

## API

### `POST /v1/diligence` — x402 gated ($0.05 USDC)

```json
{
  "vendor_name": "Northstar Crypto Capital",
  "vendor_country": "AE",
  "vendor_wallet": "0x...",
  "amount_usd": 50000
}
```

Returns: `session_id`, `evidence`, `synthesis`, `merkle_root`, `anchor_tx`, `basescan_url`, `officer_url`

### `GET /v1/officer/{session_id}`

Returns the officer review view: session metadata, `merkle_root`, `anchor_tx`, `basescan_url`, `sign_url`.

### `POST /v1/officer/{session_id}/sign`

The officer signs the `merkle_root` with their wallet (EIP-191 `personal_sign`) and posts the signature. Counsel recovers the signer address and stores it alongside the decision.

```json
{
  "decision": "APPROVED",
  "signature": "0x<personal_sign(merkle_root)>",
  "notes": "Travel rule clear. Proceed with enhanced monitoring."
}
```

Returns: `decision`, `signer_address`, `merkle_root`, `anchor_tx`, `basescan_url`

---

## The Integrity Chain

```
evidence_hash_1 ─┐
evidence_hash_2 ─┼─► merkle_root ──► Base tx (calldata) ──► officer.sign(merkle_root)
synthesis_hash  ─┘                        │                        │
                                    basescan.org               signer_address
                                    (immutable)             (cryptographically bound)
```

Every compliance decision has:
- A **content hash** of every data source the AI touched
- An **on-chain timestamp** (Base block) proving when it happened
- A **wallet signature** from the approving officer tied to that exact evidence set

---

## gavel_toolkit

`gavel_toolkit` is the provider-agnostic discovery layer. Fork it and plug in your own compliance providers — Refinitiv, Bridger, Dow Jones, internal lists.

```python
from gavel_toolkit.discovery import resolve, resolve_and_call

# Find all providers for an intent
providers = resolve("travel_rule_compliance")

# Route, pay x402, and get results in one call
result = resolve_and_call(
    intent="travel_rule_compliance",
    payload={"originator": {...}, "beneficiary": {...}, "amount_usd": 50000},
    payer_key="0x<private-key>",
)
print(result["recommendation"])  # "PROCEED"
```

Drop a JSON file in `gavel_toolkit/providers/` to register a new provider — no Python changes needed:

```json
{
  "id": "my_kyc_provider",
  "intent": "kyc_verification",
  "url": "https://my-kyc-api.com/verify",
  "method": "POST",
  "price_usd": 0.01,
  "network": "eip155:8453"
}
```

See [gavel_toolkit/README.md](gavel_toolkit/README.md) for full documentation.

---

## Tech Stack

| Layer | Tech |
|-------|------|
| Payment | [x402](https://github.com/coinbase/x402) — HTTP 402 on Base USDC |
| Facilitator | Coinbase Developer Platform |
| On-chain anchor | Base mainnet — Merkle root as calldata |
| API | FastAPI + AWS Lambda (Mangum) |
| AI | Amazon Bedrock — Claude Haiku 4.5 |
| Evidence store | DynamoDB |
| Officer signing | EIP-191 `personal_sign` — signer address recovered server-side |
| Compliance data | MRU SENTINEL (travel rule), Orbis (trade/embedded finance) |
| Discovery | `gavel_toolkit` — JSON registry, `resolve()` / `resolve_and_call()` |

---

## Why x402

x402 turns compliance APIs into pay-per-query infrastructure. Instead of annual license agreements and manual integrations, any agent can call any provider with a single HTTP request and a Base USDC micropayment. The facilitator settles on-chain — no accounts, no invoices, no API keys shared.

This is the payment rail that makes composable compliance infrastructure possible.

---

## Repository Structure

```
gavel/
├── src/
│   ├── app.py                  # FastAPI + x402 middleware + Mangum
│   ├── routes/
│   │   ├── diligence.py        # POST /v1/diligence
│   │   └── officer.py          # GET/POST /v1/officer/{id}
│   ├── services/
│   │   ├── bazaar_client.py    # Outbound x402 compliance calls
│   │   ├── bedrock_client.py   # Claude synthesis
│   │   ├── cdp_auth.py         # CDP EdDSA JWT auth
│   │   └── evidence_store.py   # DynamoDB + Merkle root + Base anchor
│   └── models.py
├── gavel_toolkit/
│   ├── discovery.py            # resolve() / resolve_and_call()
│   ├── providers/              # JSON provider registry
│   └── README.md
├── template.yaml               # AWS SAM
└── test_e2e.py                 # Live end-to-end test (pays real USDC)
```

---

## Built solo at EasyA Consensus 2026, Miami.
