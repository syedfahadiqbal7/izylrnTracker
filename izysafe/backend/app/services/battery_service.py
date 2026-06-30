"""Battery alerts — a per-position check kept off the request hot path (§4).

Runs in a webhook BackgroundTask. Reads the device fresh (so a parent's threshold
change takes effect immediately), persists `last_battery` only when it changed, and
fires at most one alert per level per 4h:

  * critical_battery  when battery ≤ critical threshold (default 5%)
  * low_battery       when battery ≤ the device's configurable `battery_threshold`

Debounce (`battery_alerted:{device_id}`) stores the last level alerted so a drain
from low→critical still escalates, while repeats stay quiet. Recharging above the
threshold clears the marker so the next drain alerts fresh.
"""
from __future__ import annotations

import logging
import uuid
from collections.abc import Callable

from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import redis_keys as rk
from app.core.config import settings
from app.models.device import Device
from app.services.alert_service import AlertService
from app.services.fcm_gateway import FcmGateway

logger = logging.getLogger("izysafe.battery")

_TITLES = {
    "low": "Low battery",
    "critical": "Critical battery",
}


def _body(level: str, device_name: str, battery: int) -> str:
    if level == "critical":
        return f"{device_name} battery critically low ({battery}%). Charge now."
    return f"{device_name} battery is low ({battery}%). Charge soon."


class BatteryService:
    def __init__(
        self,
        session_factory: Callable[[], AsyncSession],
        redis: Redis,
        fcm: FcmGateway,
    ) -> None:
        self.session_factory = session_factory
        self.redis = redis
        self.fcm = fcm

    async def evaluate(self, device_id: uuid.UUID, battery: int) -> None:
        async with self.session_factory() as session:
            device = await session.get(Device, device_id)
            if device is None or device.deleted_at is not None:
                return

            level = self._level(battery, device.battery_threshold)
            debounce = await self.redis.get(rk.battery_alerted(device_id))
            fire = self._should_fire(level, debounce)

            if level is None and debounce is not None:
                await self.redis.delete(rk.battery_alerted(device_id))  # recharged → reset

            changed = device.last_battery != battery
            if changed:
                device.last_battery = battery

            if fire:
                await AlertService(session, self.fcm).notify_family(
                    device.child_id,
                    f"{fire}_battery",
                    _TITLES[fire],
                    _body(fire, device.name, battery),
                    {"device_id": str(device_id), "battery": battery},
                )

            if changed or fire:
                await session.commit()

        if fire:
            await self.redis.set(
                rk.battery_alerted(device_id), fire, ex=settings.battery_alert_cooldown_seconds
            )
            logger.info("Battery %s alert for device %s (%d%%)", fire, device_id, battery)

    @staticmethod
    def _level(battery: int, threshold: int) -> str | None:
        if battery <= settings.battery_critical_threshold:
            return "critical"
        if battery <= threshold:
            return "low"
        return None

    @staticmethod
    def _should_fire(level: str | None, debounce: str | None) -> str | None:
        """Fire critical on escalation (debounce not already critical); fire low only
        when nothing is currently debounced."""
        if level == "critical" and debounce != "critical":
            return "critical"
        if level == "low" and debounce is None:
            return "low"
        return None
