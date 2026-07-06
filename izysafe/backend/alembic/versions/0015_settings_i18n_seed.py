"""Seed i18n strings for the parent-app Settings screen (Sprint 11, Slice 4)

Profile / family / notification (quiet hours) / language / emergency-contacts / plan /
logout strings in en/hi/ar, plus plan.* tier + status labels. Idempotent (ON CONFLICT).
"""
from __future__ import annotations

from alembic import op
from sqlalchemy import text

revision = "0015_settings_i18n_seed"
down_revision = "0014_i18n_pages_and_alerts_seed"
branch_labels = None
depends_on = None

# (key, en, hi, ar)
TRANSLATIONS: list[tuple[str, str, str, str]] = [
    # section headers
    ("settings.family", "Family & children", "परिवार और बच्चे", "العائلة والأطفال"),
    ("settings.notifications", "Notifications", "सूचनाएँ", "الإشعارات"),
    ("settings.emergency_contacts", "Emergency contacts", "आपातकालीन संपर्क",
     "جهات اتصال الطوارئ"),
    ("settings.plan", "Plan", "योजना", "الخطة"),
    # profile
    ("settings.edit_profile", "Edit profile", "प्रोफ़ाइल संपादित करें", "تعديل الملف الشخصي"),
    ("settings.name", "Name", "नाम", "الاسم"),
    ("settings.email", "Email", "ईमेल", "البريد الإلكتروني"),
    # notifications / quiet hours
    ("settings.quiet_hours", "Quiet hours", "शांत घंटे", "ساعات الهدوء"),
    ("settings.quiet_hours_desc", "Mute non-urgent alerts during set hours.",
     "निर्धारित घंटों में गैर-जरूरी अलर्ट म्यूट करें।",
     "كتم التنبيهات غير العاجلة خلال ساعات محددة."),
    ("settings.change_hours", "Change hours", "घंटे बदलें", "تغيير الساعات"),
    ("settings.quiet_from", "Mute from", "इससे म्यूट करें", "كتم من"),
    ("settings.quiet_to", "Mute until", "इस तक म्यूट करें", "كتم حتى"),
    ("settings.sos_always", "SOS emergency alerts always come through.",
     "एसओएस आपातकालीन अलर्ट हमेशा आते हैं।", "تنبيهات الطوارئ SOS تصل دائمًا."),
    # emergency contacts
    ("settings.emergency_premium", "Emergency contacts are a Premium feature.",
     "आपातकालीन संपर्क एक प्रीमियम सुविधा है।", "جهات اتصال الطوارئ ميزة مميّزة."),
    ("settings.emergency_premium_hint",
     "Upgrade to add trusted contacts who are alerted on an SOS.",
     "एसओएस पर सूचित होने वाले विश्वसनीय संपर्क जोड़ने के लिए अपग्रेड करें।",
     "قم بالترقية لإضافة جهات اتصال موثوقة يتم تنبيهها عند SOS."),
    ("settings.no_emergency", "No emergency contacts yet.", "अभी कोई आपातकालीन संपर्क नहीं।",
     "لا توجد جهات اتصال طوارئ بعد."),
    # plan
    ("settings.renews", "Renews", "नवीनीकरण", "يتجدد"),
    ("settings.manage_plan", "Manage", "प्रबंधित करें", "إدارة"),
    ("settings.coming_soon", "Plan management is coming soon.",
     "योजना प्रबंधन जल्द आ रहा है।", "إدارة الخطة قادمة قريبًا."),
    # logout
    ("settings.logout_confirm", "Sign out of izyLrn on this device?",
     "इस डिवाइस पर izyLrn से साइन आउट करें?", "تسجيل الخروج من izyLrn على هذا الجهاز؟"),
    # plan tier + status labels
    ("plan.free", "Free", "मुफ़्त", "مجاني"),
    ("plan.basic", "Basic", "बेसिक", "أساسي"),
    ("plan.premium", "Premium", "प्रीमियम", "مميّز"),
    ("plan.status_active", "Active", "सक्रिय", "نشط"),
    ("plan.status_past_due", "Payment due", "भुगतान बाकी", "دفعة مستحقة"),
    ("plan.status_cancelled", "Cancelled", "रद्द", "ملغى"),
    ("plan.status_expired", "Expired", "समाप्त", "منتهي"),
    ("plan.status_free", "Free plan", "मुफ़्त योजना", "خطة مجانية"),
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
