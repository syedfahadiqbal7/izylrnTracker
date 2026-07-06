"""Seed parent-app (Flutter) translation strings — Live Map + SOS + common (Sprint 11)

The parent mobile app pulls every string through the same i18n system (GET /i18n/{locale}).
This seeds the Live-Map / bus / SOS / emergency keys it needs in en/hi/ar so the app is
genuinely multilingual out of the box; admins can edit them from the panel afterwards.
Idempotent (ON CONFLICT DO NOTHING).
"""
from __future__ import annotations

from alembic import op
from sqlalchemy import text

revision = "0013_parent_app_i18n_seed"
down_revision = "0012_i18n_and_menus"
branch_labels = None
depends_on = None

# (key, en, hi, ar)
TRANSLATIONS: list[tuple[str, str, str, str]] = [
    # ---- common (parent app) ----
    ("common.retry", "Retry", "पुनः प्रयास करें", "إعادة المحاولة"),
    ("common.call", "Call", "कॉल करें", "اتصال"),
    ("common.today", "Today", "आज", "اليوم"),
    ("app.hi", "Hi", "नमस्ते", "مرحبًا"),
    ("home.children", "children", "बच्चे", "الأطفال"),
    ("home.child", "child", "बच्चा", "طفل"),
    ("home.no_children", "No children linked to your account yet.",
     "आपके खाते से अभी कोई बच्चा नहीं जुड़ा है।", "لا يوجد أطفال مرتبطون بحسابك بعد."),
    ("home.track", "Track live", "लाइव ट्रैक करें", "تتبع مباشر"),
    ("child.devices", "devices", "डिवाइस", "الأجهزة"),
    ("child.device", "device", "डिवाइस", "جهاز"),
    # ---- live map ----
    ("map.title", "Live Location", "लाइव लोकेशन", "الموقع المباشر"),
    ("map.last_seen", "Last seen", "आख़िरी बार देखा गया", "آخر ظهور"),
    ("map.updated", "Updated", "अपडेट किया गया", "تم التحديث"),
    ("map.locating", "Locating…", "स्थान खोजा जा रहा है…", "جارٍ تحديد الموقع…"),
    ("map.no_location", "No live location yet", "अभी कोई लाइव लोकेशन नहीं",
     "لا يوجد موقع مباشر بعد"),
    ("map.no_location_hint", "The tracker will appear here once it reports a position.",
     "ट्रैकर स्थिति रिपोर्ट करते ही यहाँ दिखाई देगा।",
     "سيظهر جهاز التتبع هنا بمجرد إبلاغه عن موقع."),
    ("map.recenter", "Recenter", "पुनः केंद्रित करें", "إعادة التوسيط"),
    ("map.safe_zones", "Safe zones", "सुरक्षित क्षेत्र", "المناطق الآمنة"),
    ("map.child_layer", "Child", "बच्चा", "الطفل"),
    ("map.moments_ago", "moments ago", "कुछ पल पहले", "قبل لحظات"),
    ("map.min_ago", "min ago", "मिनट पहले", "دقيقة مضت"),
    ("map.hr_ago", "hr ago", "घंटे पहले", "ساعة مضت"),
    # ---- bus ----
    ("bus.title", "School Bus", "स्कूल बस", "حافلة المدرسة"),
    ("bus.eta", "ETA", "अनुमानित समय", "الوقت المتوقع"),
    ("bus.min", "min", "मिनट", "دقيقة"),
    ("bus.stop", "Stop", "स्टॉप", "المحطة"),
    ("bus.en_route", "En route", "रास्ते में", "في الطريق"),
    ("bus.off", "Bus tracking is off for this child.",
     "इस बच्चे के लिए बस ट्रैकिंग बंद है।", "تتبع الحافلة متوقف لهذا الطفل."),
    ("bus.no_position", "Bus position not available yet.",
     "बस की स्थिति अभी उपलब्ध नहीं है।", "موقع الحافلة غير متاح بعد."),
    # ---- SOS / emergency ----
    ("sos.active_title", "SOS Emergency", "एसओएस आपातकाल", "حالة طوارئ SOS"),
    ("sos.active_body", "triggered an emergency alert.",
     "ने आपातकालीन अलर्ट भेजा है।", "أطلق تنبيه طوارئ."),
    ("sos.triggered", "Triggered", "ट्रिगर किया गया", "تم التفعيل"),
    ("sos.approximate", "Approximate location", "अनुमानित स्थान", "موقع تقريبي"),
    ("sos.resolve", "Resolve emergency", "आपातकाल हल करें", "إنهاء الطوارئ"),
    ("sos.resolving", "Resolving…", "हल किया जा रहा है…", "جارٍ الإنهاء…"),
    ("sos.all_clear", "No active emergencies", "कोई सक्रिय आपातकाल नहीं",
     "لا توجد حالات طوارئ نشطة"),
    ("emergency.button", "Emergency", "आपातकाल", "طوارئ"),
    ("emergency.title", "Emergency options", "आपातकालीन विकल्प", "خيارات الطوارئ"),
    ("emergency.call_services", "Call emergency services", "आपातकालीन सेवाओं को कॉल करें",
     "الاتصال بخدمات الطوارئ"),
    ("emergency.confirm", "This will place a phone call. Continue?",
     "इससे फ़ोन कॉल की जाएगी। जारी रखें?", "سيؤدي هذا إلى إجراء مكالمة هاتفية. متابعة؟"),
]


def upgrade() -> None:
    conn = op.get_bind()
    for key, en, hi, ar in TRANSLATIONS:
        conn.execute(
            text(
                "INSERT INTO translations (key, en, hi, ar) VALUES (:k, :en, :hi, :ar) "
                "ON CONFLICT (key) DO NOTHING"
            ),
            {"k": key, "en": en, "hi": hi, "ar": ar},
        )


def downgrade() -> None:
    conn = op.get_bind()
    keys = [t[0] for t in TRANSLATIONS]
    conn.execute(text("DELETE FROM translations WHERE key = ANY(:keys)"), {"keys": keys})
