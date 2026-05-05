import os

from fastapi import APIRouter, HTTPException

from models import OfficerSignRequest
from services import evidence_store, officer_registry
from services.signing import verify_evm, verify_solana

ENFORCE_OFFICER_REGISTRY = os.getenv("ENFORCE_OFFICER_REGISTRY", "true").lower() == "true"

router = APIRouter()


def _verify_signature(
    session_id: str,
    merkle_root: str,
    decision: str,
    signature: str,
    signer_pubkey: str | None,
) -> tuple[str, str]:
    """Returns (signer_identifier, scheme) or raises HTTPException(400)."""
    if signer_pubkey:
        try:
            if not verify_solana(session_id, merkle_root, decision, signature, signer_pubkey):
                raise ValueError("Ed25519 signature does not verify")
            return signer_pubkey, "ed25519"
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Invalid Solana signature: {e}")
    try:
        addr = verify_evm(session_id, merkle_root, decision, signature)
        return addr, "eip712"
    except Exception as e:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid EIP-712 signature — sign the typed-data approval payload: {e}",
        )


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
        "signing_payload_hint": {
            "evm": "EIP-712 typed-data with domain {name:'Counsel', version:'1', chainId:8453} and primaryType 'Approval' over {session_id, merkle_root, decision}",
            "solana": "Ed25519 over UTF-8 'Counsel/v1\\nchain=solana\\nsession_id=...\\nmerkle_root=...\\ndecision=...'",
        },
    }


@router.post("/officer/{session_id}/sign")
async def officer_sign(session_id: str, req: OfficerSignRequest):
    session = evidence_store.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    if session.get("status") not in ("pending",):
        raise HTTPException(status_code=409, detail="Session already decided")

    merkle_root = session.get("merkle_root", "")
    signer, scheme = _verify_signature(
        session_id, merkle_root, req.decision, req.signature, req.signer_pubkey
    )

    if ENFORCE_OFFICER_REGISTRY and not officer_registry.is_authorized(signer):
        raise HTTPException(
            status_code=403,
            detail=f"Signer {signer} is not registered as an authorized compliance officer for this tenant",
        )

    try:
        evidence_store.record_approval(session_id, req.decision, req.signature, req.notes or "", signer)
    except Exception as e:
        if "ConditionalCheckFailed" in repr(e):
            raise HTTPException(status_code=409, detail="Session already decided")
        raise

    return {
        "session_id": session_id,
        "decision": req.decision,
        "signer": signer,
        "signature_scheme": scheme,
        "merkle_root": merkle_root,
        "anchors": _anchors(session),
        "status": "recorded",
    }
