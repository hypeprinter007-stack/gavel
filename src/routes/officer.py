from fastapi import APIRouter, HTTPException

from ..models import OfficerSignRequest
from ..services import evidence_store

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
        "sign_url": f"/v1/officer/{session_id}/sign",
    }


@router.post("/officer/{session_id}/sign")
async def officer_sign(session_id: str, req: OfficerSignRequest):
    session = evidence_store.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    if session.get("status") not in ("pending",):
        raise HTTPException(status_code=409, detail="Session already decided")

    evidence_store.record_approval(session_id, req.decision, req.signature, req.notes or "")

    return {
        "session_id": session_id,
        "decision": req.decision,
        "signature": req.signature,
        "status": "recorded",
    }
