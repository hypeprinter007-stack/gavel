"""Customer registry — per-tenant API keys for /v1/diligence callers.

Authenticates the *requesting institution*, not just whoever has a
wallet. Required so the travel-rule originator field reflects the
real customer (e.g. "Acme Bank, US") instead of a generic
"Counsel Demo Client", and so per-tenant officer registries can be
scoped properly.

API keys are generated server-side at registration; the raw key is
returned exactly ONCE and never retrievable again. The DynamoDB row
stores only the SHA-256 hash of the key, so a database read does
not yield credentials.
"""
from __future__ import annotations

import hashlib
import os
import secrets as _stdlib_secrets
import time

import boto3

TABLE = os.getenv("EVIDENCE_TABLE", "counsel-evidence")

_db = None


def _table():
    global _db
    if _db is None:
        _db = boto3.resource(
            "dynamodb",
            region_name=os.getenv("BEDROCK_REGION", "us-east-1"),
        ).Table(TABLE)
    return _db


def _hash(api_key: str) -> str:
    return hashlib.sha256(api_key.encode()).hexdigest()


def _slug(name: str) -> str:
    return "".join(c.lower() if c.isalnum() else "_" for c in name).strip("_")


def register_customer(
    customer_name: str,
    customer_country: str,
    tenant: str | None = None,
) -> dict:
    """Generate a new API key and register the customer. Returns the
    raw key ONCE plus the persisted record minus the key itself."""
    api_key = "ck_live_" + _stdlib_secrets.token_urlsafe(32)
    kh = _hash(api_key)
    record = {
        "pk": f"customer#{kh}",
        "type": "customer",
        "key_hash": kh,
        "customer_name": customer_name,
        "customer_country": customer_country,
        "tenant": tenant or _slug(customer_name),
        "status": "active",
        "created_at": int(time.time()),
    }
    _table().put_item(Item=record)
    return {"api_key": api_key, "customer": record}


def lookup(api_key: str) -> dict | None:
    """Return the customer record if the key is active, else None."""
    if not api_key:
        return None
    kh = _hash(api_key)
    resp = _table().get_item(Key={"pk": f"customer#{kh}"})
    item = resp.get("Item")
    if not item or item.get("status") != "active":
        return None
    return item


def list_customers() -> list[dict]:
    resp = _table().scan(
        FilterExpression="#t = :t",
        ExpressionAttributeNames={"#t": "type"},
        ExpressionAttributeValues={":t": "customer"},
    )
    return resp.get("Items", [])


def revoke(key_hash: str) -> bool:
    """Mark a customer revoked by their key hash. Returns True if a row
    transitioned from active to revoked."""
    try:
        _table().update_item(
            Key={"pk": f"customer#{key_hash}"},
            UpdateExpression="SET #s = :s",
            ConditionExpression="attribute_exists(pk) AND #s = :a",
            ExpressionAttributeNames={"#s": "status"},
            ExpressionAttributeValues={":s": "revoked", ":a": "active"},
        )
        return True
    except Exception:
        return False
