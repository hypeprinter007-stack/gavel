"""Live integration tests — runs against real AWS + Bazaar endpoints."""
import asyncio
import json
import os
import sys

from dotenv import load_dotenv
load_dotenv()

# ── 1. Bedrock ────────────────────────────────────────────────────────────────

def test_bedrock():
    print("\n── Bedrock synthesis ──")
    from src.services.bedrock_client import synthesize
    evidence = {
        "travel_rule": {"compositeRisk": "clear", "recommendation": "PROCEED"},
        "trade_finance_risk": {"score": 60.5, "tier": "elevated-risk"},
        "embedded_finance_score": {"score": 76.5, "tier": "good"},
    }
    output, prompt_hash = synthesize("Northstar Crypto Capital", evidence)
    parsed = json.loads(output)
    print(f"  risk_level:      {parsed.get('risk_level')}")
    print(f"  recommendation:  {parsed.get('recommendation')}")
    print(f"  summary:         {parsed.get('summary', '')[:80]}...")
    print(f"  prompt_hash:     {prompt_hash[:16]}...")
    return True


# ── 2. Bazaar — MRU Travel Rule ───────────────────────────────────────────────

def test_mru():
    print("\n── MRU Travel Rule ──")
    from src.services.bazaar_client import ofac_screen
    result = ofac_screen(
        vendor_name="Northstar Crypto Capital",
        vendor_wallet="0x0360D000622F942b9656D59c679D19d5D12ec989",
        vendor_country="AE",
        amount_usd=50000,
    )
    print(f"  recommendation:  {result.get('recommendation')}")
    print(f"  compositeRisk:   {result.get('compositeRisk')}")
    print(f"  packetId:        {result.get('packetId')}")
    return True


# ── 3. Bazaar — Orbis Trade Finance ──────────────────────────────────────────

def test_orbis_tf():
    print("\n── Orbis Trade Finance ──")
    from src.services.bazaar_client import trade_finance_risk
    result = trade_finance_risk(50000, "medium")
    print(f"  score:  {result.get('score')}")
    print(f"  tier:   {result.get('tier')}")
    return True


# ── 4. Bazaar — Orbis Embedded Finance ───────────────────────────────────────

def test_orbis_ef():
    print("\n── Orbis Embedded Finance ──")
    from src.services.bazaar_client import embedded_finance_score
    result = embedded_finance_score("other")
    print(f"  score:  {result.get('score')}")
    print(f"  tier:   {result.get('tier')}")
    return True


# ── 5. Full diligence flow (bypass x402 — internal test) ─────────────────────

async def test_full_flow():
    print("\n── Full diligence flow ──")
    from fastapi.testclient import TestClient

    # Patch middleware to bypass x402 for internal test
    import src.app as app_module
    original_middleware = None

    from src.routes.diligence import run_diligence
    from src.models import DiligenceRequest

    req = DiligenceRequest(
        vendor_name="Northstar Crypto Capital",
        vendor_country="AE",
        vendor_wallet="0x0360D000622F942b9656D59c679D19d5D12ec989",
        amount_usd=50000,
    )
    result = await run_diligence(req)
    print(f"  session_id:   {result['session_id']}")
    print(f"  synthesis:    {json.dumps(result.get('synthesis', {}), indent=4)[:200]}")
    return True


if __name__ == "__main__":
    tests = [
        ("Bedrock", test_bedrock),
        ("MRU Travel Rule", test_mru),
        ("Orbis Trade Finance", test_orbis_tf),
        ("Orbis Embedded Finance", test_orbis_ef),
    ]

    results = {}
    for name, fn in tests:
        try:
            fn()
            results[name] = "PASS"
        except Exception as e:
            results[name] = f"FAIL: {e}"
            print(f"  ERROR: {e}")

    try:
        asyncio.run(test_full_flow())
        results["Full flow"] = "PASS"
    except Exception as e:
        results["Full flow"] = f"FAIL: {e}"
        print(f"  ERROR: {e}")

    print("\n── Results ──")
    for name, status in results.items():
        icon = "✓" if status == "PASS" else "✗"
        print(f"  {icon} {name}: {status}")
