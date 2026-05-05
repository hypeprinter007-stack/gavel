from pydantic import BaseModel
from typing import Optional


class DiligenceRequest(BaseModel):
    vendor_name: str
    vendor_country: str
    vendor_wallet: str
    officer_email: Optional[str] = None
    amount_usd: float = 50000


class OfficerSignRequest(BaseModel):
    signature: str
    decision: str  # "approve" | "reject"
    notes: Optional[str] = None
