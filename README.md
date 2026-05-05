# Counsel — Decision Integrity Layer for Institutional AI Agents

**EasyA Consensus 2026 · Miami · Built on Base**

Counsel is a compliance infrastructure layer that lets institutional AI agents make high-stakes vendor decisions with a tamper-evident audit trail and x402 micropayments — all on Base.

---

## The Problem

AI agents are moving into institutional workflows: trade approvals, vendor onboarding, compliance screening. But there's no standard way to:

1. **Pay for compliance data** at query time (current: annual licenses, manual integrations)
2. **Prove** the AI saw what it claims to have seen before recommending APPROVE
3. **Give a compliance officer** a reviewable, signable record they can stand behind

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
                               Merkle root anchored to DynamoDB
                                          │
                               Officer review + sign endpoint
```

1. **Client pays $0.05 USDC** via x402 on Base to call `/v1/diligence`
2. **Counsel pays 3 compliance APIs** in parallel ($0.005 each) using x402
3. **Claude Haiku synthesizes** the evidence into a structured recommendation
4. **Merkle root** anchors the entire evidence set — tamper-evident, on-chain verifiable
5. **Compliance officer** reviews and signs via `/v1/officer/{id}/sign`

---

## Live Demo

**API:** `https://ki55wa4a21.execute-api.us-east-1.amazonaws.com`

```bash
# Install
pip install requests eth-account x402

# Set your Base wallet key
export CLIENT_PRIVATE_KEY=0x...

python test_e2e.py
```

**Sample response:**

```json
{
  "session_id": "6caf7b97-0614-4a54-87be-991538a55385",
  "vendor": "Northstar Crypto Capital",
  "merkle_root": "d8421ad7dc077db47bf3642912cd3520fffa1cd740dfb86054c643d07c92a85e",
  "synthesis": {
    "risk_level": "medium",
    "recommendation": "ENHANCED_DILIGENCE",
    "summary": "Travel Rule compliance verified. UAE jurisdiction monitored, not high-risk. Recommend enhanced due diligence before approval.",
    "key_findings": [...]
  },
  "officer_url": "/v1/officer/6caf7b97-0614-4a54-87be-991538a55385"
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

Returns: `session_id`, `evidence`, `synthesis`, `merkle_root`, `synthesis_hash`, `officer_url`

### `GET /v1/officer/{session_id}`

Returns the officer review view with session metadata and sign URL.

### `POST /v1/officer/{session_id}/sign`

```json
{
  "decision": "APPROVED",
  "signature": "0x...",
  "notes": "Reviewed. Travel rule clear. Proceed with enhanced monitoring."
}
```

---

## gavel_toolkit

`gavel_toolkit` is the provider-agnostic discovery layer extracted from Counsel. Any developer can fork it and plug in their own compliance providers.

```python
from gavel_toolkit.discovery import resolve, resolve_and_call

# Find all providers for an intent
providers = resolve("travel_rule_compliance")

# Route, pay, and get results in one call
result = resolve_and_call(
    intent="travel_rule_compliance",
    payload={"originator": {...}, "beneficiary": {...}, "amount_usd": 50000},
    payer_key="0x<private-key>",
)
print(result["recommendation"])  # "PROCEED"
```

Add your own provider by dropping a JSON file in `gavel_toolkit/providers/`:

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
| API | FastAPI + AWS Lambda (Mangum) |
| AI | Amazon Bedrock — Claude Haiku 4.5 |
| Evidence store | DynamoDB |
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
│   ├── app.py              # FastAPI + x402 middleware + Mangum
│   ├── routes/
│   │   ├── diligence.py    # POST /v1/diligence
│   │   └── officer.py      # GET/POST /v1/officer/{id}
│   ├── services/
│   │   ├── bazaar_client.py    # Outbound x402 compliance calls
│   │   ├── bedrock_client.py   # Claude synthesis
│   │   ├── cdp_auth.py         # CDP EdDSA JWT auth
│   │   └── evidence_store.py   # DynamoDB + Merkle root
│   └── models.py
├── gavel_toolkit/
│   ├── discovery.py        # resolve() / resolve_and_call()
│   ├── providers/          # JSON provider registry
│   └── README.md
├── template.yaml           # AWS SAM
└── test_e2e.py             # Live end-to-end test
```

---

## Built solo at EasyA Consensus 2026, Miami.
