import hashlib
import json
import os
import time
import uuid

import boto3

TABLE = os.getenv("EVIDENCE_TABLE", "counsel-evidence")
BASE_RPC_URL = os.getenv("BASE_RPC_URL", "https://mainnet.base.org")
TREASURY_KEY = os.getenv("TREASURY_PRIVATE_KEY")
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


def anchor_to_base(merkle_root: str) -> str:
    """Posts merkle_root as calldata to Base. Returns tx hash."""
    from web3 import Web3
    w3 = Web3(Web3.HTTPProvider(BASE_RPC_URL))
    acct = w3.eth.account.from_key(TREASURY_KEY)
    nonce = w3.eth.get_transaction_count(acct.address)
    gas_price = w3.eth.gas_price
    tx = {
        "from": acct.address,
        "to": acct.address,
        "value": 0,
        "data": "0x" + merkle_root,
        "nonce": nonce,
        "chainId": 8453,
        "maxFeePerGas": gas_price,
        "maxPriorityFeePerGas": w3.to_wei(0.001, "gwei"),
    }
    tx["gas"] = w3.eth.estimate_gas(tx)
    signed = w3.eth.account.sign_transaction(tx, TREASURY_KEY)
    tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
    return "0x" + tx_hash.hex()


def finalize_session(session_id: str, evidence_hashes: list[str], synthesis_hash: str) -> tuple[str, str]:
    """Returns (merkle_root, anchor_tx_hash)."""
    leaves = evidence_hashes + ([synthesis_hash] if synthesis_hash else [])
    merkle_root = compute_merkle_root(leaves)
    anchor_tx = anchor_to_base(merkle_root)
    _table().update_item(
        Key={"pk": f"session#{session_id}"},
        UpdateExpression="SET merkle_root = :m, anchor_tx = :t",
        ExpressionAttributeValues={":m": merkle_root, ":t": anchor_tx},
    )
    return merkle_root, anchor_tx


def record_approval(session_id: str, decision: str, signature: str, notes: str = "", signer_address: str = "") -> None:
    _table().put_item(Item={
        "pk": f"session#{session_id}#approval",
        "type": "approval",
        "decision": decision,
        "signature": signature,
        "signer_address": signer_address,
        "notes": notes,
        "decided_at": int(time.time()),
    })
    _table().update_item(
        Key={"pk": f"session#{session_id}"},
        UpdateExpression="SET #s = :s, signer_address = :a",
        ExpressionAttributeNames={"#s": "status"},
        ExpressionAttributeValues={":s": decision, ":a": signer_address},
    )


def get_session(session_id: str) -> dict:
    resp = _table().get_item(Key={"pk": f"session#{session_id}"})
    return resp.get("Item", {})
