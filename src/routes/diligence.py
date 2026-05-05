import json

from fastapi import APIRouter, HTTPException

from ..models import DiligenceRequest
from ..services import bazaar_client, bedrock_client, evidence_store

router = APIRouter()


@router.post("/diligence")
async def run_diligence(req: DiligenceRequest):
    session_id = evidence_store.new_session(req.vendor_name)

    try:
        travel_rule = bazaar_client.ofac_screen(
            req.vendor_name, req.vendor_wallet, req.vendor_country, req.amount_usd
        )
        evidence_store.record_evidence(session_id, "mru_travel_rule", travel_rule)
    except Exception as e:
        travel_rule = {"error": str(e)}

    try:
        tf_risk = bazaar_client.trade_finance_risk(req.amount_usd)
        evidence_store.record_evidence(session_id, "orbis_trade_finance", tf_risk)
    except Exception as e:
        tf_risk = {"error": str(e)}

    try:
        ef_score = bazaar_client.embedded_finance_score()
        evidence_store.record_evidence(session_id, "orbis_embedded_finance", ef_score)
    except Exception as e:
        ef_score = {"error": str(e)}

    evidence = {
        "travel_rule": travel_rule,
        "trade_finance_risk": tf_risk,
        "embedded_finance_score": ef_score,
    }

    try:
        synthesis_output, prompt_hash = bedrock_client.synthesize(req.vendor_name, evidence)
        synthesis_hash = evidence_store.record_synthesis(session_id, prompt_hash, synthesis_output, "claude-haiku-4-5")
        synthesis = json.loads(synthesis_output)
    except Exception as e:
        synthesis = {"error": str(e)}
        synthesis_hash = ""

    return {
        "session_id": session_id,
        "vendor": req.vendor_name,
        "evidence": evidence,
        "synthesis": synthesis,
        "synthesis_hash": synthesis_hash,
        "officer_url": f"/v1/officer/{session_id}",
    }
