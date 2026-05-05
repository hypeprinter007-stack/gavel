import os

import httpx

TREASURY_KEY = os.getenv("TREASURY_PRIVATE_KEY", "")
TREASURY_ADDR = os.getenv("TREASURY_ADDRESS", "")


def _x402_pay_and_fetch(url: str, method: str, payload: dict) -> dict:
    from x402.client import Client
    from eth_account import Account

    acct = Account.from_key(TREASURY_KEY)
    client = Client(acct)

    if method == "POST":
        resp = client.post(url, json=payload)
    else:
        resp = client.get(url, params=payload)

    resp.raise_for_status()
    return resp.json()


def ofac_screen(vendor_name: str, vendor_wallet: str, vendor_country: str, amount_usd: float) -> dict:
    return _x402_pay_and_fetch(
        "https://mru-oracle.com/compliance/travel-rule",
        "POST",
        {
            "originator": {"address": TREASURY_ADDR, "name": "Acme Corp", "country_code": "US"},
            "beneficiary": {"address": vendor_wallet, "name": vendor_name, "country_code": vendor_country},
            "amount_usd": amount_usd,
            "purpose": "trade settlement",
        },
    )


def trade_finance_risk(amount_usd: float, country_risk: str = "medium") -> dict:
    return _x402_pay_and_fetch(
        "https://orbisapi.com/proxy/trade-finance-risk-score-api-d53631/score",
        "POST",
        {
            "transactionValueUsd": amount_usd,
            "buyerCountryRisk": country_risk,
            "paymentTerm": "open-account",
            "tenorDays": 30,
            "buyerCreditRating": "BBB",
        },
    )


def embedded_finance_score(jurisdiction: str = "other") -> dict:
    return _x402_pay_and_fetch(
        "https://orbisapi.com/proxy/embedded-finance-score-api-a69119/analyze",
        "POST",
        {
            "complianceFrameworks": 3,
            "kycAmlLevel": "enhanced",
            "monthlyVolume": 5000000,
            "apiResponseMs": 250,
            "jurisdiction": jurisdiction,
            "errorRate": 0.002,
            "encryptionLevel": "aes256-fips",
        },
    )
