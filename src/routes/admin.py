"""Admin endpoints for the institutional officer registry.

Auth: bearer token via ADMIN_API_KEY env var. Without it set, all
endpoints return 503 — fail closed instead of fail open.
"""
from typing import Literal, Optional

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel

from services import customer_registry, officer_registry, secrets

router = APIRouter()


def _admin_api_key() -> str:
    return secrets.get("admin_api_key", env_fallback="ADMIN_API_KEY")


def _require_admin(authorization: Optional[str] = Header(None)) -> None:
    expected = _admin_api_key()
    if not expected:
        raise HTTPException(status_code=503, detail="Admin API not configured")
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing bearer token")
    token = authorization[len("Bearer ") :]
    # constant-time comparison to deter token-length / timing inference
    import hmac
    if not hmac.compare_digest(token, expected):
        raise HTTPException(status_code=403, detail="Invalid admin token")


class OfficerRegistration(BaseModel):
    signer: str
    scheme: Literal["eip712", "ed25519"]
    label: Optional[str] = ""
    tenant: Optional[str] = None  # defaults to DEFAULT_TENANT


@router.post("/admin/officers", dependencies=[Depends(_require_admin)])
async def register_officer(req: OfficerRegistration):
    item = officer_registry.register_officer(
        signer=req.signer,
        scheme=req.scheme,
        tenant=req.tenant or officer_registry.DEFAULT_TENANT,
        label=req.label or "",
    )
    return {"registered": True, "officer": item}


@router.delete("/admin/officers/{signer}", dependencies=[Depends(_require_admin)])
async def revoke_officer(signer: str, tenant: Optional[str] = None):
    deleted = officer_registry.revoke_officer(
        signer=signer,
        tenant=tenant or officer_registry.DEFAULT_TENANT,
    )
    return {"revoked": deleted}


@router.get("/admin/officers", dependencies=[Depends(_require_admin)])
async def list_officers(tenant: Optional[str] = None):
    items = officer_registry.list_officers(
        tenant=tenant or officer_registry.DEFAULT_TENANT,
    )
    return {"tenant": tenant or officer_registry.DEFAULT_TENANT, "officers": items}


# ───────────── Customer registry ─────────────


class CustomerRegistration(BaseModel):
    customer_name: str
    customer_country: str  # ISO 3166-1 alpha-2
    tenant: Optional[str] = None  # auto-slugged from customer_name if omitted


@router.post("/admin/customers", dependencies=[Depends(_require_admin)])
async def create_customer(req: CustomerRegistration):
    """Register a new customer. Returns the API key ONCE — store it
    immediately, it cannot be retrieved later."""
    result = customer_registry.register_customer(
        customer_name=req.customer_name,
        customer_country=req.customer_country,
        tenant=req.tenant,
    )
    rec = result["customer"]
    return {
        "api_key": result["api_key"],
        "customer": {
            "tenant": rec["tenant"],
            "customer_name": rec["customer_name"],
            "customer_country": rec["customer_country"],
            "key_hash": rec["key_hash"],
            "status": rec["status"],
            "created_at": rec["created_at"],
        },
        "warning": "API key shown once and never retrievable. Store it in your secret manager now.",
    }


@router.get("/admin/customers", dependencies=[Depends(_require_admin)])
async def list_customers():
    items = customer_registry.list_customers()
    # Return key_hash (used to identify the row) but never the key itself.
    return {"customers": [
        {k: v for k, v in c.items() if k not in ("pk", "type")}
        for c in items
    ]}


@router.delete("/admin/customers/{key_hash}", dependencies=[Depends(_require_admin)])
async def revoke_customer(key_hash: str):
    revoked = customer_registry.revoke(key_hash)
    return {"revoked": revoked}
