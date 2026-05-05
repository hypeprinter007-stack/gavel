import datetime
import hashlib
import json
import logging
import os
import time
import uuid
from concurrent.futures import ThreadPoolExecutor

import boto3

log = logging.getLogger("counsel.evidence")

from services import secrets

TABLE = os.getenv("EVIDENCE_TABLE", "counsel-evidence")
BASE_RPC_URL = os.getenv("BASE_RPC_URL", "https://mainnet.base.org")
SOLANA_RPC_URL = os.getenv("SOLANA_RPC_URL", "https://api.mainnet-beta.solana.com")


def _treasury_evm_key() -> str:
    return secrets.get("treasury_evm_key", env_fallback="TREASURY_PRIVATE_KEY")


def _treasury_solana_key() -> str:
    return secrets.get("treasury_solana_key", env_fallback="SOLANA_TREASURY_KEY")
EVIDENCE_VAULT_BUCKET = os.getenv("EVIDENCE_VAULT_BUCKET", "")
EVIDENCE_RETENTION_DAYS = int(os.getenv("EVIDENCE_RETENTION_DAYS", "2555"))  # 7y default
_db = None
_s3 = None


def _table():
    global _db
    if _db is None:
        _db = boto3.resource("dynamodb", region_name=os.getenv("BEDROCK_REGION", "us-east-1")).Table(TABLE)
    return _db


def _s3_client():
    global _s3
    if _s3 is None:
        _s3 = boto3.client("s3", region_name=os.getenv("BEDROCK_REGION", "us-east-1"))
    return _s3


def _vault_put(key: str, body: bytes, content_type: str) -> dict:
    """Write to the WORM evidence vault with COMPLIANCE retention.

    Returns {"bucket","key","version_id","etag","s3_uri"} or raises if
    the vault isn't configured. Falls back to no-op when bucket env
    is unset (local dev).
    """
    if not EVIDENCE_VAULT_BUCKET:
        return {}
    retain_until = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=EVIDENCE_RETENTION_DAYS)
    resp = _s3_client().put_object(
        Bucket=EVIDENCE_VAULT_BUCKET,
        Key=key,
        Body=body,
        ContentType=content_type,
        ObjectLockMode="COMPLIANCE",
        ObjectLockRetainUntilDate=retain_until,
        ServerSideEncryption="AES256",
    )
    return {
        "bucket": EVIDENCE_VAULT_BUCKET,
        "key": key,
        "version_id": resp.get("VersionId", ""),
        "etag": resp.get("ETag", "").strip('"'),
        "s3_uri": f"s3://{EVIDENCE_VAULT_BUCKET}/{key}",
    }


def new_session(vendor_name: str, tenant: str = "counsel", customer: str = "") -> str:
    session_id = str(uuid.uuid4())
    item = {
        "pk": f"session#{session_id}",
        "type": "session_root",
        "vendor_name": vendor_name,
        "tenant": tenant,
        "started_at": int(time.time()),
        "status": "pending",
    }
    if customer:
        item["customer"] = customer
    _table().put_item(Item=item)
    return session_id


def record_evidence(session_id: str, source: str, data: dict) -> str:
    """Hash-only in DynamoDB; raw bytes WORM-locked in the vault.

    Splitting hash from raw means a malicious operator with table-write
    perms cannot rewrite the underlying evidence — the S3 object is
    locked with COMPLIANCE retention, immutable for the retention
    period even to root.
    """
    raw = json.dumps(data, sort_keys=True)
    raw_bytes = raw.encode()
    h = hashlib.sha256(raw_bytes).hexdigest()
    vault_ref = _vault_put(
        key=f"sessions/{session_id}/evidence/{source}.json",
        body=raw_bytes,
        content_type="application/json",
    )
    item = {
        "pk": f"session#{session_id}#evidence#{source}",
        "type": "evidence",
        "source": source,
        "hash": h,
        "fetched_at": int(time.time()),
    }
    if vault_ref:
        item.update({
            "vault_s3_uri": vault_ref["s3_uri"],
            "vault_version_id": vault_ref["version_id"],
            "vault_etag": vault_ref["etag"],
        })
    else:
        # Vault not configured (e.g. local dev) — fall back to inline raw.
        item["raw"] = raw
    _table().put_item(Item=item)
    return h


def record_synthesis(session_id: str, prompt_hash: str, output: str, model: str) -> str:
    h = hashlib.sha256(output.encode()).hexdigest()
    vault_ref = _vault_put(
        key=f"sessions/{session_id}/synthesis.json",
        body=output.encode(),
        content_type="application/json",
    )
    item = {
        "pk": f"session#{session_id}#synthesis",
        "type": "synthesis",
        "prompt_hash": prompt_hash,
        "output_hash": h,
        "model": model,
        "created_at": int(time.time()),
    }
    if vault_ref:
        item.update({
            "vault_s3_uri": vault_ref["s3_uri"],
            "vault_version_id": vault_ref["version_id"],
            "vault_etag": vault_ref["etag"],
        })
    else:
        item["output"] = output
    _table().put_item(Item=item)
    return h


