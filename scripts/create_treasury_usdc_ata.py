"""One-shot: create the Solana treasury's USDC Associated Token Account.

Without this, x402 SVM payment simulation fails with InvalidAccountData
because the receiver has no token account to credit.

Idempotent: safe to run multiple times.
"""
import os

import base58
import requests as rq
from dotenv import load_dotenv

load_dotenv()

from solders.hash import Hash
from solders.keypair import Keypair
from solders.message import Message
from solders.pubkey import Pubkey
from solders.transaction import Transaction
from spl.token.instructions import (
    create_associated_token_account,
    get_associated_token_address,
)

USDC_MINT = Pubkey.from_string("EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v")
RPC = os.getenv("SOLANA_RPC_URL", "https://api.mainnet-beta.solana.com")
SOL_KEY_B58 = os.environ["SOLANA_TREASURY_KEY"]


def _rpc(method, params):
    r = rq.post(RPC, json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params}, timeout=15)
    r.raise_for_status()
    j = r.json()
    if "error" in j:
        raise RuntimeError(j["error"])
    return j["result"]


def main():
    kp = Keypair.from_bytes(base58.b58decode(SOL_KEY_B58))
    owner = kp.pubkey()
    ata = get_associated_token_address(owner, USDC_MINT)
    print(f"Treasury wallet:        {owner}")
    print(f"USDC ATA (target):      {ata}")

    info = _rpc("getAccountInfo", [str(ata), {"encoding": "base64"}])["value"]
    if info is not None:
        print("ATA already exists. Nothing to do.")
        return

    blockhash = _rpc("getLatestBlockhash", [{"commitment": "finalized"}])["value"]["blockhash"]
    ix = create_associated_token_account(payer=owner, owner=owner, mint=USDC_MINT)
    msg = Message.new_with_blockhash([ix], owner, Hash.from_string(blockhash))
    tx = Transaction([kp], msg, Hash.from_string(blockhash))
    sig = _rpc("sendTransaction", [base58.b58encode(bytes(tx)).decode(),
                                    {"encoding": "base58", "preflightCommitment": "processed"}])
    print(f"Tx sent: {sig}")
    print(f"Solscan: https://solscan.io/tx/{sig}")


if __name__ == "__main__":
    main()
