"""Input validators that raise the standard APIException with the exact
user-facing messages from User_Journey.docx (Feature 7)."""
from __future__ import annotations

import re

from app.core.errors import APIException

# +91 then 10 digits starting 6-9  |  +971 then 9 digits starting 5
_IN_RE = re.compile(r"^\+91[6-9]\d{9}$")
_AE_RE = re.compile(r"^\+971[5]\d{8}$")


def validate_phone(phone: str) -> str:
    """Validate + normalize an E.164 phone for the IN/UAE markets.

    Returns the trimmed phone on success; raises APIException(400) with a
    precise message otherwise.
    """
    p = (phone or "").strip().replace(" ", "")

    if not p.startswith("+91") and not p.startswith("+971"):
        raise APIException(
            400, "INVALID_PHONE",
            "Enter a valid Indian (+91) or UAE (+971) mobile number",
        )
    if p.startswith("+971"):
        if not _AE_RE.match(p):
            raise APIException(400, "INVALID_PHONE", "Enter a valid UAE mobile number")
    elif not _IN_RE.match(p):
        raise APIException(
            400, "INVALID_PHONE", "Enter a valid 10-digit Indian mobile number"
        )
    return p
