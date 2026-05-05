"""End-to-end test: pays the live Lambda with x402 and runs full diligence."""
import json
import os

from dotenv import load_dotenv
load_dotenv()

from eth_account import Account
from eth_account.messages import encode_defunct
from x402 import x402ClientSync
from x402.mechanisms.evm.exact import ExactEvmClientScheme
from x402.mechanisms.evm.signers import EthAccountSigner
from x402.http.clients.requests import x402_requests

API_URL = "https://ki55wa4a21.execute-api.us-east-1.amazonaws.com"
CLIENT_KEY = os.getenv("CLIENT_PRIVATE_KEY")
OFFICER_KEY = os.getenv("OFFICER_PRIVATE_KEY")

def run():
    acct = Account.from_key(CLIENT_KEY)
    officer = Account.from_key(OFFICER_KEY)
    print(f"Client (payer):    {acct.address}")
    print(f"Officer (signer):  {officer.address}")

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
        timeout=90,
    )

    print(f"Status: {resp.status_code}")
    data = resp.json()
    print(f"\nsession_id:      {data.get('session_id')}")
    print(f"merkle_root:     {data.get('merkle_root')}")
    anchors = data.get("anchors") or {}
    if anchors.get("base"):
        print(f"Base anchor:     {anchors['base']['tx']}")
        print(f"  basescan:      {anchors['base']['explorer_url']}")
    if anchors.get("solana"):
        print(f"Solana anchor:   {anchors['solana']['tx']}")
        print(f"  solscan:       {anchors['solana']['explorer_url']}")
    print(f"\nsynthesis:")
    print(json.dumps(data.get('synthesis', {}), indent=2))

    session_id = data.get("session_id")
    merkle_root = data.get("merkle_root")

    if not session_id:
        return

    # Officer signs the merkle_root with their wallet
    print(f"\n--- Officer review ---")
    print(f"GET /v1/officer/{session_id}...")
    r2 = session.get(f"{API_URL}/v1/officer/{session_id}", timeout=15)
    print(f"Status: {r2.status_code}")
    print(json.dumps(r2.json(), indent=2))

    if merkle_root:
        print(f"\nOfficer ({officer.address}) signs merkle_root...")
        msg = encode_defunct(text=merkle_root)
        signed_msg = officer.sign_message(msg)
        sig_hex = signed_msg.signature.hex()
        print(f"Signature: 0x{sig_hex[:20]}...")

        print(f"\nPOST /v1/officer/{session_id}/sign...")
        r3 = session.post(
            f"{API_URL}/v1/officer/{session_id}/sign",
            json={
                "decision": "APPROVED",
                "signature": "0x" + sig_hex,
                "notes": "Travel rule clear. Proceed with enhanced monitoring per UAE FATF status.",
            },
            timeout=15,
        )
        print(f"Status: {r3.status_code}")
        print(json.dumps(r3.json(), indent=2))

if __name__ == "__main__":
    run()
