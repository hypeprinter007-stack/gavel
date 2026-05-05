import json
from concurrent.futures import ThreadPoolExecutor, as_completed

from fastapi import APIRouter, HTTPException

from models import DiligenceRequest
from services import bazaar_client, bedrock_client, evidence_store

router = APIRouter()


def _call_bazaar(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except Exception as e:
        return {"error": str(e)}


@router.post("/diligence")
async def run_diligence(req: DiligenceRequest):
    session_id = evidence_store.new_session(req.vendor_name)

    # Run all 3 Bazaar calls in parallel
    with ThreadPoolExecutor(max_workers=3) as pool:
        futures = {
            pool.submit(_call_bazaar, bazaar_client.ofac_screen,
                        req.vendor_name, req.vendor_wallet, req.vendor_country, req.amount_usd): "mru_travel_rule",
            pool.submit(_call_bazaar, bazaar_client.trade_finance_risk, req.amount_usd): "orbis_trade_finance",
            pool.submit(_call_bazaar, bazaar_client.embedded_finance_score): "orbis_embedded_finance",
        }
        results = {}
        for future in as_completed(futures, timeout=20):
            key = futures[future]
            data = future.result()
            results[key] = data
            if "error" not in data:
                evidence_store.record_evidence(session_id, key, data)

    evidence = {
        "travel_rule": results.get("mru_travel_rule", {}),
        "trade_finance_risk": results.get("orbis_trade_finance", {}),
        "embedded_finance_score": results.get("orbis_embedded_finance", {}),
    }

    evidence_hashes = [
        h for key, h in {
            k: evidence_store.record_evidence(session_id, k, v)
            for k, v in evidence.items()
            if "error" not in v
        }.items()
    ]

    try:
        synthesis_output, prompt_hash = bedrock_client.synthesize(req.vendor_name, evidence)
        synthesis_hash = evidence_store.record_synthesis(session_id, prompt_hash, synthesis_output, "claude-haiku-4-5")
        synthesis = json.loads(synthesis_output)
    except Exception as e:
        synthesis = {"error": str(e)}
        synthesis_hash = ""

    merkle_root, anchor_tx = evidence_store.finalize_session(session_id, evidence_hashes, synthesis_hash)

    return {
        "session_id": session_id,
        "vendor": req.vendor_name,
        "evidence": evidence,
        "synthesis": synthesis,
        "merkle_root": merkle_root,
        "synthesis_hash": synthesis_hash,
        "anchor_tx": anchor_tx,
        "basescan_url": f"https://basescan.org/tx/{anchor_tx}",
        "officer_url": f"/v1/officer/{session_id}",
    }
