"""End-to-end test: pays the live Lambda with x402 and runs full diligence."""
import json
import os

from dotenv import load_dotenv
load_dotenv()

from eth_account import Account
from x402 import x402ClientSync
from x402.mechanisms.evm.exact import ExactEvmClientScheme
from x402.mechanisms.evm.signers import EthAccountSigner
from x402.http.clients.requests import x402_requests

API_URL = "https://ki55wa4a21.execute-api.us-east-1.amazonaws.com"
CLIENT_KEY = os.getenv("CLIENT_PRIVATE_KEY")

def run():
    acct = Account.from_key(CLIENT_KEY)
    print(f"Paying from: {acct.address}  (client wallet, separate from treasury)")

    signer = EthAccountSigner(acct)
    client = x402ClientSync()
    client.register("eip155:8453", ExactEvmClientScheme(signer))
    session = x402_requests(client)

    print("\nPOST /v1/diligence (paying $0.05 USDC on Base)...")
    resp = session.post(
        f"{API_URL}/v1/diligence",
        json={
            "vendor_name": "Northstar Crypto Capital",
            "vendor_country": "AE",
            "vendor_wallet": "0x0360D000622F942b9656D59c679D19d5D12ec989",
            "amount_usd": 50000,
        },
        timeout=60,
    )

    print(f"Status: {resp.status_code}")
    data = resp.json()
    print(f"\nsession_id:      {data.get('session_id')}")
    print(f"synthesis:")
    print(json.dumps(data.get('synthesis', {}), indent=2))
    print(f"\nofficer_url:     {data.get('officer_url')}")

    session_id = data.get("session_id")
    if session_id:
        print(f"\nGET /v1/officer/{session_id}...")
        r2 = session.get(f"{API_URL}/v1/officer/{session_id}", timeout=15)
        print(f"Status: {r2.status_code}")
        print(json.dumps(r2.json(), indent=2))

if __name__ == "__main__":
    run()
