"""End-to-end test for Counsel.

Default: client pays in Base USDC, officer signs with EVM wallet.
With --solana-pay: client pays in Solana USDC.
With --solana-sign: officer signs with Solana wallet (Ed25519).
Combine flags for fully Solana-only flow.
"""
import json
import os
import sys

from dotenv import load_dotenv
load_dotenv()

import base58
from eth_account import Account
from eth_account.messages import encode_defunct
from solders.keypair import Keypair as SolanaKeypair

from x402 import x402ClientSync
from x402.mechanisms.evm.exact import ExactEvmClientScheme
from x402.mechanisms.evm.signers import EthAccountSigner
from x402.mechanisms.svm.exact import register_exact_svm_client
from x402.mechanisms.svm.signers import KeypairSigner as SolanaKeypairSigner
from x402.http.clients.requests import x402_requests

API_URL = "https://ki55wa4a21.execute-api.us-east-1.amazonaws.com"
SOLANA_MAINNET_CAIP2 = "solana:5eykt4UsFv8P8NJdTREpY1vzqKqZKvdp"

CLIENT_KEY = os.getenv("CLIENT_PRIVATE_KEY")
OFFICER_KEY = os.getenv("OFFICER_PRIVATE_KEY")
SOLANA_CLIENT_KEY = os.getenv("SOLANA_CLIENT_KEY")


def _build_session(use_solana_pay: bool):
    client = x402ClientSync()
    if use_solana_pay:
        if not SOLANA_CLIENT_KEY:
            raise RuntimeError("SOLANA_CLIENT_KEY not set")
        sol_signer = SolanaKeypairSigner.from_base58(SOLANA_CLIENT_KEY)
        register_exact_svm_client(client, sol_signer, networks=SOLANA_MAINNET_CAIP2)
        payer_label = f"Solana wallet {sol_signer.keypair.pubkey()}"
    else:
        evm_signer = EthAccountSigner(Account.from_key(CLIENT_KEY))
        client.register("eip155:8453", ExactEvmClientScheme(evm_signer))
        payer_label = f"EVM wallet {Account.from_key(CLIENT_KEY).address}"
    return x402_requests(client), payer_label


def _sign_evm(merkle_root: str) -> dict:
    officer = Account.from_key(OFFICER_KEY)
    msg = encode_defunct(text=merkle_root)
    sig = officer.sign_message(msg).signature.hex()
    print(f"Officer (EVM, {officer.address}) signs merkle_root...")
    return {"signature": "0x" + sig, "decision": "APPROVED",
            "notes": "Travel rule clear. Proceed with enhanced monitoring."}


def _sign_solana(merkle_root: str) -> dict:
    # Generate a fresh Solana officer keypair on the fly — this is the
    # "Phantom wallet officer" path. No funding needed; signing is off-chain.
    officer = SolanaKeypair()
    sig = officer.sign_message(merkle_root.encode("utf-8"))
    print(f"Officer (Solana, {officer.pubkey()}) signs merkle_root with Ed25519...")
    return {
        "signature": base58.b58encode(bytes(sig)).decode(),
        "signer_pubkey": str(officer.pubkey()),
        "decision": "APPROVED",
        "notes": "Travel rule clear. Solana officer approval.",
    }


def run(use_solana_pay: bool, use_solana_sign: bool):
    session, payer_label = _build_session(use_solana_pay)
    print(f"Payer:  {payer_label}")
    print(f"Officer: {'Solana Ed25519 (fresh keypair)' if use_solana_sign else 'EVM EIP-191'}")

    pay_chain = "Solana USDC" if use_solana_pay else "Base USDC"
    print(f"\nPOST /v1/diligence (paying $0.05 in {pay_chain})...")
    resp = session.post(
        f"{API_URL}/v1/diligence",
        json={
            "vendor_name": "Northstar Crypto Capital",
            "vendor_country": "AE",
            "vendor_wallet": "0x0360D000622F942b9656D59c679D19d5D12ec989",
            "amount_usd": 50000,
        },
        timeout=120,
    )
    print(f"Status: {resp.status_code}")
    data = resp.json()
    print(f"\nsession_id:      {data.get('session_id')}")
    print(f"merkle_root:     {data.get('merkle_root')}")
    anchors = data.get("anchors") or {}
    if anchors.get("base"):
        print(f"Base anchor:     {anchors['base']['explorer_url']}")
    if anchors.get("solana"):
        print(f"Solana anchor:   {anchors['solana']['explorer_url']}")
    print("\nsynthesis:")
    print(json.dumps(data.get("synthesis", {}), indent=2))

    session_id = data.get("session_id")
    merkle_root = data.get("merkle_root")
    if not session_id or not merkle_root:
        return

    print("\n--- Officer review ---")
    payload = _sign_solana(merkle_root) if use_solana_sign else _sign_evm(merkle_root)
    r3 = session.post(f"{API_URL}/v1/officer/{session_id}/sign", json=payload, timeout=20)
    print(f"\nPOST /v1/officer/{session_id}/sign — {r3.status_code}")
    print(json.dumps(r3.json(), indent=2))


if __name__ == "__main__":
    args = sys.argv[1:]
    run(use_solana_pay="--solana-pay" in args, use_solana_sign="--solana-sign" in args)
