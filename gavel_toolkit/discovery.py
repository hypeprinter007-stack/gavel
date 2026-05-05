"""
gavel_toolkit.discovery — registry-based provider router for x402 compliance services.

Usage:
    from gavel_toolkit.discovery import resolve, resolve_and_call

    # Find providers for an intent
    providers = resolve("travel_rule_compliance")

    # Route and pay in one call
    result = resolve_and_call(
        intent="travel_rule_compliance",
        payload={...},
        payer_key="0x...",
    )
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

_REGISTRY_DIR = Path(__file__).parent / "providers"
_registry: list[dict] | None = None


def _load_registry() -> list[dict]:
    global _registry
    if _registry is None:
        _registry = []
        for f in _REGISTRY_DIR.glob("*.json"):
            with open(f) as fh:
                _registry.append(json.load(fh))
    return _registry


def resolve(intent: str, tags: list[str] | None = None) -> list[dict]:
    """Return all providers matching the given intent, optionally filtered by tags."""
    providers = [p for p in _load_registry() if p.get("intent") == intent]
    if tags:
        providers = [
            p for p in providers
            if any(t in p.get("tags", []) for t in tags)
        ]
    return sorted(providers, key=lambda p: p.get("price_usd", 999))


def list_intents() -> list[str]:
    """Return all unique intents registered in the provider registry."""
    return sorted({p["intent"] for p in _load_registry()})


def list_providers() -> list[dict]:
    """Return all registered providers."""
    return _load_registry()


def resolve_and_call(
    intent: str,
    payload: dict[str, Any],
    payer_key: str,
    tags: list[str] | None = None,
) -> dict[str, Any]:
    """
    Resolve the best provider for an intent and execute the x402 call.

    Args:
        intent: The compliance intent (e.g. "travel_rule_compliance")
        payload: Request body to send to the provider
        payer_key: Private key hex string for x402 payment signing
        tags: Optional tag filters to narrow provider selection

    Returns:
        Provider response dict with added _provider and _price_usd fields
    """
    import requests as _requests
    from eth_account import Account
    from x402 import x402ClientSync
    from x402.mechanisms.evm.exact import ExactEvmClientScheme
    from x402.mechanisms.evm.signers import EthAccountSigner
    from x402.http.clients.requests import x402_requests

    providers = resolve(intent, tags)
    if not providers:
        raise ValueError(f"No providers found for intent '{intent}'")

    acct = Account.from_key(payer_key)
    signer = EthAccountSigner(acct)
    client = x402ClientSync()
    client.register("eip155:8453", ExactEvmClientScheme(signer))
    session = x402_requests(client)

    last_error = None
    for provider in providers:
        try:
            resp = session.request(
                method=provider["method"],
                url=provider["url"],
                json=payload,
                timeout=15,
            )
            resp.raise_for_status()
            result = resp.json()
            result["_provider"] = provider["id"]
            result["_price_usd"] = provider["price_usd"]
            return result
        except Exception as e:
            last_error = e
            continue

    raise RuntimeError(f"All providers for intent '{intent}' failed. Last error: {last_error}")
