"""Self-hosted stub responses for Orbis-shaped compliance APIs (demo mode).

Used when upstream Orbis is in maintenance. Responses are deterministic
functions of the request inputs so the demo synthesis stays coherent.
The `_demo_stub: True` field is preserved end-to-end for audit honesty.
"""
from fastapi import APIRouter, Body

router = APIRouter()

_COUNTRY_RISK = {"low": 0, "medium": 18, "high": 38, "very-high": 58}
_PAYMENT_TERM = {
    "confirmed-lc": -10, "lc": -5, "documentary-collection": 0,
    "open-account": 8, "cash-in-advance": -15,
}


@router.post("/stub/orbis/trade-finance-risk")
async def trade_finance_risk(req: dict = Body(...)):
    amount = float(req.get("transactionValueUsd", 0))
    country = req.get("buyerCountryRisk", "medium")
    term = req.get("paymentTerm", "open-account")
    tenor = int(req.get("tenorDays", 30))

    score = 30 + _COUNTRY_RISK.get(country, 18) + _PAYMENT_TERM.get(term, 0)
    if amount > 100000:
        score += 8
    if tenor > 60:
        score += 5
    score = max(5, min(95, score))

    tier = "LOW" if score < 35 else "MEDIUM" if score < 60 else "HIGH"

    return {
        "score": score,
        "tier": tier,
        "factors": [
            {"name": "transaction_value", "contribution": 8 if amount > 100000 else 0},
            {"name": "buyer_country_risk", "contribution": _COUNTRY_RISK.get(country, 18)},
            {"name": "payment_term", "contribution": _PAYMENT_TERM.get(term, 0)},
            {"name": "tenor_days", "contribution": 5 if tenor > 60 else 0},
        ],
        "recommendation": (
            "PROCEED" if tier == "LOW"
            else "PROCEED_WITH_MONITORING" if tier == "MEDIUM"
            else "ENHANCED_REVIEW_REQUIRED"
        ),
        "concerns": (
            ["Counterparty jurisdiction monitored under FATF guidance"]
            if country in ("medium", "high", "very-high") else []
        ),
        "_demo_stub": True,
    }


@router.post("/stub/orbis/embedded-finance-score")
async def embedded_finance_score(req: dict = Body(...)):
    frameworks = int(req.get("complianceFrameworks", 0))
    kyc = req.get("kycAmlLevel", "basic")
    volume = float(req.get("monthlyVolume", 0))
    api_ms = int(req.get("apiResponseMs", 500))
    err_rate = float(req.get("errorRate", 0.01))
    enc = req.get("encryptionLevel", "tls")

    compliance = 40 + frameworks * 8 + {"none": 0, "basic": 5, "standard": 15, "enhanced": 25}.get(kyc, 5)
    security = 50 + {"none": 0, "tls": 10, "aes256": 25, "aes256-fips": 35}.get(enc, 10)
    perf = max(20, 100 - api_ms // 5 - int(err_rate * 1000))
    juris = 70 if volume < 10_000_000 else 60

    overall = (compliance + security + perf + juris) // 4
    overall = max(20, min(95, overall))
    tier = "WEAK" if overall < 50 else "ADEQUATE" if overall < 70 else "STRONG"

    return {
        "score": overall,
        "tier": tier,
        "complianceScore": min(100, compliance),
        "securityScore": min(100, security),
        "factors": [
            {"category": "compliance", "score": min(100, compliance)},
            {"category": "security", "score": min(100, security)},
            {"category": "performance", "score": perf},
            {"category": "jurisdiction", "score": juris},
        ],
        "recommendations": [
            f"KYC/AML level: {kyc} — {'meets enterprise standard' if kyc == 'enhanced' else 'consider upgrading'}",
            f"Encryption: {enc} — {'FIPS-validated' if enc == 'aes256-fips' else 'baseline'}",
            f"API performance: {api_ms}ms p50 — {'strong' if api_ms < 300 else 'acceptable'}",
        ],
        "_demo_stub": True,
    }
