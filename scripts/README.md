# Counsel — operational scripts

Five scripts: three one-shot setup, two on-demand smoke tests. Each is
idempotent or read-only; run any of them more than once safely.

## Setup (run once after first deploy)

### `create_treasury_usdc_ata.py`
Creates the Solana treasury's USDC Associated Token Account so x402-SVM
inbound payments don't fail simulation with `InvalidAccountData`. Pays
~0.002 SOL rent from the treasury wallet's existing SOL balance.

```bash
python scripts/create_treasury_usdc_ata.py
```

Idempotent — checks for existing ATA before creating. Required only
once per treasury wallet.

### `apply_throttling.sh`
Applies 100 RPS sustained / 50 in-flight burst rate limits to the API
Gateway HTTP API stage (`$default`). SAM's `AWS::Serverless::HttpApi`
doesn't propagate `DefaultRouteSettings` cleanly, so we apply via
`apigatewayv2 update-stage` post-deploy. Run after every CFN deploy
that recreates the API.

```bash
bash scripts/apply_throttling.sh
# Override: BURST=100 RATE=200 bash scripts/apply_throttling.sh
```

### `apply_ttl.sh`
Enables DynamoDB TTL on the evidence table using the `ttl_at`
attribute. Auto-purges session and erasure rows after their 7-year AML
retention window expires. Run once after the evidence table is
created.

```bash
bash scripts/apply_ttl.sh
```

## Smoke tests (on demand)

### `test_solana_anchor.py`
Standalone roundtrip of the Solana Memo-program anchor used by
`evidence_store.anchor_to_solana()`. Posts a synthetic merkle_root
("deadbeef" × 8) as a Memo tx and prints the Solscan link. Useful for
verifying Solana RPC connectivity + treasury wallet balance before a
demo.

```bash
python scripts/test_solana_anchor.py
# → Signature: ...
# → Solscan:   https://solscan.io/tx/...
```

### `test_idempotency.py`
Demonstrates the `Idempotency-Key` middleware: 1st call pays + runs
diligence (~17s), 2nd call with same key returns cached response in
~100ms with `Idempotent-Replayed: true` header, 3rd call with same key
+ different payload returns 409.

```bash
python scripts/test_idempotency.py
```

## Prerequisites

All scripts read `.env` for credentials. See [`.env.example`](../.env.example)
for the variables required by each script.

| Script | Reads | Costs |
|---|---|---|
| `create_treasury_usdc_ata.py` | `SOLANA_TREASURY_KEY`, `SOLANA_RPC_URL` | ~0.002 SOL one-time |
| `apply_throttling.sh` | AWS CLI default profile | None |
| `apply_ttl.sh` | AWS CLI default profile | None |
| `test_solana_anchor.py` | `SOLANA_TREASURY_KEY`, `SOLANA_RPC_URL` | ~0.000005 SOL per run |
| `test_idempotency.py` | `CLIENT_PRIVATE_KEY` | $0.05 USDC per first call |
