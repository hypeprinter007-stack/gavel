import base64
import json
import os
import secrets
import time
from urllib.parse import urlparse

CDP_API_KEY_ID = os.getenv("CDP_API_KEY_ID", "")
CDP_API_KEY_SECRET = os.getenv("CDP_API_KEY_SECRET", "")
FACILITATOR_URL = "https://api.cdp.coinbase.com/platform/v2/x402"


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _build_cdp_jwt(method: str, path: str) -> str:
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    raw_key = base64.b64decode(CDP_API_KEY_SECRET)
    private_key = Ed25519PrivateKey.from_private_bytes(raw_key[:32])
    now = int(time.time())
    parsed = urlparse(FACILITATOR_URL)
    uri = f"{method} {parsed.netloc}{path}"
    header = {"alg": "EdDSA", "typ": "JWT", "kid": CDP_API_KEY_ID, "nonce": secrets.token_hex(16)}
    payload = {"sub": CDP_API_KEY_ID, "iss": "cdp", "aud": ["cdp_service"],
               "nbf": now, "exp": now + 120, "uri": uri}
    h = _b64url(json.dumps(header, separators=(",", ":")).encode())
    p = _b64url(json.dumps(payload, separators=(",", ":")).encode())
    signing_input = f"{h}.{p}".encode()
    sig = private_key.sign(signing_input)
    return f"{h}.{p}.{_b64url(sig)}"


def _build_cdp_auth_provider():
    if not CDP_API_KEY_ID or not CDP_API_KEY_SECRET:
        return None
    from x402.http.facilitator_client_base import CreateHeadersAuthProvider
    def create_headers():
        return {
            "verify": {"Authorization": f"Bearer {_build_cdp_jwt('POST', '/platform/v2/x402/verify')}"},
            "settle": {"Authorization": f"Bearer {_build_cdp_jwt('POST', '/platform/v2/x402/settle')}"},
            "supported": {"Authorization": f"Bearer {_build_cdp_jwt('GET', '/platform/v2/x402/supported')}"},
        }
    return CreateHeadersAuthProvider(create_headers)
