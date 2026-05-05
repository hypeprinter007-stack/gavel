import os

import requests as _requests

from x402 import x402ClientSync
from x402.mechanisms.evm.exact import ExactEvmClientScheme
from x402.mechanisms.evm.signers import EthAccountSigner
from x402.http.clients.requests import x402_requests
from eth_account import Account

TREASURY_KEY = os.getenv("TREASURY_PRIVATE_KEY", "")


def _session() -> _requests.Session:
    acct = Account.from_key(TREASURY_KEY)
    signer = EthAccountSigner(acct)
    client = x402ClientSync()
    client.register("eip155:8453", ExactEvmClientScheme(signer))
    return x402_requests(client)


_TIMEOUT = 15


def ofac_screen(vendor_name: str, vendor_wallet: str, vendor_country: str, amount_usd: float) -> dict:
    resp = _session().post(
        "https://mru-oracle.com/compliance/travel-rule",
        json={
            "originator": {
                "address": Account.from_key(TREASURY_KEY).address,
                "name": "Acme Corp",
                "country_code": "US",
            },
            "beneficiary": {
                "address": vendor_wallet,
                "name": vendor_name,
                "country_code": vendor_country,
            },
            "amount_usd": amount_usd,
            "purpose": "trade settlement",
        },
        timeout=_TIMEOUT,
    )
    resp.raise_for_status()
    return resp.json()


def trade_finance_risk(amount_usd: float, country_risk: str = "medium") -> dict:
    resp = _session().post(
        "https://orbisapi.com/proxy/trade-finance-risk-score-api-d53631/score",
        json={
            "transactionValueUsd": amount_usd,
            "buyerCountryRisk": country_risk,
            "paymentTerm": "open-account",
            "tenorDays": 30,
            "buyerCreditRating": "BBB",
        },
        timeout=_TIMEOUT,
    )
    resp.raise_for_status()
    return resp.json()


def embedded_finance_score(jurisdiction: str = "other") -> dict:
    resp = _session().post(
        "https://orbisapi.com/proxy/embedded-finance-score-api-a69119/analyze",
        json={
            "complianceFrameworks": 3,
            "kycAmlLevel": "enhanced",
            "monthlyVolume": 5000000,
            "apiResponseMs": 250,
            "jurisdiction": jurisdiction,
            "errorRate": 0.002,
            "encryptionLevel": "aes256-fips",
        },
        timeout=_TIMEOUT,
    )
    resp.raise_for_status()
    return resp.json()
