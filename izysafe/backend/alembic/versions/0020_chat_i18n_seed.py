"""Seed i18n strings for the parent-app Chat screen (Sprint 11, Chat slice, F23).

chat.* keys for the parent↔watch message thread (title, empty state, composer hint,
watch label, tier gate + errors) in en/hi/ar. No DDL. Idempotent (ON CONFLICT DO NOTHING).
"""
from __future__ import annotations

from alembic import op
from sqlalchemy import text

revision = "0020_chat_i18n_seed"
down_revision = "0019_polish_i18n_seed"
branch_labels = None
depends_on = None

# (key, en, hi, ar)
TRANSLATIONS: list[tuple[str, str, str, str]] = [
    ("chat.title", "Chat", "चैट", "الدردشة"),
    ("chat.subtitle", "Message the watch", "वॉच को संदेश भेजें", "راسل الساعة"),
    ("chat.empty", "No messages yet", "अभी कोई संदेश नहीं", "لا توجد رسائل بعد"),
    ("chat.empty_hint", "Send a short message to your child's watch.",
     "अपने बच्चे की वॉच पर एक छोटा संदेश भेजें।", "أرسل رسالة قصيرة إلى ساعة طفلك."),
    ("chat.hint", "Type a message…", "एक संदेश लिखें…", "اكتب رسالة…"),
    ("chat.watch", "Watch", "वॉच", "الساعة"),
    ("chat.requires_basic", "Upgrade to Basic plan to use chat.",
     "चैट का उपयोग करने के लिए बेसिक प्लान लें।", "قم بالترقية إلى الباقة الأساسية لاستخدام الدردشة."),
    ("chat.load_error", "Could not load messages.", "संदेश लोड नहीं हो सके।",
     "تعذّر تحميل الرسائل."),
    ("chat.send_error", "Could not send the message.", "संदेश नहीं भेजा जा सका।",
     "تعذّر إرسال الرسالة."),
    # message status labels (for accessibility / future use)
    ("chat.queued", "Queued", "कतारबद्ध", "في قائمة الانتظار"),
    ("chat.sent", "Sent", "भेजा गया", "تم الإرسال"),
    ("chat.delivered", "Delivered", "वितरित", "تم التسليم"),
    ("chat.failed", "Failed", "विफल", "فشل"),
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
