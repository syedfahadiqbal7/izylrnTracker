"""Subscription plan catalog (Sprint 6 Slice 1).

The purchasable-plan source of truth for the API: pricing (INR for India, AED for the
UAE — Decision A), headline features, and the tier limits shown on the paywall. Kept in
code (Decision B) — prices change rarely and there's no admin UI until the web admin
(Sprint 9+).

NB this is the **display** catalog. The *enforcement* limits live next to each feature
(`CHILD_LIMITS`, `GEOFENCE_LIMITS`, `GUARDIAN_LIMITS`, the per-feature tier sets); the
numbers here mirror CLAUDE.md §10 and are drift-guarded by a test that cross-checks them
against those enforcement constants. `None` in a limit = unlimited.
"""
from __future__ import annotations

from dataclasses import dataclass

# Currency chosen by country (Decision A): UAE → AED, everyone else → INR.
CURRENCY_BY_COUNTRY = {"+971": "AED"}
DEFAULT_CURRENCY = "INR"

TIER_ORDER = ["free", "basic", "premium", "school"]


def currency_for_country(country_code: str | None) -> str:
    return CURRENCY_BY_COUNTRY.get(country_code or "", DEFAULT_CURRENCY)


@dataclass(frozen=True)
class Plan:
    tier: str
    name: str
    # Monthly price in MAJOR units per currency (₹99, AED9). None = custom/contact sales.
    price: dict[str, int | None]
    purchasable: bool           # Free can't be bought; School is contractual (contact sales)
    features: list[str]
    limits: dict[str, int | None]  # children, devices_per_child, history_days, geofences, guardians
    billing_period: str | None = "month"

    def price_for(self, currency: str) -> int | None:
        return self.price.get(currency)


def _limits(children, devices, history, geofences, guardians) -> dict[str, int | None]:
    return {
        "children": children,
        "devices_per_child": devices,
        "history_days": history,
        "geofences": geofences,
        "guardians": guardians,
    }


# Ordered catalog (mirrors CLAUDE.md §10).
PLANS: dict[str, Plan] = {
    "free": Plan(
        tier="free",
        name="Free",
        price={"INR": 0, "AED": 0},
        purchasable=False,
        billing_period=None,
        features=["1 child", "1 device", "24-hour history", "1 safe zone", "Live location & SOS"],
        limits=_limits(1, 1, 1, 1, 0),
    ),
    "basic": Plan(
        tier="basic",
        name="Basic",
        price={"INR": 99, "AED": 9},
        purchasable=True,
        features=[
            "Up to 3 children", "2 devices per child", "7-day history", "5 safe zones",
            "2 guardians", "Sound Around", "Two-way Call", "School Mode", "Speed Alert",
        ],
        limits=_limits(3, 2, 7, 5, 2),
    ),
    "premium": Plan(
        tier="premium",
        name="Premium",
        price={"INR": 199, "AED": 19},
        purchasable=True,
        features=[
            "Unlimited children", "3 devices per child", "30-day history",
            "Unlimited safe zones", "5 guardians", "Safe Routes", "Polygon zones",
            "Emergency Contacts", "Teen Mode", "Everything in Basic",
        ],
        limits=_limits(None, 3, 30, None, 5),
    ),
    "school": Plan(
        tier="school",
        name="School",
        price={"INR": None, "AED": None},
        purchasable=False,   # contact sales — contractual/custom
        billing_period=None,
        features=[
            "500+ students", "90-day history", "Web dashboard", "Attendance",
            "Bus tracking", "Teacher accounts",
        ],
        limits=_limits(None, 2, 90, None, None),
    ),
}


def plan_for_tier(tier: str) -> Plan | None:
    return PLANS.get(tier)


def purchasable_plans() -> list[Plan]:
    return [PLANS[t] for t in TIER_ORDER if PLANS[t].purchasable]
