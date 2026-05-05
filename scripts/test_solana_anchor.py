"""Smoke test for Solana Memo anchor before wiring into Lambda."""
import os
import sys

import base58
from dotenv import load_dotenv
load_dotenv()

import requests as rq
from solders.hash import Hash
from solders.instruction import Instruction, AccountMeta
from solders.keypair import Keypair
from solders.message import Message
from solders.pubkey import Pubkey
from solders.transaction import Transaction

MEMO_PROGRAM_ID = Pubkey.from_string("MemoSq4gqABAXKb96qnH8TysNcWxMyWCqXgDLGmfcHr")
RPC = os.getenv("SOLANA_RPC_URL", "https://api.mainnet-beta.solana.com")
SOL_KEY_B58 = os.getenv("SOLANA_TREASURY_KEY")


def _rpc(method, params):
    resp = rq.post(RPC, json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params}, timeout=15)
    resp.raise_for_status()
    j = resp.json()
    if "error" in j:
        raise RuntimeError(f"RPC error: {j['error']}")
    return j["result"]


def anchor_memo(memo_text: str) -> str:
    kp = Keypair.from_bytes(base58.b58decode(SOL_KEY_B58))
    blockhash_str = _rpc("getLatestBlockhash", [{"commitment": "finalized"}])["value"]["blockhash"]

    ix = Instruction(
        program_id=MEMO_PROGRAM_ID,
        accounts=[AccountMeta(pubkey=kp.pubkey(), is_signer=True, is_writable=True)],
        data=memo_text.encode("utf-8"),
    )
    msg = Message.new_with_blockhash([ix], kp.pubkey(), Hash.from_string(blockhash_str))
    tx = Transaction([kp], msg, Hash.from_string(blockhash_str))
    raw = bytes(tx)
    sig = _rpc("sendTransaction", [base58.b58encode(raw).decode(), {"encoding": "base58", "preflightCommitment": "processed"}])
    return sig


if __name__ == "__main__":
    test_root = "deadbeef" * 8
    print(f"Memo: {test_root}")
    sig = anchor_memo(test_root)
    print(f"Signature: {sig}")
    print(f"Solscan:   https://solscan.io/tx/{sig}")
