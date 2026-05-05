from eth_account import Account
from eth_account.messages import encode_defunct
from fastapi import APIRouter, HTTPException

from models import OfficerSignRequest
from services import evidence_store

router = APIRouter()


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
        "anchor_tx": session.get("anchor_tx"),
        "basescan_url": f"https://basescan.org/tx/{session.get('anchor_tx')}" if session.get("anchor_tx") else None,
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
    try:
        msg = encode_defunct(text=merkle_root)
        signer_address = Account.recover_message(msg, signature=req.signature)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid signature — sign the merkle_root with your wallet")

    evidence_store.record_approval(session_id, req.decision, req.signature, req.notes or "", signer_address)

    return {
        "session_id": session_id,
        "decision": req.decision,
        "signer_address": signer_address,
        "merkle_root": merkle_root,
        "anchor_tx": session.get("anchor_tx"),
        "basescan_url": f"https://basescan.org/tx/{session.get('anchor_tx')}",
        "status": "recorded",
    }
