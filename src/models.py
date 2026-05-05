from pydantic import BaseModel
from typing import Literal, Optional


class DiligenceRequest(BaseModel):
    vendor_name: str
    vendor_country: str
    vendor_wallet: str
    officer_email: Optional[str] = None
    amount_usd: float = 50000


Decision = Literal["APPROVED", "REJECTED"]


class OfficerSignRequest(BaseModel):
    signature: str
    decision: Decision
    notes: Optional[str] = None
    # If signer_pubkey is provided, signature is treated as Ed25519 (Solana wallet);
    # otherwise it's verified as EIP-191 personal_sign and the signer address
    # is recovered server-side.
    signer_pubkey: Optional[str] = None
