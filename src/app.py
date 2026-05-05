import logging
import os

from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI
from mangum import Mangum

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)

from routes.admin import router as admin_router
from routes.diligence import router as diligence_router
from routes.officer import router as officer_router
from routes.stub import router as stub_router

app = FastAPI(title="Counsel", description="Decision integrity layer for institutional AI agents")

TREASURY = os.getenv("TREASURY_ADDRESS", "")
SOLANA_TREASURY = os.getenv("SOLANA_TREASURY_ADDRESS", "")
SOLANA_MAINNET_CAIP2 = "solana:5eykt4UsFv8P8NJdTREpY1vzqKqZKvdp"

from x402.http.middleware.fastapi import payment_middleware, RouteConfig
from x402.http import HTTPFacilitatorClient, FacilitatorConfig, PaymentOption
from x402.server import x402ResourceServer
from services.cdp_auth import _build_cdp_auth_provider

facilitator = HTTPFacilitatorClient(
    FacilitatorConfig(
        url="https://api.cdp.coinbase.com/platform/v2/x402",
        auth_provider=_build_cdp_auth_provider(),
    )
)
from x402.mechanisms.evm.exact import ExactEvmServerScheme
from x402.mechanisms.svm.exact import register_exact_svm_server

x402_server = x402ResourceServer(facilitator_clients=facilitator)
x402_server.register("eip155:8453", ExactEvmServerScheme())
register_exact_svm_server(x402_server, networks=SOLANA_MAINNET_CAIP2)

_accepts: list[PaymentOption] = [
    PaymentOption(
        scheme="exact",
        pay_to=TREASURY,
        price="$0.05",
        network="eip155:8453",
    ),
]
if SOLANA_TREASURY:
    _accepts.append(
        PaymentOption(
            scheme="exact",
            pay_to=SOLANA_TREASURY,
            price="$0.05",
            network=SOLANA_MAINNET_CAIP2,
        )
    )

x402_routes = {
    "POST /v1/diligence": RouteConfig(
        accepts=_accepts,
        description="Vendor due diligence — $0.05 USDC, settle on Base or Solana",
    ),
}


@app.middleware("http")
async def x402_mw(request, call_next):
    return await payment_middleware(x402_routes, x402_server)(request, call_next)


# Middleware layering note (FastAPI: last registered = outermost):
#   inner ──▶ outer execution order
#   x402_mw ◀ idempotency_mw ◀ api_key_mw   (declared in this order)
# So a request flows: api_key check → idempotency cache → x402 → handler.
# Reasoning: 401 (unauth) before 402 (payment), and 200 (cache hit)
# before 402 — neither should trigger a charge.
import json as _json

from fastapi.responses import JSONResponse, Response
from services import customer_registry, idempotency

ENFORCE_CUSTOMER_AUTH = os.getenv("ENFORCE_CUSTOMER_AUTH", "true").lower() == "true"


@app.middleware("http")
async def idempotency_mw(request, call_next):
    if not (request.method == "POST" and request.url.path == "/v1/diligence"):
        return await call_next(request)

    key = request.headers.get("idempotency-key") or request.headers.get("Idempotency-Key")
    if not key:
        return await call_next(request)

    body = await request.body()
    request_h = idempotency.request_hash(body)

    cached = idempotency.lookup(key)
    if cached:
        if cached.get("request_hash") == request_h:
            return JSONResponse(
                _json.loads(cached["response_body"]),
                status_code=int(cached["status_code"]),
                headers={"Idempotent-Replayed": "true"},
            )
        return JSONResponse(
            {"detail": "Idempotency-Key was previously used with a different payload"},
            status_code=409,
        )

    # New key — let it through, then cache the response on success.
    response = await call_next(request)
    if response.status_code == 200:
        chunks: list[bytes] = []
        async for chunk in response.body_iterator:
            chunks.append(chunk)
        full = b"".join(chunks)
        try:
            idempotency.store(key, request_h, 200, _json.loads(full))
        except Exception:
            pass
        return Response(
            content=full,
            status_code=response.status_code,
            headers=dict(response.headers),
            media_type=response.media_type,
        )
    return response


@app.middleware("http")
async def api_key_mw(request, call_next):
    """Authenticate the requesting institution before x402 charges."""
    if not (request.method == "POST" and request.url.path == "/v1/diligence"):
        return await call_next(request)
    if not ENFORCE_CUSTOMER_AUTH:
        return await call_next(request)

    api_key = request.headers.get("x-counsel-api-key") or request.headers.get("X-Counsel-API-Key")
    if not api_key:
        return JSONResponse(
            {"detail": "Missing X-Counsel-API-Key header. Register a customer via /v1/admin/customers."},
            status_code=401,
        )
    customer = customer_registry.lookup(api_key)
    if not customer:
        return JSONResponse(
            {"detail": "Invalid or revoked customer API key"},
            status_code=401,
        )
    request.state.customer = customer
    return await call_next(request)


@app.get("/health")
def health():
    return {"status": "ok", "service": "counsel"}


app.include_router(diligence_router, prefix="/v1")
app.include_router(officer_router, prefix="/v1")
app.include_router(stub_router, prefix="/v1")
app.include_router(admin_router, prefix="/v1")

handler = Mangum(app)
