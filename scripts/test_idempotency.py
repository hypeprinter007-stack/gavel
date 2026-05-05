"""Demonstrate idempotency: same Idempotency-Key + same payload returns
the cached response with the Idempotent-Replayed: true header, without
charging x402 again. Different payload + same key returns 409.
"""
import os
import time
import uuid

from dotenv import load_dotenv
load_dotenv()

from eth_account import Account
from x402 import x402ClientSync
from x402.mechanisms.evm.exact import ExactEvmClientScheme
from x402.mechanisms.evm.signers import EthAccountSigner
from x402.http.clients.requests import x402_requests

API = "https://ki55wa4a21.execute-api.us-east-1.amazonaws.com"
PAYLOAD = {
    "vendor_name": "Northstar Crypto Capital",
    "vendor_country": "AE",
    "vendor_wallet": "0x0360D000622F942b9656D59c679D19d5D12ec989",
    "amount_usd": 50000,
}


def _sess():
    acct = Account.from_key(os.environ["CLIENT_PRIVATE_KEY"])
    client = x402ClientSync()
    client.register("eip155:8453", ExactEvmClientScheme(EthAccountSigner(acct)))
    return x402_requests(client)


def main():
    s = _sess()
    key = str(uuid.uuid4())

    print(f"Idempotency-Key: {key}")
    print()

    print("=== 1st call: should pay x402 + run diligence ===")
    t0 = time.time()
    r1 = s.post(f"{API}/v1/diligence", json=PAYLOAD,
                headers={"Idempotency-Key": key}, timeout=120)
    print(f"  status: {r1.status_code}")
    print(f"  duration: {time.time() - t0:.1f}s")
    print(f"  Idempotent-Replayed header: {r1.headers.get('Idempotent-Replayed', 'absent')}")
    print(f"  session_id: {r1.json().get('session_id')}")
    print(f"  base anchor: {r1.json().get('anchors', {}).get('base', {}).get('tx', '')[:20]}...")

    print()
    print("=== 2nd call: same key + same payload → cached, no charge ===")
    t0 = time.time()
    r2 = s.post(f"{API}/v1/diligence", json=PAYLOAD,
                headers={"Idempotency-Key": key}, timeout=30)
    print(f"  status: {r2.status_code}")
    print(f"  duration: {time.time() - t0:.1f}s  (much faster — no x402, no Bedrock, no anchors)")
    print(f"  Idempotent-Replayed header: {r2.headers.get('Idempotent-Replayed', 'absent')}")
    print(f"  session_id: {r2.json().get('session_id')}  (matches first call)")

    print()
    print("=== 3rd call: same key + DIFFERENT payload → 409 conflict ===")
    different = {**PAYLOAD, "amount_usd": 99999}
    r3 = s.post(f"{API}/v1/diligence", json=different,
                headers={"Idempotency-Key": key}, timeout=30)
    print(f"  status: {r3.status_code}")
    print(f"  detail: {r3.json().get('detail')}")


if __name__ == "__main__":
    main()
