"""Pydantic v2 request/response schemas for the auth endpoints.

Phone-format and OTP-format validation is done in the service layer (via
app.core.validators) so we can return the exact User-Journey error codes/messages
through the standard envelope, rather than Pydantic's 422 shape.
"""
from __future__ import annotations

from pydantic import BaseModel, Field


# ---- /auth/send-otp ----
class SendOtpRequest(BaseModel):
    phone: str = Field(..., examples=["+919876543210"])


class SendOtpResponse(BaseModel):
    success: bool = True
    expires_in: int                 # seconds until OTP expiry
    channel: str                    # "whatsapp" | "sms"


# ---- /auth/verify-otp (next slice) ----
class VerifyOtpRequest(BaseModel):
    phone: str = Field(..., examples=["+919876543210"])
    otp: str = Field(..., examples=["123456"])


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    is_new_user: bool = False


# ---- /auth/refresh (next slice) ----
class RefreshRequest(BaseModel):
    refresh_token: str
