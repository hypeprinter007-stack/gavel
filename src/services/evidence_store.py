import hashlib
import json
import os
import time
import uuid

import boto3

TABLE = os.getenv("EVIDENCE_TABLE", "counsel-evidence")
_db = None


def _table():
    global _db
    if _db is None:
        _db = boto3.resource("dynamodb", region_name=os.getenv("BEDROCK_REGION", "us-east-1")).Table(TABLE)
    return _db


def new_session(vendor_name: str) -> str:
    session_id = str(uuid.uuid4())
    _table().put_item(Item={
        "pk": f"session#{session_id}",
        "type": "session_root",
        "vendor_name": vendor_name,
        "started_at": int(time.time()),
        "status": "pending",
    })
    return session_id


def record_evidence(session_id: str, source: str, data: dict) -> str:
    raw = json.dumps(data, sort_keys=True)
    h = hashlib.sha256(raw.encode()).hexdigest()
    _table().put_item(Item={
        "pk": f"session#{session_id}#evidence#{source}",
        "type": "evidence",
        "source": source,
        "hash": h,
        "raw": raw,
        "fetched_at": int(time.time()),
    })
    return h


def record_synthesis(session_id: str, prompt_hash: str, output: str, model: str) -> str:
    h = hashlib.sha256(output.encode()).hexdigest()
    _table().put_item(Item={
        "pk": f"session#{session_id}#synthesis",
        "type": "synthesis",
        "prompt_hash": prompt_hash,
        "output_hash": h,
        "output": output,
        "model": model,
        "created_at": int(time.time()),
    })
    return h


def compute_merkle_root(hashes: list[str]) -> str:
    combined = "".join(sorted(hashes))
    return hashlib.sha256(combined.encode()).hexdigest()


def finalize_session(session_id: str, evidence_hashes: list[str], synthesis_hash: str) -> str:
    merkle_root = compute_merkle_root(evidence_hashes + [synthesis_hash])
    _table().update_item(
        Key={"pk": f"session#{session_id}"},
        UpdateExpression="SET merkle_root = :m",
        ExpressionAttributeValues={":m": merkle_root},
    )
    return merkle_root


def record_approval(session_id: str, decision: str, signature: str, notes: str = "") -> None:
    _table().put_item(Item={
        "pk": f"session#{session_id}#approval",
        "type": "approval",
        "decision": decision,
        "signature": signature,
        "notes": notes,
        "decided_at": int(time.time()),
    })
    _table().update_item(
        Key={"pk": f"session#{session_id}"},
        UpdateExpression="SET #s = :s",
        ExpressionAttributeNames={"#s": "status"},
        ExpressionAttributeValues={":s": decision},
    )


def get_session(session_id: str) -> dict:
    resp = _table().get_item(Key={"pk": f"session#{session_id}"})
    return resp.get("Item", {})
