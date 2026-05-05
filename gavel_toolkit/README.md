# gavel_toolkit

Reusable primitives for building institutional AI agents with x402 payments on Base.

## What it is

`gavel_toolkit` is the provider-agnostic layer extracted from [Counsel](../README.md). It gives you:

- **Provider registry** — JSON-defined compliance service providers, each with intent, URL, price, and schema
- **`resolve(intent)`** — find all providers matching a compliance intent
- **`resolve_and_call(intent, payload, payer_key)`** — route, pay via x402, and return results in one call

## Quick start

```python
from gavel_toolkit.discovery import resolve, resolve_and_call

# See what intents are available
from gavel_toolkit.discovery import list_intents
print(list_intents())
# ['embedded_finance_compliance', 'trade_finance_risk', 'travel_rule_compliance']

# Find providers for an intent
providers = resolve("travel_rule_compliance")
# [{'id': 'mru_travel_rule', 'price_usd': 0.005, ...}]

# Route and pay in one call
result = resolve_and_call(
    intent="travel_rule_compliance",
    payload={
        "originator": {"address": "0x...", "name": "Acme Corp", "country_code": "US"},
        "beneficiary": {"address": "0x...", "name": "Vendor", "country_code": "AE"},
        "amount_usd": 50000,
        "purpose": "trade settlement",
    },
    payer_key="0x<your-private-key>",
)
print(result["recommendation"])  # "PROCEED"
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

| Provider | Intent | Price |
|----------|--------|-------|
| MRU SENTINEL Travel Rule | `travel_rule_compliance` | $0.005 |
| Orbis Trade Finance Risk | `trade_finance_risk` | $0.005 |
| Orbis Embedded Finance Score | `embedded_finance_compliance` | $0.005 |

## Fork and customize

This toolkit is designed to be forked. Replace the providers with your own (Refinitiv, Bridger, Dow Jones, internal lists). The agent declares intent; the registry routes and pays.

```
git clone https://github.com/hypeprinter007-stack/gavel.git
cd gavel/gavel_toolkit
# Add your providers to providers/
# Use resolve_and_call() in your agent
```
