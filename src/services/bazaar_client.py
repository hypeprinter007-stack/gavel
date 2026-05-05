import os

import requests as _requests

from x402 import x402ClientSync
from x402.mechanisms.evm.exact import ExactEvmClientScheme
from x402.mechanisms.evm.signers import EthAccountSigner
from x402.http.clients.requests import x402_requests
from eth_account import Account

from services import secrets


def _treasury_key() -> str:
    return secrets.get("treasury_evm_key", env_fallback="TREASURY_PRIVATE_KEY")
MRU_TRAVEL_RULE_URL = os.getenv("MRU_TRAVEL_RULE_URL", "https://mru-oracle.com/compliance/travel-rule")
ORBIS_TRADE_URL = os.getenv("ORBIS_TRADE_URL", "https://orbisapi.com/proxy/trade-finance-risk-score-api-d53631/score")
ORBIS_EMBEDDED_URL = os.getenv("ORBIS_EMBEDDED_URL", "https://orbisapi.com/proxy/embedded-finance-score-api-a69119/analyze")
ORIGINATOR_NAME = os.getenv("ORIGINATOR_NAME", "Counsel Demo Client")
ORIGINATOR_COUNTRY = os.getenv("ORIGINATOR_COUNTRY", "US")

# FATF risk categorization for trade-finance buyer-country-risk enum.
# References: FATF Public Statement (high-risk + monitored jurisdictions),
# OFAC sanctions program list. ISO 3166-1 alpha-2 codes.
_FATF_HIGH_RISK = {"IR", "KP", "MM"}                 # call for action
_FATF_MONITORED = {"AE", "BG", "BF", "CM", "HR", "CD", "HT", "JM", "ML",
                   "MZ", "NG", "PA", "PH", "SN", "SS", "SY", "TZ", "TR",
                   "UG", "VE", "VN", "YE"}            # increased monitoring
_FATF_LOW_RISK = {"US", "GB", "DE", "FR", "JP", "CA", "AU", "NL", "SE",
                  "CH", "SG", "DK", "NO", "FI", "NZ", "IE", "AT"}

_JURISDICTION_BUCKETS = {
    "us": "us", "ca": "us",
    "gb": "uk",
    "de": "eu", "fr": "eu", "nl": "eu", "es": "eu", "it": "eu",
    "se": "eu", "dk": "eu", "fi": "eu", "no": "eu", "ie": "eu",
    "at": "eu", "be": "eu", "pt": "eu", "pl": "eu",
    "sg": "apac", "jp": "apac", "hk": "apac", "au": "apac",
    "kr": "apac", "tw": "apac", "nz": "apac",
}


def _country_risk(iso2: str) -> str:
    code = (iso2 or "").upper()
    if code in _FATF_HIGH_RISK:
        return "very-high"
    if code in _FATF_MONITORED:
        return "medium"
    if code in _FATF_LOW_RISK:
        return "low"
    return "medium"


def _jurisdiction_bucket(iso2: str) -> str:
    return _JURISDICTION_BUCKETS.get((iso2 or "").lower(), "other")


_cached_session: _requests.Session | None = None
_cached_treasury_address: str | None = None


def _session() -> _requests.Session:
    """Lazy-init x402 session; reused across calls in the same Lambda container."""
    global _cached_session
    if _cached_session is None:
        acct = Account.from_key(_treasury_key())
        signer = EthAccountSigner(acct)
        client = x402ClientSync()
        client.register("eip155:8453", ExactEvmClientScheme(signer))
        _cached_session = x402_requests(client)
    return _cached_session


def _treasury_address() -> str:
    global _cached_treasury_address
    if _cached_treasury_address is None:
        _cached_treasury_address = Account.from_key(_treasury_key()).address
    return _cached_treasury_address


_TIMEOUT = 15


def ofac_screen(vendor_name: str, vendor_wallet: str, vendor_country: str, amount_usd: float) -> dict:
    resp = _session().post(
        MRU_TRAVEL_RULE_URL,
        json={
            "originator": {
                "address": _treasury_address(),
                "name": ORIGINATOR_NAME,
                "country_code": ORIGINATOR_COUNTRY,
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


def trade_finance_risk(amount_usd: float, vendor_country: str = "") -> dict:
    resp = _session().post(
        ORBIS_TRADE_URL,
        json={
            "transactionValueUsd": amount_usd,
            "buyerCountryRisk": _country_risk(vendor_country),
            "paymentTerm": "open-account",
            "tenorDays": 30,
            "buyerCreditRating": "BBB",
        },
        timeout=_TIMEOUT,
    )
    resp.raise_for_status()
    return resp.json()


def embedded_finance_score(vendor_country: str = "") -> dict:
    resp = _session().post(
        ORBIS_EMBEDDED_URL,
        json={
            "complianceFrameworks": 3,
            "kycAmlLevel": "enhanced",
            "monthlyVolume": 5000000,
            "apiResponseMs": 250,
            "jurisdiction": _jurisdiction_bucket(vendor_country),
            "errorRate": 0.002,
            "encryptionLevel": "aes256-fips",
        },
        timeout=_TIMEOUT,
    )
    resp.raise_for_status()
    return resp.json()
