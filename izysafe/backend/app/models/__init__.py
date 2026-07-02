"""Model aggregator.

Importing this package registers every table on Base.metadata so Alembic's
autogenerate (and any metadata.create_all in tests) sees the full schema.
Keep this list in sync when adding a model.
"""
from app.models.base import Base
from app.models.user import User, OtpSession, Subscription
from app.models.child import Child, FamilyMember, Invite
from app.models.device import Device, PairingCode
from app.models.location import Location, Geofence, GeofenceEvent, PickupEvent
from app.models.route import SafeRoute, ShareLink
from app.models.sos import SosEvent, EmergencyContact
from app.models.alert import Alert
from app.models.comms import AudioSession, CallRecord, ChatMessage
from app.models.teen import Trip, CrashEvent
from app.models.integration import IzyLrnLink, WearableIntegration, Translation
from app.models.school import (
    School,
    SchoolAdmin,
    StudentEnrollment,
    AttendanceRecord,
    Driver,
    BusRoute,
    BusRouteStop,
    BusAssignment,
    BusTrip,
    BusBoarding,
)

__all__ = [
    "Base",
    "User", "OtpSession", "Subscription",
    "Child", "FamilyMember", "Invite",
    "Device", "PairingCode",
    "Location", "Geofence", "GeofenceEvent", "PickupEvent",
    "SafeRoute", "ShareLink",
    "SosEvent", "EmergencyContact",
    "Alert",
    "AudioSession", "CallRecord", "ChatMessage",
    "Trip", "CrashEvent",
    "IzyLrnLink", "WearableIntegration", "Translation",
    "School", "SchoolAdmin", "StudentEnrollment", "AttendanceRecord",
    "Driver", "BusRoute", "BusRouteStop", "BusAssignment", "BusTrip", "BusBoarding",
]
