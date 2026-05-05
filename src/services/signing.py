"""Domain-separated officer signature verification.

Two schemes are supported:

EVM (Metamask, Rabby, etc.):
    EIP-712 typed data with Counsel as the domain. Metamask renders the
    sign prompt as a structured object — the officer sees what they're
    approving (session_id, merkle_root, decision) instead of a raw hash.

Solana (Phantom, Solflare):
    Ed25519 over a domain-prefixed UTF-8 string. Solana has no
    EIP-712 equivalent, but the prefix kills cross-app replay because
    a signature for "Counsel/v1\\n..." can't be reused as a signature
    for any other application's payload.

The signature binds:
- the application (Counsel)
- the version (v1)
- the chain context (chainId for EVM; "solana" prefix for SVM)
- the specific session_id
- the merkle_root
- the decision (APPROVED vs REJECTED — flip-resistant)
"""
from __future__ import annotations

DOMAIN_NAME = "Counsel"
DOMAIN_VERSION = "1"
EVM_CHAIN_ID = 8453  # Base mainnet


def evm_typed_data(session_id: str, merkle_root: str, decision: str) -> dict:
    """Returns the EIP-712 typed-data structure to sign / recover from."""
    return {
        "types": {
            "EIP712Domain": [
                {"name": "name", "type": "string"},
                {"name": "version", "type": "string"},
                {"name": "chainId", "type": "uint256"},
            ],
            "Approval": [
                {"name": "session_id", "type": "string"},
                {"name": "merkle_root", "type": "string"},
                {"name": "decision", "type": "string"},
            ],
        },
        "primaryType": "Approval",
        "domain": {
            "name": DOMAIN_NAME,
            "version": DOMAIN_VERSION,
            "chainId": EVM_CHAIN_ID,
        },
        "message": {
            "session_id": session_id,
            "merkle_root": merkle_root,
            "decision": decision,
        },
    }


def solana_message(session_id: str, merkle_root: str, decision: str) -> bytes:
    """Returns the canonical UTF-8 bytes the Solana officer signs over."""
    body = (
        f"{DOMAIN_NAME}/v{DOMAIN_VERSION}\n"
        f"chain=solana\n"
        f"session_id={session_id}\n"
        f"merkle_root={merkle_root}\n"
        f"decision={decision}"
    )
    return body.encode("utf-8")


def verify_evm(session_id: str, merkle_root: str, decision: str, signature: str) -> str:
    """Recover the EIP-712 signer address. Raises on invalid signature."""
    from eth_account import Account
    from eth_account.messages import encode_typed_data

    typed = evm_typed_data(session_id, merkle_root, decision)
    msg = encode_typed_data(full_message=typed)
    return Account.recover_message(msg, signature=signature)


def verify_solana(session_id: str, merkle_root: str, decision: str, signature: str, signer_pubkey: str) -> bool:
    """Verify Ed25519 signature against pubkey. Raises on invalid pubkey/sig."""
    import base58
    from solders.pubkey import Pubkey
    from solders.signature import Signature

    pk = Pubkey.from_string(signer_pubkey)
    sig = Signature.from_bytes(base58.b58decode(signature))
    return sig.verify(pk, solana_message(session_id, merkle_root, decision))
