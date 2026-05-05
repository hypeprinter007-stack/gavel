from eth_account import Account
from eth_account.messages import encode_defunct
from fastapi import APIRouter, HTTPException

from models import OfficerSignRequest
from services import evidence_store

router = APIRouter()


def _verify_signature(merkle_root: str, signature: str, signer_pubkey: str | None) -> tuple[str, str]:
    """Returns (signer_identifier, scheme).

    If signer_pubkey is set: Ed25519 (Solana wallet) — verify signature against pubkey.
    Otherwise: EIP-191 personal_sign — recover signer address from signature.
    """
    if signer_pubkey:
        import base58
        from solders.pubkey import Pubkey
        from solders.signature import Signature
        try:
            pk = Pubkey.from_string(signer_pubkey)
            sig_bytes = base58.b58decode(signature)
            sig = Signature.from_bytes(sig_bytes)
            if not sig.verify(pk, merkle_root.encode("utf-8")):
                raise ValueError("Ed25519 signature does not verify")
            return signer_pubkey, "ed25519"
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Invalid Solana signature: {e}")
    else:
        try:
            msg = encode_defunct(text=merkle_root)
            addr = Account.recover_message(msg, signature=signature)
            return addr, "eip191"
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid EIP-191 signature — sign the merkle_root")


def _anchors(session: dict) -> dict:
    base_tx = session.get("anchor_tx")
    sol_tx = session.get("solana_anchor_tx")
    return {
        "base": {"tx": base_tx, "explorer_url": f"https://basescan.org/tx/{base_tx}"} if base_tx else None,
        "solana": {"tx": sol_tx, "explorer_url": f"https://solscan.io/tx/{sol_tx}"} if sol_tx else None,
    }


@router.get("/officer/{session_id}")
async def get_officer_view(session_id: str):
    session = evidence_store.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return {
        "session_id": session_id,
        "vendor": session.get("vendor_name"),
        "status": session.get("status"),
        "started_at": session.get("started_at"),
        "merkle_root": session.get("merkle_root"),
        "anchors": _anchors(session),
        "sign_url": f"/v1/officer/{session_id}/sign",
    }


@router.post("/officer/{session_id}/sign")
async def officer_sign(session_id: str, req: OfficerSignRequest):
    session = evidence_store.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    if session.get("status") not in ("pending",):
        raise HTTPException(status_code=409, detail="Session already decided")

    merkle_root = session.get("merkle_root", "")
    signer, scheme = _verify_signature(merkle_root, req.signature, req.signer_pubkey)

    evidence_store.record_approval(session_id, req.decision, req.signature, req.notes or "", signer)

    return {
        "session_id": session_id,
        "decision": req.decision,
        "signer": signer,
        "signature_scheme": scheme,
        "merkle_root": merkle_root,
        "anchors": _anchors(session),
        "status": "recorded",
    }
