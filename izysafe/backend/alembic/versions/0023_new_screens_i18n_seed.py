"""Seed hi/ar i18n for the new screens: add-child, SOS popup, profile, plan, devices.

All keys use `t(key, fallback)` so English already works; this adds Hindi + Arabic.
No DDL. Idempotent (ON CONFLICT DO NOTHING) — pre-existing keys are left untouched.
"""
from __future__ import annotations

from alembic import op
from sqlalchemy import text

revision = "0023_new_screens_i18n_seed"
down_revision = "0022_user_profile_fields"
branch_labels = None
depends_on = None

# (key, en, hi, ar)
TRANSLATIONS: list[tuple[str, str, str, str]] = [
    # ---- Add child ----
    ("home.add_child", "Add child", "बच्चा जोड़ें", "إضافة طفل"),
    ("common.add", "Add", "जोड़ें", "إضافة"),
    ("common.optional", "optional", "वैकल्पिक", "اختياري"),
    ("child.name", "Name", "नाम", "الاسم"),
    ("child.name_hint", "e.g. Ahmed", "उदा. अहमद", "مثال: أحمد"),
    ("child.name_too_short", "Enter the child's name", "बच्चे का नाम दर्ज करें", "أدخل اسم الطفل"),
    ("child.class_grade", "Class / grade", "कक्षा / श्रेणी", "الصف / المستوى"),
    ("child.grade_hint", "e.g. Kg1-J", "उदा. Kg1-J", "مثال: Kg1-J"),
    ("child.add_error", "Could not add the child. Please try again.",
     "बच्चा नहीं जोड़ा जा सका। कृपया पुनः प्रयास करें।", "تعذّر إضافة الطفل. حاول مرة أخرى."),
    # ---- SOS popup ----
    ("sos.title", "SOS Emergency", "एसओएस आपातकाल", "طوارئ SOS"),
    ("sos.a_child", "your child", "आपका बच्चा", "طفلك"),
    ("sos.triggered_by", "Emergency alert from", "आपातकालीन अलर्ट:", "تنبيه طارئ من"),
    ("sos.at", "at", "समय", "في"),
    ("sos.approx_location", "approximate location", "अनुमानित स्थान", "موقع تقريبي"),
    ("sos.view_on_map", "View on live map", "लाइव मैप पर देखें", "عرض على الخريطة المباشرة"),
    ("sos.resolve", "Mark as resolved", "हल किया हुआ चिह्नित करें", "وضع علامة كمحلول"),
    ("sos.resolving", "Resolving…", "हल हो रहा है…", "جارٍ الحل…"),
    # ---- Profile / settings ----
    ("settings.edit_profile", "Edit profile", "प्रोफ़ाइल संपादित करें", "تعديل الملف الشخصي"),
    ("settings.name", "Name", "नाम", "الاسم"),
    ("settings.email", "Email", "ईमेल", "البريد الإلكتروني"),
    ("settings.address", "Home address", "घर का पता", "عنوان المنزل"),
    ("settings.address_hint", "Building, street, area, city", "बिल्डिंग, सड़क, क्षेत्र, शहर",
     "المبنى، الشارع، المنطقة، المدينة"),
    ("settings.home_location", "Home location", "घर का स्थान", "موقع المنزل"),
    ("settings.clear_pin", "Clear", "हटाएँ", "مسح"),
    ("settings.tap_map_hint", "Tap the map to drop a pin on your home.",
     "अपने घर पर पिन लगाने के लिए मैप पर टैप करें।", "انقر على الخريطة لتحديد موقع منزلك."),
    ("settings.additional_numbers", "Additional numbers", "अतिरिक्त नंबर", "أرقام إضافية"),
    ("settings.no_numbers", "No extra numbers yet.", "अभी कोई अतिरिक्त नंबर नहीं।",
     "لا توجد أرقام إضافية بعد."),
    ("settings.label", "Label", "लेबल", "التسمية"),
    ("settings.number", "Number", "नंबर", "الرقم"),
    ("settings.save_error", "Could not save. Please try again.",
     "सहेजा नहीं जा सका। कृपया पुनः प्रयास करें।", "تعذّر الحفظ. حاول مرة أخرى."),
    ("settings.load_error", "Could not load your profile.",
     "आपकी प्रोफ़ाइल लोड नहीं हो सकी।", "تعذّر تحميل ملفك الشخصي."),
    ("settings.renews", "Renews", "नवीनीकरण", "يتجدد"),
    ("settings.plan", "Plan", "प्लान", "الباقة"),
    ("common.save", "Save", "सहेजें", "حفظ"),
    ("common.cancel", "Cancel", "रद्द करें", "إلغاء"),
    ("common.remove", "Remove", "हटाएँ", "إزالة"),
    ("common.retry", "Retry", "पुनः प्रयास", "إعادة المحاولة"),
    # ---- Plan management ----
    ("plan.current", "Current plan", "वर्तमान प्लान", "الباقة الحالية"),
    ("plan.month", "mo", "माह", "شهر"),
    ("plan.choose", "Choose", "चुनें", "اختيار"),
    ("plan.contact_sales", "Contact sales", "सेल्स से संपर्क करें", "تواصل مع المبيعات"),
    ("plan.checkout_started", "Checkout started.", "चेकआउट शुरू हुआ।", "بدأ الدفع."),
    ("plan.payments_unavailable",
     "Online payments aren't available yet. Please contact support to upgrade.",
     "ऑनलाइन भुगतान अभी उपलब्ध नहीं है। अपग्रेड के लिए सहायता से संपर्क करें।",
     "المدفوعات عبر الإنترنت غير متاحة بعد. يرجى التواصل مع الدعم للترقية."),
    ("plan.webhook_note", "Your plan updates automatically once payment is confirmed.",
     "भुगतान की पुष्टि होते ही आपका प्लान अपने आप अपडेट हो जाएगा।",
     "تُحدَّث باقتك تلقائيًا بمجرد تأكيد الدفع."),
    ("plan.free", "Free", "निःशुल्क", "مجاني"),
    ("plan.basic", "Basic", "बेसिक", "أساسي"),
    ("plan.premium", "Premium", "प्रीमियम", "بريميوم"),
    ("plan.school", "School", "स्कूल", "مدرسة"),
    # ---- Roster: student devices dialog ----
    ("roster.manage_devices", "Devices", "डिवाइस", "الأجهزة"),
    ("roster.devices_title", "Devices", "डिवाइस", "الأجهزة"),
    ("roster.devices_desc",
     "Trackers the school has provisioned for this student. They appear on Live Tracking once the parent has granted location consent.",
     "इस छात्र के लिए स्कूल द्वारा जोड़े गए ट्रैकर। अभिभावक की स्थान सहमति के बाद ये लाइव ट्रैकिंग पर दिखेंगे।",
     "أجهزة التتبع التي وفّرتها المدرسة لهذا الطالب. تظهر في التتبع المباشر بعد موافقة ولي الأمر على مشاركة الموقع."),
    ("roster.no_devices", "No devices yet.", "अभी कोई डिवाइस नहीं।", "لا توجد أجهزة بعد."),
    ("roster.pair_device", "Pair a device", "डिवाइस जोड़ें", "إقران جهاز"),
    ("roster.device_name", "Device name", "डिवाइस का नाम", "اسم الجهاز"),
    ("roster.eg_tag", "e.g. School bag tracker", "उदा. स्कूल बैग ट्रैकर", "مثال: جهاز تتبع حقيبة المدرسة"),
    ("roster.device_imei", "IMEI", "IMEI", "IMEI"),
    ("roster.imei_hint", "From the tracker / its QR code", "ट्रैकर / उसके QR कोड से",
     "من الجهاز / رمز QR الخاص به"),
    ("roster.add_device", "Add device", "डिवाइस जोड़ें", "إضافة جهاز"),
    ("roster.online", "Online", "ऑनलाइन", "متصل"),
    ("roster.offline", "Offline", "ऑफ़लाइन", "غير متصل"),
    ("roster.remove_device", "Remove device", "डिवाइस हटाएँ", "إزالة الجهاز"),
    ("roster.device_add_error", "Could not add the device.", "डिवाइस नहीं जोड़ा जा सका।",
     "تعذّر إضافة الجهاز."),
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
