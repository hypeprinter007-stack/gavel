import os

from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI
from mangum import Mangum

from .routes.diligence import router as diligence_router
from .routes.officer import router as officer_router

app = FastAPI(title="Counsel", description="Decision integrity layer for institutional AI agents")

TREASURY = os.getenv("TREASURY_ADDRESS", "")

from x402.http.middleware.fastapi import payment_middleware, RouteConfig
from x402.http import HTTPFacilitatorClient, FacilitatorConfig, PaymentOption
from x402.server import x402ResourceServer
from .services.cdp_auth import _build_cdp_auth_provider

facilitator = HTTPFacilitatorClient(
    FacilitatorConfig(
        url="https://api.cdp.coinbase.com/platform/v2/x402",
        auth_provider=_build_cdp_auth_provider(),
    )
)
from x402.mechanisms.evm.exact import ExactEvmServerScheme

x402_server = x402ResourceServer(facilitator_clients=facilitator)
x402_server.register("eip155:8453", ExactEvmServerScheme())

x402_routes = {
    "POST /v1/diligence": RouteConfig(
        accepts=PaymentOption(
            scheme="exact",
            pay_to=TREASURY,
            price="$0.05",
            network="eip155:8453",
        ),
        description="Vendor due diligence — $0.05 USDC",
    ),
}


@app.middleware("http")
async def x402_mw(request, call_next):
    return await payment_middleware(x402_routes, x402_server)(request, call_next)


@app.get("/health")
def health():
    return {"status": "ok", "service": "counsel"}


app.include_router(diligence_router, prefix="/v1")
app.include_router(officer_router, prefix="/v1")

handler = Mangum(app)
