"""Seed i18n strings for Share Links (Sprint 11, Slice 7).

share.* keys for the parent-app screen (create link, TTL picker, QR + copy, active-link
list with expiry/views/revoke) + track.* keys for the public login-less tracking page,
all in en/hi/ar. No DDL. Idempotent (ON CONFLICT DO NOTHING).
"""
from __future__ import annotations

from alembic import op
from sqlalchemy import text

revision = "0018_share_links_i18n_seed"
down_revision = "0017_devices_i18n_seed"
branch_labels = None
depends_on = None

# (key, en, hi, ar)
TRANSLATIONS: list[tuple[str, str, str, str]] = [
    # ---- parent-app Share Links screen (share.*) ----
    ("share.title", "Share links", "शेयर लिंक", "روابط المشاركة"),
    ("share.subtitle", "Temporary live-tracking links", "अस्थायी लाइव-ट्रैकिंग लिंक",
     "روابط تتبّع مباشر مؤقتة"),
    ("share.create", "Create link", "लिंक बनाएं", "إنشاء رابط"),
    ("share.new", "New share link", "नया शेयर लिंक", "رابط مشاركة جديد"),
    ("share.empty", "No active links", "कोई सक्रिय लिंक नहीं", "لا توجد روابط نشطة"),
    ("share.empty_hint",
     "Create a temporary link to let someone follow your child's live location.",
     "किसी को अपने बच्चे की लाइव लोकेशन दिखाने के लिए एक अस्थायी लिंक बनाएं।",
     "أنشئ رابطًا مؤقتًا للسماح لشخص بمتابعة موقع طفلك المباشر."),
    ("share.duration", "Link duration", "लिंक अवधि", "مدّة الرابط"),
    ("share.duration_hint", "The link stops working after this time.",
     "इस समय के बाद लिंक काम करना बंद कर देगा।", "يتوقّف الرابط عن العمل بعد هذه المدّة."),
    ("share.hour_1", "1 hour", "1 घंटा", "ساعة واحدة"),
    ("share.hour_8", "8 hours", "8 घंटे", "8 ساعات"),
    ("share.hour_24", "24 hours", "24 घंटे", "24 ساعة"),
    ("share.scan", "Scan to open", "खोलने के लिए स्कैन करें", "امسح للفتح"),
    ("share.copy", "Copy link", "लिंक कॉपी करें", "نسخ الرابط"),
    ("share.copied", "Link copied", "लिंक कॉपी हो गया", "تم نسخ الرابط"),
    ("share.open", "Open", "खोलें", "فتح"),
    ("share.created", "Share link created", "शेयर लिंक बन गया", "تمّ إنشاء رابط المشاركة"),
    ("share.expires_in", "Expires in", "समाप्त होगा", "ينتهي خلال"),
    ("share.expired", "Expired", "समाप्त", "منتهي"),
    ("share.views", "views", "बार देखा गया", "مشاهدات"),
    ("share.revoke", "Revoke", "रद्द करें", "إلغاء"),
    ("share.revoke_confirm", "Revoke this link? It will stop working immediately.",
     "इस लिंक को रद्द करें? यह तुरंत काम करना बंद कर देगा।",
     "إلغاء هذا الرابط؟ سيتوقّف عن العمل فورًا."),
    ("share.revoked", "Link revoked", "लिंक रद्द कर दिया", "تمّ إلغاء الرابط"),
    ("share.requires_basic", "Upgrade to Basic plan to share live-tracking links.",
     "लाइव-ट्रैकिंग लिंक शेयर करने के लिए बेसिक प्लान लें।",
     "قم بالترقية إلى الباقة الأساسية لمشاركة روابط التتبّع."),
    ("share.d_left", "d", "दि", "ي"),
    ("share.h_left", "h", "घं", "س"),
    ("share.m_left", "m", "मि", "د"),
    # ---- public tracking page (track.*) ----
    ("track.tracking", "Tracking", "ट्रैकिंग", "تتبّع"),
    ("track.loading", "Loading…", "लोड हो रहा है…", "جارٍ التحميل…"),
    ("track.waiting", "Waiting for a location fix…", "लोकेशन का इंतज़ार…",
     "بانتظار تحديد الموقع…"),
    ("track.updated", "Updated", "अपडेट किया गया", "تم التحديث"),
    ("track.just_now", "just now", "अभी", "الآن"),
    ("track.min_ago", "min ago", "मिनट पहले", "دقيقة مضت"),
    ("track.hr_ago", "h ago", "घंटे पहले", "ساعة مضت"),
    ("track.expires", "Link expires", "लिंक समाप्त होगा", "ينتهي الرابط"),
    ("track.expired_title", "Link expired", "लिंक समाप्त", "انتهى الرابط"),
    ("track.expired", "This tracking link is invalid or has expired.",
     "यह ट्रैकिंग लिंक अमान्य है या समाप्त हो गया है।",
     "رابط التتبّع هذا غير صالح أو منتهي الصلاحية."),
    ("track.busy", "Too many requests — please wait a moment.",
     "बहुत अधिक अनुरोध — कृपया थोड़ी देर रुकें।", "طلبات كثيرة — يرجى الانتظار قليلاً."),
    ("track.error", "Couldn't load tracking right now.",
     "अभी ट्रैकिंग लोड नहीं हो सकी।", "تعذّر تحميل التتبّع الآن."),
    ("track.no_location", "No location shared yet.", "अभी कोई लोकेशन साझा नहीं की गई।",
     "لم تتم مشاركة أيّ موقع بعد."),
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
