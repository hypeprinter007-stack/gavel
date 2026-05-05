import json
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed

from fastapi import APIRouter

from models import DiligenceRequest
from services import bazaar_client, bedrock_client, evidence_store

router = APIRouter()
log = logging.getLogger("counsel.diligence")

# Maps provider ID (DynamoDB source key) to friendly name (API response key)
PROVIDERS = {
    "mru_travel_rule": "travel_rule",
    "orbis_trade_finance": "trade_finance_risk",
    "orbis_embedded_finance": "embedded_finance_score",
}


def _call_bazaar(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except Exception as e:
        log.warning("bazaar call failed: %s -> %s: %s", fn.__name__, type(e).__name__, e)
        return {"error": str(e), "error_type": type(e).__name__}


@router.post("/diligence")
async def run_diligence(req: DiligenceRequest):
    session_id = evidence_store.new_session(req.vendor_name)
    log.info("diligence start session=%s vendor=%s country=%s amount=%s",
             session_id, req.vendor_name, req.vendor_country, req.amount_usd)

    with ThreadPoolExecutor(max_workers=3) as pool:
        futures = {
            pool.submit(_call_bazaar, bazaar_client.ofac_screen,
                        req.vendor_name, req.vendor_wallet, req.vendor_country, req.amount_usd): "mru_travel_rule",
            pool.submit(_call_bazaar, bazaar_client.trade_finance_risk,
                        req.amount_usd, req.vendor_country): "orbis_trade_finance",
            pool.submit(_call_bazaar, bazaar_client.embedded_finance_score,
                        req.vendor_country): "orbis_embedded_finance",
        }
        raw_results: dict[str, dict] = {}
        evidence_hashes: list[str] = []
        try:
            for future in as_completed(futures, timeout=20):
                provider_id = futures[future]
                data = future.result()
                raw_results[provider_id] = data
                if "error" not in data:
                    evidence_hashes.append(
                        evidence_store.record_evidence(session_id, provider_id, data)
                    )
        except TimeoutError:
            pass

    evidence = {
        friendly: raw_results.get(provider_id, {"error": "timeout"})
        for provider_id, friendly in PROVIDERS.items()
    }

    try:
        synthesis_output, prompt_hash, model_id = bedrock_client.synthesize(req.vendor_name, evidence)
        synthesis_hash = evidence_store.record_synthesis(session_id, prompt_hash, synthesis_output, model_id)
        synthesis = json.loads(synthesis_output)
    except Exception as e:
        synthesis = {"error": str(e)}
        synthesis_hash = ""

    merkle_root, anchor_tx, solana_anchor_tx = evidence_store.finalize_session(
        session_id, evidence_hashes, synthesis_hash
    )
    log.info("diligence done session=%s merkle=%s base=%s solana=%s",
             session_id, merkle_root, anchor_tx, solana_anchor_tx or "skipped")

    return {
        "session_id": session_id,
        "vendor": req.vendor_name,
        "evidence": evidence,
        "synthesis": synthesis,
        "merkle_root": merkle_root,
        "synthesis_hash": synthesis_hash,
        "anchors": {
            "base": {
                "tx": anchor_tx,
                "explorer_url": f"https://basescan.org/tx/{anchor_tx}",
            },
            "solana": (
                {
                    "tx": solana_anchor_tx,
                    "explorer_url": f"https://solscan.io/tx/{solana_anchor_tx}",
                }
                if solana_anchor_tx else None
            ),
        },
        "officer_url": f"/v1/officer/{session_id}",
    }
