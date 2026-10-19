"""Seed hi/ar i18n for the parent-app enrollment consent screen (enroll.*).

No DDL. Idempotent (ON CONFLICT DO NOTHING).
"""
from __future__ import annotations

from alembic import op
from sqlalchemy import text

revision = "0024_enroll_consent_i18n"
down_revision = "0023_new_screens_i18n_seed"
branch_labels = None
depends_on = None

# (key, en, hi, ar)
TRANSLATIONS: list[tuple[str, str, str, str]] = [
    ("enroll.title", "School requests", "स्कूल अनुरोध", "طلبات المدرسة"),
    ("enroll.desc",
     "Schools that have added your child. Approve to let a school see them, and choose what to share.",
     "जिन स्कूलों ने आपके बच्चे को जोड़ा है। स्कूल को देखने की अनुमति दें और चुनें कि क्या साझा करना है।",
     "المدارس التي أضافت طفلك. وافق للسماح للمدرسة برؤيته واختر ما تشاركه."),
    ("enroll.empty", "No school requests yet.", "अभी कोई स्कूल अनुरोध नहीं।",
     "لا توجد طلبات مدرسة بعد."),
    ("enroll.visibility", "Let the school see this student", "स्कूल को यह छात्र देखने दें",
     "السماح للمدرسة برؤية هذا الطالب"),
    ("enroll.visibility_hint", "Turn on to approve the enrollment.",
     "नामांकन स्वीकृत करने के लिए चालू करें।", "فعّل للموافقة على التسجيل."),
    ("enroll.share_location", "Share live location", "लाइव स्थान साझा करें",
     "مشاركة الموقع المباشر"),
    ("enroll.bus_tracking", "Bus tracking", "बस ट्रैकिंग", "تتبع الحافلة"),
    ("enroll.consented", "Approved", "स्वीकृत", "تمت الموافقة"),
    ("enroll.pending", "Pending", "लंबित", "قيد الانتظار"),
    ("enroll.save_error", "Could not update. Please try again.",
     "अपडेट नहीं हो सका। कृपया पुनः प्रयास करें।", "تعذّر التحديث. حاول مرة أخرى."),
    ("enroll.pending_count", "pending approval", "स्वीकृति लंबित", "بانتظار الموافقة"),
    ("enroll.manage_hint", "Manage school visibility & consent",
     "स्कूल दृश्यता और सहमति प्रबंधित करें", "إدارة ظهور المدرسة والموافقة"),
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
