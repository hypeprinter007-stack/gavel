"""Officer registry — institutional authorization layer.

Backed by the same DynamoDB table as evidence; uses a separate pk
namespace (`officer#{tenant}#{signer}`). Empty tenant defaults to
"counsel" so single-tenant demos work without changes.

Without this module the API verifies that *some* private key signed
the approval payload. With this module the API also verifies that
the recovered signer is on the tenant's allowlist — i.e. an
authorized compliance officer, not just any wallet on the internet.
"""
from __future__ import annotations

import os
import time

import boto3

TABLE = os.getenv("EVIDENCE_TABLE", "counsel-evidence")
DEFAULT_TENANT = os.getenv("DEFAULT_TENANT", "counsel")

_db = None


def _table():
    global _db
    if _db is None:
        _db = boto3.resource(
            "dynamodb",
            region_name=os.getenv("BEDROCK_REGION", "us-east-1"),
        ).Table(TABLE)
    return _db


def _pk(tenant: str, signer: str) -> str:
    return f"officer#{tenant}#{signer.lower() if signer.startswith('0x') else signer}"


def register_officer(signer: str, scheme: str, tenant: str = DEFAULT_TENANT, label: str = "") -> dict:
    """Add an authorized officer. Idempotent — re-registering refreshes label."""
    item = {
        "pk": _pk(tenant, signer),
        "type": "officer",
        "tenant": tenant,
        "signer": signer,
        "scheme": scheme,  # "eip712" or "ed25519"
        "label": label,
        "registered_at": int(time.time()),
    }
    _table().put_item(Item=item)
    return item


def revoke_officer(signer: str, tenant: str = DEFAULT_TENANT) -> bool:
    """Remove an officer from the allowlist. Returns True if a row was deleted."""
    resp = _table().delete_item(
        Key={"pk": _pk(tenant, signer)},
        ReturnValues="ALL_OLD",
    )
    return resp.get("Attributes") is not None


def is_authorized(signer: str, tenant: str = DEFAULT_TENANT) -> bool:
    resp = _table().get_item(Key={"pk": _pk(tenant, signer)})
    return "Item" in resp


def list_officers(tenant: str = DEFAULT_TENANT) -> list[dict]:
    """List authorized officers for a tenant. Uses Scan since pk is per-officer."""
    resp = _table().scan(
        FilterExpression="#t = :t AND tenant = :tn",
        ExpressionAttributeNames={"#t": "type"},
        ExpressionAttributeValues={":t": "officer", ":tn": tenant},
    )
    return resp.get("Items", [])