def compute_merkle_root(hashes: list[str]) -> str:
    combined = "".join(sorted(hashes))
    return hashlib.sha256(combined.encode()).hexdigest()


def anchor_to_base(merkle_root: str) -> str:
    """Posts merkle_root as calldata to Base. Returns tx hash."""
    from web3 import Web3
    w3 = Web3(Web3.HTTPProvider(BASE_RPC_URL))
    key = _treasury_evm_key()
    acct = w3.eth.account.from_key(key)
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
    signed = w3.eth.account.sign_transaction(tx, key)
    tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
    return "0x" + tx_hash.hex()


_MEMO_PROGRAM_ID = "MemoSq4gqABAXKb96qnH8TysNcWxMyWCqXgDLGmfcHr"


def anchor_to_solana(merkle_root: str) -> str:
    """Posts merkle_root via Solana Memo program. Returns base58 tx signature."""
    import base58
    import requests as rq
    from solders.hash import Hash
    from solders.instruction import AccountMeta, Instruction
    from solders.keypair import Keypair
    from solders.message import Message
    from solders.pubkey import Pubkey
    from solders.transaction import Transaction

    sol_key = _treasury_solana_key()
    if not sol_key:
        raise RuntimeError("Solana treasury key not configured (Secrets Manager + env both empty)")

    kp = Keypair.from_bytes(base58.b58decode(sol_key))

    def _rpc(method, params, retries: int = 2):
        """One retry with 1s backoff — public mainnet RPC 503s under burst load."""
        last_err: Exception | None = None
        for attempt in range(retries + 1):
            try:
                r = rq.post(
                    SOLANA_RPC_URL,
                    json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params},
                    timeout=10,
                )
                r.raise_for_status()
                j = r.json()
                if "error" in j:
                    raise RuntimeError(f"Solana RPC: {j['error']}")
                return j["result"]
            except Exception as e:
                last_err = e
                if attempt < retries:
                    log.warning("solana RPC %s failed (attempt %d): %s; retrying", method, attempt + 1, e)
                    time.sleep(1)
                    continue
                raise
        raise last_err  # unreachable, satisfies type checker

    blockhash = _rpc("getLatestBlockhash", [{"commitment": "finalized"}])["value"]["blockhash"]
    ix = Instruction(
        program_id=Pubkey.from_string(_MEMO_PROGRAM_ID),
        accounts=[AccountMeta(pubkey=kp.pubkey(), is_signer=True, is_writable=True)],
        data=merkle_root.encode("utf-8"),
    )
    msg = Message.new_with_blockhash([ix], kp.pubkey(), Hash.from_string(blockhash))
    tx = Transaction([kp], msg, Hash.from_string(blockhash))
    raw = bytes(tx)
    return _rpc("sendTransaction", [base58.b58encode(raw).decode(), {"encoding": "base58", "preflightCommitment": "processed"}])


def finalize_session(session_id: str, evidence_hashes: list[str], synthesis_hash: str) -> tuple[str, str, str | None]:
    """Returns (merkle_root, base_anchor_tx, solana_anchor_tx_or_None)."""
    leaves = evidence_hashes + ([synthesis_hash] if synthesis_hash else [])
    merkle_root = compute_merkle_root(leaves)

    base_tx: str = ""
    solana_tx: str | None = None
    with ThreadPoolExecutor(max_workers=2) as pool:
        f_base = pool.submit(anchor_to_base, merkle_root)
        f_sol = pool.submit(anchor_to_solana, merkle_root)
        base_tx = f_base.result(timeout=30)
        try:
            solana_tx = f_sol.result(timeout=20)
        except Exception as e:
            log.warning("solana anchor failed: %s: %s", type(e).__name__, e)
            solana_tx = None

    update_expr = "SET merkle_root = :m, anchor_tx = :t"
    values: dict = {":m": merkle_root, ":t": base_tx}
    if solana_tx:
        update_expr += ", solana_anchor_tx = :s"
        values[":s"] = solana_tx
    _table().update_item(
        Key={"pk": f"session#{session_id}"},
        UpdateExpression=update_expr,
        ExpressionAttributeValues=values,
    )
    return merkle_root, base_tx, solana_tx


def record_approval(session_id: str, decision: str, signature: str, notes: str = "", signer: str = "") -> None:
    """Atomic claim: only succeeds if the session is still pending.

    Raises botocore.exceptions.ClientError (ConditionalCheckFailedException)
    if another concurrent request already decided the session — the caller
    should translate this into a 409.
    """
    _table().update_item(
        Key={"pk": f"session#{session_id}"},
        UpdateExpression="SET #s = :s, signer = :a",
        ConditionExpression="#s = :pending",
        ExpressionAttributeNames={"#s": "status"},
        ExpressionAttributeValues={":s": decision, ":a": signer, ":pending": "pending"},
    )
    _table().put_item(Item={
        "pk": f"session#{session_id}#approval",
        "type": "approval",
        "decision": decision,
        "signature": signature,
        "signer": signer,
        "notes": notes,
        "decided_at": int(time.time()),
    })


def get_session(session_id: str) -> dict:
    resp = _table().get_item(Key={"pk": f"session#{session_id}"})
    return resp.get("Item", {})
