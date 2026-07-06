"""Seed i18n strings for the parent-app Devices (pairing & management) screens
(Sprint 11, Device Pairing slice).

devices.* keys for the device list + pair/edit forms (name, IMEI/QR, type, thresholds,
online/battery status, tier + error messages) in en/hi/ar. No DDL — the `devices` table
already carries every column this feature uses. Idempotent (ON CONFLICT DO NOTHING).
"""
from __future__ import annotations

from alembic import op
from sqlalchemy import text

revision = "0017_devices_i18n_seed"
down_revision = "0016_safe_zones_i18n_seed"
branch_labels = None
depends_on = None

# (key, en, hi, ar)
TRANSLATIONS: list[tuple[str, str, str, str]] = [
    ("devices.title", "Devices", "डिवाइस", "الأجهزة"),
    ("devices.add", "Add device", "डिवाइस जोड़ें", "إضافة جهاز"),
    ("devices.empty", "No devices yet", "अभी कोई डिवाइस नहीं", "لا توجد أجهزة بعد"),
    ("devices.empty_hint", "Pair a watch or tracker to see your child's live location.",
     "अपने बच्चे का लाइव लोकेशन देखने के लिए एक वॉच या ट्रैकर जोड़ें।",
     "أضف ساعة أو جهاز تتبّع لرؤية موقع طفلك المباشر."),
    ("devices.new", "Pair a device", "डिवाइस जोड़ें", "إقران جهاز"),
    ("devices.edit", "Edit device", "डिवाइस संपादित करें", "تعديل الجهاز"),
    ("devices.name", "Device name", "डिवाइस का नाम", "اسم الجهاز"),
    ("devices.name_hint", "e.g. Aryan's Watch", "उदा. आर्यन की वॉच", "مثال: ساعة أريان"),
    ("devices.name_required", "Please name the device.", "कृपया डिवाइस का नाम दें।",
     "يرجى تسمية الجهاز."),
    ("devices.imei", "IMEI", "IMEI", "IMEI"),
    ("devices.imei_hint", "Enter or scan the IMEI printed on the device.",
     "डिवाइस पर छपा IMEI दर्ज करें या स्कैन करें।",
     "أدخل أو امسح رقم IMEI المطبوع على الجهاز."),
    ("devices.imei_required", "Please enter the device IMEI.", "कृपया डिवाइस का IMEI दर्ज करें।",
     "يرجى إدخال رقم IMEI للجهاز."),
    ("devices.scan", "Scan QR code", "QR कोड स्कैन करें", "مسح رمز QR"),
    ("devices.type", "Device type", "डिवाइस प्रकार", "نوع الجهاز"),
    ("devices.type_watch", "Watch", "वॉच", "ساعة"),
    ("devices.type_bag_tracker", "Bag tracker", "बैग ट्रैकर", "جهاز تتبّع الحقيبة"),
    ("devices.type_phone", "Phone", "फ़ोन", "هاتف"),
    ("devices.model", "Model", "मॉडल", "الطراز"),
    ("devices.color", "Colour", "रंग", "اللون"),
    ("devices.online", "Online", "ऑनलाइन", "متصل"),
    ("devices.offline", "Offline", "ऑफ़लाइन", "غير متصل"),
    ("devices.active", "Active", "सक्रिय", "نشط"),
    ("devices.battery", "Battery", "बैटरी", "البطارية"),
    ("devices.last_seen", "Last seen", "अंतिम बार देखा गया", "آخر ظهور"),
    ("devices.never_seen", "Not connected yet", "अभी तक कनेक्ट नहीं हुआ", "لم يتّصل بعد"),
    ("devices.battery_threshold", "Low-battery alert at", "लो-बैटरी अलर्ट पर",
     "تنبيه انخفاض البطارية عند"),
    ("devices.watch_removed", "Watch-removed alert", "वॉच हटाने का अलर्ट", "تنبيه إزالة الساعة"),
    ("devices.watch_removed_desc", "Alert me if the watch is taken off.",
     "वॉच उतारे जाने पर मुझे सूचित करें।", "أعلمني إذا تمّت إزالة الساعة."),
    ("devices.removed_threshold", "Alert after", "इसके बाद अलर्ट करें", "التنبيه بعد"),
    ("devices.minutes", "min", "मिनट", "دقيقة"),
    ("devices.pairing", "Pairing…", "जोड़ा जा रहा है…", "جارٍ الإقران…"),
    ("devices.paired", "Device paired", "डिवाइस जोड़ा गया", "تمّ إقران الجهاز"),
    ("devices.save", "Save", "सहेजें", "حفظ"),
    ("devices.remove", "Remove device", "डिवाइस हटाएं", "إزالة الجهاز"),
    ("devices.remove_confirm", "Remove this device?", "इस डिवाइस को हटाएं?", "إزالة هذا الجهاز؟"),
    ("devices.imei_taken", "A device with this IMEI already exists.",
     "इस IMEI वाला डिवाइस पहले से मौजूद है।", "يوجد جهاز بهذا الرقم IMEI بالفعل."),
    ("devices.limit_reached", "You've reached your plan's device limit for this child.",
     "आपने इस बच्चे के लिए अपने प्लान की डिवाइस सीमा पूरी कर ली है।",
     "لقد وصلت إلى حدّ الأجهزة في باقتك لهذا الطفل."),
    ("devices.pending_hint", "Live tracking starts once the device powers on and connects.",
     "डिवाइस चालू होकर कनेक्ट होते ही लाइव ट्रैकिंग शुरू हो जाएगी।",
     "يبدأ التتبّع المباشر بمجرّد تشغيل الجهاز واتّصاله."),
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
