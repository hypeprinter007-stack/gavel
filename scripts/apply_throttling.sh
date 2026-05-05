#!/usr/bin/env bash
# Apply per-stage throttling to the Counsel HTTP API.
#
# Run after deploy. The throttling is at the AWS edge — requests in
# excess of the rate limit are rejected with 429 before reaching
# Lambda, which is the goal: we don't want abuse paying x402 and
# triggering Bedrock + outbound x402 calls.
#
# 100 RPS sustained / 50 in-flight burst is sized for institutional
# usage patterns: a real customer making one diligence call every
# 10s would never hit the limit, but a script trying to spend-amplify
# at scale gets cut off.
set -euo pipefail

API_ID="${API_ID:-ki55wa4a21}"
STAGE='$default'
BURST="${BURST:-50}"
RATE="${RATE:-100}"

aws apigatewayv2 update-stage \
  --api-id "$API_ID" \
  --stage-name "$STAGE" \
  --default-route-settings "ThrottlingBurstLimit=$BURST,ThrottlingRateLimit=$RATE" \
  --query '{StageName: StageName, DefaultRouteSettings: DefaultRouteSettings}' \
  --output json

echo
echo "Throttling applied: rate=$RATE rps, burst=$BURST in-flight"
echo "Verify: aws apigatewayv2 get-stage --api-id $API_ID --stage-name '\$default'"
