# gavel_toolkit

Reusable primitives for building institutional AI agents with x402 payments on Base.

## What it is

`gavel_toolkit` is the provider-agnostic layer extracted from [Counsel](../README.md). It gives you:

- **Provider registry** — JSON-defined compliance service providers, each with intent, URL, price, and schema
- **`resolve(intent)`** — find all providers matching a compliance intent
- **`resolve_and_call(intent, payload, payer_key)`** — route, pay via x402, and return results in one call

## Quick start

```python
from gavel_toolkit.discovery import resolve, resolve_and_call, list_intents

print(list_intents())
# ['embedded_finance_compliance', 'kyc_attestation', 'trade_finance_risk',
#  'travel_rule_compliance', 'wallet_screening']

# Find providers for an intent (cross-chain, sorted by price)
providers = resolve("wallet_screening")
# [{'id': 'solana_aml_checker', 'network': 'solana:5eykt4Us...', 'price_usd': 0.001, ...},
#  {'id': 'scorechain_solana_aml', 'network': 'solana:5eykt4Us...', 'price_usd': 0.01, ...}]

# Route, pay, and call in one shot. Pass keys for whichever chain(s) you can
# settle on; the dispatcher skips providers it can't pay.
result = resolve_and_call(
    intent="travel_rule_compliance",
    payload={
        "originator": {"address": "0x...", "name": "Customer", "country_code": "US"},
        "beneficiary": {"address": "0x...", "name": "Vendor", "country_code": "AE"},
        "amount_usd": 50000,
        "purpose": "trade settlement",
    },
    evm_payer_key="0x<hex private key>",     # for eip155:* providers
    solana_payer_key="<base58 keypair>",     # for solana:* providers
)
print(result["recommendation"])  # "PROCEED"
print(result["_provider"], result["_network"])  # routed provider + chain
```

## Adding your own providers

Create a JSON file in `gavel_toolkit/providers/`:

```json
{
  "id": "my_kyc_provider",
  "name": "My KYC API",
  "intent": "kyc_verification",
  "url": "https://my-kyc-api.com/verify",
  "method": "POST",
  "price_usd": 0.01,
  "network": "eip155:8453",
  "description": "KYC verification for retail customers",
  "tags": ["kyc", "identity", "retail"]
}
```

That's it. `resolve("kyc_verification")` will include your provider automatically.

## Built-in providers

The registry uses CAIP-2 chain identifiers, so the same `resolve(intent)` call returns providers across multiple chains. Counsel routes payment to the right network automatically.

**Base (`eip155:8453`)** — live integrations

| Provider | Intent | Price |
|----------|--------|-------|
| MRU SENTINEL Travel Rule | `travel_rule_compliance` | $0.005 |
| Orbis Trade Finance Risk | `trade_finance_risk` | $0.005 |
| Orbis Embedded Finance Score | `embedded_finance_compliance` | $0.005 |

**Solana (`solana:5eykt4Us...`)** — registered, integration pending

| Provider | Intent | Price |
|----------|--------|-------|
| Scorechain Solana AML | `wallet_screening` | $0.01 |
| Solana Attestation Service | `kyc_attestation` | $0.005 |
| SOLANA AML Checker | `wallet_screening` | $0.001 |

**Routed via pay.sh** — Solana Foundation + Google Cloud's x402 marketplace

| Provider | Intent | Price | Routing |
|----------|--------|-------|---------|
| Helius Solana RPC | `solana_rpc` | $0.0001 | `via: pay.sh` |

Provider entries can declare `"via": "pay.sh"` to indicate routing through the [pay.sh](https://github.com/solana-foundation/pay) proxy launched by the Solana Foundation and Google Cloud. The x402 protocol is identical (same SVM scheme, same CDP facilitator), so adding pay.sh-routed dispatch is a small extension on top of `_build_session`. The flag is honored by `resolve_and_call` today (skips with an explanatory message); native dispatch lands in the next iteration.

```python
from gavel_toolkit.discovery import resolve
resolve("wallet_screening")
# [{"id": "solana_aml_checker", "network": "solana:5eykt4Us...", ...},
#  {"id": "scorechain_solana_aml", "network": "solana:5eykt4Us...", ...}]
```

## Fork and customize

This toolkit is designed to be forked. Replace the providers with your own (Refinitiv, Bridger, Dow Jones, internal lists). The agent declares intent; the registry routes and pays.

```
git clone https://github.com/hypeprinter007-stack/gavel.git
cd gavel/gavel_toolkit
# Add your providers to providers/
# Use resolve_and_call() in your agent
```
