"""Idempotency cache for /v1/diligence.

Customers send Idempotency-Key on the request; if Counsel has seen
that key before with the same payload it returns the cached
response. Different payload + same key returns 409. Unseen key falls
through to normal x402-gated processing.

Cache lives in the existing DynamoDB table (separate pk namespace)
with a TTL attribute. Storing the payload hash and a small response
body keeps rows under DynamoDB's 400KB item ceiling.
"""
from __future__ import annotations

import hashlib
import json
import os
import time

import boto3

TABLE = os.getenv("EVIDENCE_TABLE", "counsel-evidence")
IDEMPOTENCY_TTL_SECONDS = 60 * 60 * 24  # 24h

_db = None


def _table():
    global _db
    if _db is None:
        _db = boto3.resource(
            "dynamodb",
            region_name=os.getenv("BEDROCK_REGION", "us-east-1"),
        ).Table(TABLE)
    return _db


def _pk(key: str) -> str:
    return f"idem#{key}"


def request_hash(payload_bytes: bytes) -> str:
    return hashlib.sha256(payload_bytes).hexdigest()


def lookup(key: str) -> dict | None:
    """Returns the cached record or None if unseen."""
    resp = _table().get_item(Key={"pk": _pk(key)})
    item = resp.get("Item")
    if not item:
        return None
    if int(time.time()) > int(item.get("expires_at", 0)):
        return None
    return item


def store(key: str, request_h: str, status_code: int, response_body: dict) -> None:
    """Cache a response under the key. Best-effort — if the row exceeds
    DynamoDB's item size limit we silently fail, since idempotency is
    an optimization not a correctness primitive."""
    try:
        _table().put_item(Item={
            "pk": _pk(key),
            "type": "idempotency",
            "request_hash": request_h,
            "status_code": status_code,
            "response_body": json.dumps(response_body),
            "stored_at": int(time.time()),
            "expires_at": int(time.time()) + IDEMPOTENCY_TTL_SECONDS,
        })
    except Exception:
        # Item too big or transient DynamoDB error — don't fail the
        # request just because we couldn't cache.
        pass
