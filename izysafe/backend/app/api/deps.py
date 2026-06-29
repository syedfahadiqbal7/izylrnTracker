"""Shared FastAPI dependencies.

Gateways are provided via dependencies so tests can override them with fakes
through app.dependency_overrides. get_current_user arrives in the next slice.
"""
from __future__ import annotations

from app.services.otp_gateway import OtpGateway


def get_otp_gateway() -> OtpGateway:
    return OtpGateway()
