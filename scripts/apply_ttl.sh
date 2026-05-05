#!/usr/bin/env bash
# Enable DynamoDB TTL on the evidence table — auto-purges session,
# erasure, and idempotency rows after their `ttl_at` UNIX timestamp.
#
# Default retention is 7 years (matches FATF Recommendation 11 / FinCEN
# BSA / EU AMLD record-keeping windows). Override per-row by setting
# RETENTION_SECONDS on the Lambda env, or per-record by writing a
# different ttl_at attribute.
#
# Run after deploy. AWS::Serverless::SimpleTable does not expose
# TimeToLiveSpecification directly; applying it via the SDK keeps the
# existing physical table intact (no replacement).
set -euo pipefail

TABLE="${TABLE:-$(aws dynamodb list-tables --query 'TableNames[?contains(@,`vidence`)]' --output text)}"

aws dynamodb update-time-to-live \
  --table-name "$TABLE" \
  --time-to-live-specification "Enabled=true, AttributeName=ttl_at" \
  --output json

echo
echo "TTL enabled on $TABLE — rows with ttl_at < now will be auto-deleted."
echo "Verify: aws dynamodb describe-time-to-live --table-name $TABLE"
