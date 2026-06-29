"""User profile operations (partial profile update + FCM token registration)."""
from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.validators import validate_email, validate_timezone
from app.models.user import User


class UserService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def update_profile(self, user: User, fields: dict[str, Any]) -> User:
        """Apply a partial profile update. Only keys present in `fields` are touched."""
        if fields.get("email") is not None:
            fields["email"] = validate_email(fields["email"])
        if fields.get("timezone") is not None:
            validate_timezone(fields["timezone"])

        for key, value in fields.items():
            setattr(user, key, value)

        await self.db.commit()
        await self.db.refresh(user)
        return user

    async def set_fcm_token(self, user: User, token: str) -> None:
        user.fcm_token = token
        await self.db.commit()
