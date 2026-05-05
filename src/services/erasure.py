"""GDPR Article 17 (Right to Erasure) handler.

Counsel's audit chain — Merkle root anchored on Base + Solana, evidence
locked in S3 with COMPLIANCE retention, officer signatures bound to
session_id — is intentionally tamper-evident. That conflicts with the
naive interpretation of "erase everything about the data subject."

The institutional answer (used by every regulated financial system):
- Anonymize identifying fields immediately on erasure request.
- Preserve hash-bound integrity records (Merkle root, signer, anchor
  txs) for the AML record-keeping window (FATF R.11 / FinCEN BSA /
  EU AMLD = ~5-7 years depending on jurisdiction).
- After retention expires, physical deletion happens automatically via
  DynamoDB TTL on session rows and S3 Object Lock retention expiry on
  evidence raw.
- Crypto-erasure of S3 objects pre-retention is a future option via a
  per-tenant KMS CMK whose deletion renders the encrypted blobs
  unreadable.

This module implements the immediate-anonymization step.
"""
from __future__ import annotations

import logging
import os
import time
import uuid

import boto3

from services import evidence_store

log = logging.getLogger("counsel.erasure")

TABLE = os.getenv("EVIDENCE_TABLE", "counsel-evidence")
_db = None

# Fields anonymized on erasure. Hashes, signatures, anchor txs, and
# vault references are PRESERVED — they're not personal data per GDPR
# Recital 26 (a SHA-256 hash is not identifiable without the source).
PII_FIELDS = {"vendor_name", "customer", "notes"}
ERASED_VALUE = "[ERASED]"


def _table():
    global _db
    if _db is None:
        _db = boto3.resource(
            "dynamodb",
            region_name=os.getenv("BEDROCK_REGION", "us-east-1"),
        ).Table(TABLE)
    return _db


def _find_sessions(by_session_id: str | None, by_vendor_name: str | None) -> list[str]:
    """Return matching session IDs."""
    if by_session_id:
        item = _table().get_item(Key={"pk": f"session#{by_session_id}"}).get("Item")
        return [by_session_id] if item else []
    if by_vendor_name:
        # Scan-filter — fine for hackathon; production would use a GSI on vendor_name.
        resp = _table().scan(
            FilterExpression="#t = :t AND vendor_name = :n",
            ExpressionAttributeNames={"#t": "type"},
            ExpressionAttributeValues={":t": "session_root", ":n": by_vendor_name},
        )
        return [item["pk"].split("#", 1)[1] for item in resp.get("Items", [])]
    return []


def _anonymize_session(session_id: str) -> dict:
    """Anonymize PII on the session_root + approval rows for one session.
    Returns a summary of what was nulled."""
    nulled: dict[str, list[str]] = {"session_root": [], "approval": []}

    # Session root
    sr_key = {"pk": f"session#{session_id}"}
    sr = _table().get_item(Key=sr_key).get("Item", {})
    sr_updates = []
    sr_values = {}
    sr_names = {}
    for i, field in enumerate(PII_FIELDS):
        if field in sr:
            sr_updates.append(f"#f{i} = :v{i}")
            sr_names[f"#f{i}"] = field
            sr_values[f":v{i}"] = ERASED_VALUE
            nulled["session_root"].append(field)
    if sr_updates:
        _table().update_item(
            Key=sr_key,
            UpdateExpression="SET " + ", ".join(sr_updates) + ", erased_at = :ts",
            ExpressionAttributeNames=sr_names,
            ExpressionAttributeValues={**sr_values, ":ts": int(time.time())},
        )

    # Approval (notes may carry PII)
    appr_key = {"pk": f"session#{session_id}#approval"}
    appr = _table().get_item(Key=appr_key).get("Item", {})
    if "notes" in appr:
        _table().update_item(
            Key=appr_key,
            UpdateExpression="SET notes = :v, erased_at = :ts",
            ExpressionAttributeValues={":v": ERASED_VALUE, ":ts": int(time.time())},
        )
        nulled["approval"].append("notes")

    return nulled


def request_erasure(
    by_session_id: str | None,
    by_vendor_name: str | None,
    reason: str,
    requested_by: str,
) -> dict:
    """Process a GDPR Right-to-Erasure request.

    Anonymizes DynamoDB PII for matching sessions and writes an erasure
    log row keyed by erasure_id. Hash, signer, anchor txs, vault refs,
    and decision are PRESERVED — they constitute the audit-chain
    integrity records the AML retention window requires.
    """
    session_ids = _find_sessions(by_session_id, by_vendor_name)
    erasure_id = str(uuid.uuid4())
    summaries = {}
    for sid in session_ids:
        summaries[sid] = _anonymize_session(sid)

    log.info(
        "erasure %s: anonymized %d sessions for reason=%s requested_by=%s",
        erasure_id, len(session_ids), reason, requested_by,
    )

    # Erasure log row — itself retained per AML rules.
    now = int(time.time())
    _table().put_item(Item={
        "pk": f"erasure#{erasure_id}",
        "type": "erasure_log",
        "erasure_id": erasure_id,
        "by_session_id": by_session_id or "",
        "by_vendor_name": by_vendor_name or "",
        "reason": reason,
        "requested_by": requested_by,
        "session_ids_affected": session_ids,
        "fields_nulled": [
            f"{sid}:{table}:{field}"
            for sid, by_table in summaries.items()
            for table, fields in by_table.items()
            for field in fields
        ],
        "executed_at": now,
        "ttl_at": now + evidence_store.RETENTION_SECONDS,
    })

    return {
        "erasure_id": erasure_id,
        "sessions_affected": len(session_ids),
        "session_ids": session_ids,
        "fields_nulled": summaries,
        "preserved_for_aml_retention": [
            "merkle_root", "anchor_tx", "solana_anchor_tx",
            "signer", "signature", "decision",
            "vault_s3_uri (S3 Object Lock COMPLIANCE until 2033)",
        ],
    }
