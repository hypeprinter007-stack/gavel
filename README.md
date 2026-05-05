# Counsel — Decision Integrity Layer for Institutional AI Agents

**EasyA Consensus 2026 · Miami · Built on Base + Solana**

Counsel is a compliance infrastructure layer that lets institutional AI agents make high-stakes vendor decisions with a tamper-evident, dual-chain audit trail — paid for via x402 on Base and anchored on both Base and Solana mainnet.

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
                            Merkle root over evidence + synthesis
                                          │
                          ┌───────────────┴───────────────┐
                          ▼                               ▼
                  Base mainnet                     Solana mainnet
                 (calldata tx)                    (Memo program)
                          │                               │
                          └───────────────┬───────────────┘
                                          │
                          Officer signs Merkle root with their wallet
                                          │
                                Signer address recovered
                                  (EIP-191, secp256k1)
```

1. **Client pays $0.05 USDC** via x402 on Base to call `/v1/diligence`
2. **Counsel pays compliance APIs** in parallel via x402
3. **Claude Haiku synthesizes** the evidence into a structured recommendation
4. **Merkle root** is computed over all evidence + synthesis hashes
5. **The same Merkle root is anchored to Base AND Solana** in parallel — calldata tx on Base, Memo program tx on Solana. Two independent L1s, one decision.
6. **Compliance officer signs the Merkle root** with their wallet — `signer_address` cryptographically recovered server-side via EIP-191

Forging an approval requires breaking SHA256 *and* the officer's secp256k1 key. Reverting the audit trail requires reorging two independent chains.

---

## Live Demo

**API:** `https://ki55wa4a21.execute-api.us-east-1.amazonaws.com`

```bash
pip install requests eth-account x402
export CLIENT_PRIVATE_KEY=0x...
export OFFICER_PRIVATE_KEY=0x...
python test_e2e.py
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

### `POST /v1/diligence` — x402 gated ($0.05 USDC)

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

The officer signs the `merkle_root` with their wallet (EIP-191 `personal_sign`). Counsel recovers the signer address server-side and stores it alongside the decision.

```json
{
  "decision": "APPROVED",
  "signature": "0x<personal_sign(merkle_root)>",
  "notes": "Travel rule clear. Proceed with enhanced monitoring."
}
```

Returns: `decision`, `signer_address`, `merkle_root`, both `anchors`

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
# [{"id": "solana_aml_checker",   "network": "solana:mainnet", "price_usd": 0.001},
#  {"id": "scorechain_solana_aml","network": "solana:mainnet", "price_usd": 0.01}]
```

**Built-in providers:**

| Provider | Intent | Network | Price |
|----------|--------|---------|-------|
| MRU SENTINEL Travel Rule | `travel_rule_compliance` | `eip155:8453` | $0.005 |
| Orbis Trade Finance Risk | `trade_finance_risk` | `eip155:8453` | $0.005 |
| Orbis Embedded Finance Score | `embedded_finance_compliance` | `eip155:8453` | $0.005 |
| Scorechain Solana AML | `wallet_screening` | `solana:mainnet` | $0.01 |
| Solana Attestation Service | `kyc_attestation` | `solana:mainnet` | $0.005 |
| SOLANA AML Checker | `wallet_screening` | `solana:mainnet` | $0.001 |

See [gavel_toolkit/README.md](gavel_toolkit/README.md) for the full registry schema.

---

## Tech Stack

| Layer | Tech |
|-------|------|
| Payment rail | [x402](https://github.com/coinbase/x402) — HTTP 402 on Base USDC |
| Facilitator | Coinbase Developer Platform (EdDSA JWT auth) |
| Base anchor | Base mainnet — Merkle root as EIP-1559 calldata (`web3.py`) |
| Solana anchor | Solana mainnet — Memo program (`solders` + raw RPC) |
| Officer signing | EIP-191 `personal_sign`; signer recovered with `eth-account` |
| API | FastAPI + AWS Lambda (Mangum) |
| AI | Amazon Bedrock — Claude Haiku 4.5 |
| Evidence store | DynamoDB single-table |
| Compliance data | MRU SENTINEL, Orbis (live), Scorechain / SAS / SOLANA-AML-Checker (registered, pending) |
| Discovery | `gavel_toolkit` — chain-agnostic JSON registry, CAIP-2 networks |

---

## Why x402 + Base + Solana

x402 turns compliance APIs into pay-per-query infrastructure. Sub-cent micropayments make it economical to call multiple providers per decision — impossible with traditional rails (Stripe, ACH, wire). The Coinbase facilitator settles on-chain with no accounts, no invoices, no shared API keys.

Base mainnet provides cheap calldata (~$0.0006 per anchor) for production-volume per-decision anchoring. Solana adds a second independent L1 with sub-second finality and ~$0.0008 Memo costs, doubling the integrity guarantee. CAIP-2 chain identifiers throughout the registry make multi-chain composability native, not bolted-on.

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
