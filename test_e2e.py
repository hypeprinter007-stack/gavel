"""End-to-end test for Counsel.

Default: client pays in Base USDC, EVM officer signs with EIP-712 typed data.
--solana-pay      : client pays in Solana USDC instead of Base.
--solana-sign     : Solana officer signs (domain-separated Ed25519).
--rogue-officer   : a fresh, UNREGISTERED keypair tries to sign — server
                    rejects with 403 even though the cryptographic
                    signature itself is mathematically valid. Demonstrates
                    the officer allowlist enforcement.
--rogue-customer  : drop the X-Counsel-API-Key header — server rejects
                    with 401 before x402 is ever charged. Demonstrates
                    customer authentication enforcement.
"""
import json
import os
import sys

from dotenv import load_dotenv
load_dotenv()

import sys as _sys
_sys.path.insert(0, "src")  # access services.signing without packaging

import base58
from eth_account import Account
from eth_account.messages import encode_typed_data
from solders.keypair import Keypair as SolanaKeypair

from services.signing import evm_typed_data, solana_message

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
OFFICER_SOLANA_KEY = os.getenv("OFFICER_SOLANA_KEY")
SOLANA_CLIENT_KEY = os.getenv("SOLANA_CLIENT_KEY")
COUNSEL_API_KEY = os.getenv("COUNSEL_API_KEY", "")


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


def _sign_evm(session_id: str, merkle_root: str, decision: str = "APPROVED") -> dict:
    officer = Account.from_key(OFFICER_KEY)
    typed = evm_typed_data(session_id, merkle_root, decision)
    msg = encode_typed_data(full_message=typed)
    sig = officer.sign_message(msg).signature.hex()
    print(f"Officer (EVM, {officer.address}) signs EIP-712 Approval typed-data...")
    return {"signature": "0x" + sig, "decision": decision,
            "notes": "Travel rule clear. Proceed with enhanced monitoring."}


def _sign_solana(session_id: str, merkle_root: str, decision: str = "APPROVED",
                 rogue: bool = False) -> dict:
    if rogue or not OFFICER_SOLANA_KEY:
        officer = SolanaKeypair()  # fresh, unregistered → expect 403
        label = "ROGUE (unregistered)"
    else:
        officer = SolanaKeypair.from_bytes(base58.b58decode(OFFICER_SOLANA_KEY))
        label = "registered"
    msg_bytes = solana_message(session_id, merkle_root, decision)
    sig = officer.sign_message(msg_bytes)
    print(f"Officer (Solana {label}, {officer.pubkey()}) signs domain-separated Counsel approval...")
    return {
        "signature": base58.b58encode(bytes(sig)).decode(),
        "signer_pubkey": str(officer.pubkey()),
        "decision": decision,
        "notes": "Travel rule clear. Solana officer approval.",
    }


def _sign_evm_rogue(session_id: str, merkle_root: str, decision: str = "APPROVED") -> dict:
    """A fresh EVM keypair signs the canonical approval; should be rejected
    by the officer registry with 403 even though the signature is valid."""
    rogue = Account.create()
    typed = evm_typed_data(session_id, merkle_root, decision)
    msg = encode_typed_data(full_message=typed)
    sig = rogue.sign_message(msg).signature.hex()
    print(f"Officer (EVM ROGUE, {rogue.address}) signs valid EIP-712 — registry should reject...")
    return {"signature": "0x" + sig, "decision": decision,
            "notes": "Unauthorized officer attempt."}


def run(use_solana_pay: bool, use_solana_sign: bool, rogue: bool = False, rogue_customer: bool = False):
    session, payer_label = _build_session(use_solana_pay)
    print(f"Payer:    {payer_label}")
    print(f"Customer: {'ROGUE (no API key) — expect 401' if rogue_customer else 'authenticated via X-Counsel-API-Key'}")
    if rogue:
        print(f"Officer:  ROGUE (fresh, unregistered) — expect 403 from allowlist enforcement")
    else:
        print(f"Officer:  {'Solana Ed25519 (registered)' if use_solana_sign else 'EVM EIP-712 (registered)'}")

    pay_chain = "Solana USDC" if use_solana_pay else "Base USDC"
    print(f"\nPOST /v1/diligence (paying $0.05 in {pay_chain})...")
    headers: dict[str, str] = {}
    if not rogue_customer and COUNSEL_API_KEY:
        headers["X-Counsel-API-Key"] = COUNSEL_API_KEY
    resp = session.post(
        f"{API_URL}/v1/diligence",
        json={
            "vendor_name": "Northstar Crypto Capital",
            "vendor_country": "AE",
            "vendor_wallet": "0x0360D000622F942b9656D59c679D19d5D12ec989",
            "amount_usd": 50000,
        },
        headers=headers,
        timeout=120,
    )
    print(f"Status: {resp.status_code}")
    if resp.status_code != 200:
        print(f"Body: {resp.text}")
        return
    data = resp.json()
    print(f"\nsession_id:      {data.get('session_id')}")
    if data.get("customer"):
        c = data["customer"]
        print(f"customer:        {c['name']} ({c['country']}) — tenant '{data.get('tenant')}'")
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
    if use_solana_sign:
        payload = _sign_solana(session_id, merkle_root, rogue=rogue)
    elif rogue:
        payload = _sign_evm_rogue(session_id, merkle_root)
    else:
        payload = _sign_evm(session_id, merkle_root)
    r3 = session.post(f"{API_URL}/v1/officer/{session_id}/sign", json=payload, timeout=20)
    print(f"\nPOST /v1/officer/{session_id}/sign — {r3.status_code}")
    print(json.dumps(r3.json(), indent=2))


if __name__ == "__main__":
    args = sys.argv[1:]
    run(
        use_solana_pay="--solana-pay" in args,
        use_solana_sign="--solana-sign" in args,
        rogue="--rogue-officer" in args,
        rogue_customer="--rogue-customer" in args,
    )
