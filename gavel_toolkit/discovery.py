"""
gavel_toolkit.discovery — chain-agnostic registry-based router for x402
compliance services.

Usage:
    from gavel_toolkit.discovery import resolve, resolve_and_call

    providers = resolve("travel_rule_compliance")

    # Multi-chain payment — pass keys for whichever chain(s) you can settle on.
    result = resolve_and_call(
        intent="wallet_screening",
        payload={...},
        evm_payer_key="0x...",
        solana_payer_key="<base58 keypair bytes>",
    )
"""

from __future__ import annotations

import json
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


def _is_evm(network: str) -> bool:
    return network.startswith("eip155:")


def _is_solana(network: str) -> bool:
    return network.startswith("solana:")


def _build_session(evm_payer_key: str | None, solana_payer_key: str | None):
    """Construct an x402 client session that can pay on any registered chain."""
    from x402 import x402ClientSync
    from x402.http.clients.requests import x402_requests

    client = x402ClientSync()

    if evm_payer_key:
        from eth_account import Account
        from x402.mechanisms.evm.exact import ExactEvmClientScheme
        from x402.mechanisms.evm.signers import EthAccountSigner
        signer = EthAccountSigner(Account.from_key(evm_payer_key))
        client.register("eip155:8453", ExactEvmClientScheme(signer))

    if solana_payer_key:
        from x402.mechanisms.svm.exact import register_exact_svm_client
        from x402.mechanisms.svm.signers import KeypairSigner
        register_exact_svm_client(client, KeypairSigner.from_base58(solana_payer_key))

    return x402_requests(client)


def resolve_and_call(
    intent: str,
    payload: dict[str, Any],
    evm_payer_key: str | None = None,
    solana_payer_key: str | None = None,
    tags: list[str] | None = None,
    timeout: int = 15,
) -> dict[str, Any]:
    """
    Resolve providers for an intent and execute the first one we can pay for.

    The function tries providers in price-ascending order and skips any whose
    network we don't have a key for (e.g. a Solana provider without
    `solana_payer_key`). Adds `_provider`, `_price_usd`, and `_network` to the
    response.
    """
    if not (evm_payer_key or solana_payer_key):
        raise ValueError("Provide at least one of evm_payer_key or solana_payer_key")

    providers = resolve(intent, tags)
    if not providers:
        raise ValueError(f"No providers registered for intent '{intent}'")

    session = _build_session(evm_payer_key, solana_payer_key)

    last_error: Exception | None = None
    skipped: list[tuple[str, str]] = []
    for provider in providers:
        network = provider.get("network", "")
        if _is_evm(network) and not evm_payer_key:
            skipped.append((provider["id"], "no evm_payer_key"))
            continue
        if _is_solana(network) and not solana_payer_key:
            skipped.append((provider["id"], "no solana_payer_key"))
            continue
        try:
            resp = session.request(
                method=provider["method"],
                url=provider["url"],
                json=payload,
                timeout=timeout,
            )
            resp.raise_for_status()
            result = resp.json()
            result["_provider"] = provider["id"]
            result["_price_usd"] = provider["price_usd"]
            result["_network"] = network
            return result
        except Exception as e:
            last_error = e
            continue

    if not last_error and skipped:
        raise RuntimeError(
            f"All providers for intent '{intent}' skipped (no key for their networks): {skipped}"
        )
    raise RuntimeError(f"All providers for intent '{intent}' failed. Last error: {last_error}")
