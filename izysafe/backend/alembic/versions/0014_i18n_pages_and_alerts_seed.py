"""Seed i18n strings for the web-admin page refactor + Flutter auth + Alerts (Sprint 11)

Adds the translation keys wired up during the full i18n pass (login/audit/reports/
attendance/roster/drivers/routes page chrome), the Flutter auth screens, and the parent
Alerts inbox (Slice 3), each in en/hi/ar. Idempotent (ON CONFLICT DO NOTHING) — admins can
edit any of these from the Localization panel afterwards.
"""
from __future__ import annotations

from alembic import op
from sqlalchemy import text

revision = "0014_i18n_pages_and_alerts_seed"
down_revision = "0013_parent_app_i18n_seed"
branch_labels = None
depends_on = None

# (key, en, hi, ar)
TRANSLATIONS: list[tuple[str, str, str, str]] = [
    # ---- common (web admin) ----
    ("common.error_generic", "Something went wrong. Please try again.",
     "कुछ गलत हो गया। कृपया पुनः प्रयास करें।", "حدث خطأ ما. يرجى المحاولة مرة أخرى."),
    ("common.email", "Email", "ईमेल", "البريد الإلكتروني"),
    ("common.password", "Password", "पासवर्ड", "كلمة المرور"),
    ("common.all", "All", "सभी", "الكل"),
    ("common.date_range", "Date range", "तिथि सीमा", "النطاق الزمني"),
    ("common.previous", "Previous", "पिछला", "السابق"),
    ("common.next", "Next", "अगला", "التالي"),
    ("common.all_classes", "All classes", "सभी कक्षाएँ", "كل الفصول"),
    # ---- login ----
    ("login.subtitle", "School Admin — sign in to your dashboard",
     "स्कूल एडमिन — अपने डैशबोर्ड में साइन इन करें", "مشرف المدرسة — سجّل الدخول إلى لوحتك"),
    ("login.incorrect", "Incorrect email or password.",
     "गलत ईमेल या पासवर्ड।", "بريد إلكتروني أو كلمة مرور غير صحيحة."),
    ("login.signing_in", "Signing in…", "साइन इन हो रहा है…", "جارٍ تسجيل الدخول…"),
    ("login.sign_in", "Sign in", "साइन इन करें", "تسجيل الدخول"),
    # ---- audit ----
    ("audit.title", "Audit Log", "ऑडिट लॉग", "سجل التدقيق"),
    ("audit.trail", "The school's activity trail.", "स्कूल की गतिविधि का रिकॉर्ड।",
     "سجل نشاط المدرسة."),
    ("audit.admin_only", "The audit log is available to administrators only.",
     "ऑडिट लॉग केवल प्रशासकों के लिए उपलब्ध है।", "سجل التدقيق متاح للمسؤولين فقط."),
    ("audit.desc", "Every recorded action in your school, newest first.",
     "आपके स्कूल की हर दर्ज गतिविधि, नवीनतम पहले।", "كل إجراء مسجّل في مدرستك، الأحدث أولًا."),
    ("audit.export", "Export CSV", "CSV निर्यात करें", "تصدير CSV"),
    ("audit.export_error", "Could not export the log.", "लॉग निर्यात नहीं हो सका।",
     "تعذّر تصدير السجل."),
    ("audit.actor", "Actor", "कर्ता", "الفاعل"),
    ("audit.action", "Action", "कार्य", "الإجراء"),
    ("audit.entity", "Entity", "इकाई", "الكيان"),
    ("audit.admin", "Admin", "प्रशासक", "مسؤول"),
    ("audit.parent", "Parent", "अभिभावक", "ولي الأمر"),
    ("audit.when", "When", "कब", "متى"),
    ("audit.details", "Details", "विवरण", "التفاصيل"),
    ("audit.no_results", "No audit entries match these filters.",
     "इन फ़िल्टर से मेल खाने वाली कोई ऑडिट प्रविष्टि नहीं।",
     "لا توجد إدخالات تدقيق تطابق هذه المرشحات."),
    ("audit.load_error", "Failed to load the audit log.", "ऑडिट लॉग लोड नहीं हो सका।",
     "فشل تحميل سجل التدقيق."),
    # ---- reports / attendance ----
    ("reports.title", "Attendance Report", "उपस्थिति रिपोर्ट", "تقرير الحضور"),
    ("reports.desc", "Date-range summary and per-student rollup across the attendance register.",
     "उपस्थिति रजिस्टर का तिथि-सीमा सारांश और प्रति-छात्र योग।",
     "ملخص حسب النطاق الزمني وتجميع لكل طالب من سجل الحضور."),
    ("attendance.title", "Daily Attendance", "दैनिक उपस्थिति", "الحضور اليومي"),
    ("attendance.desc", "The register for a single day — every consented student's status.",
     "एक दिन का रजिस्टर — हर सहमत छात्र की स्थिति।",
     "سجل ليوم واحد — حالة كل طالب موافَق عليه."),
    # ---- roster ----
    ("roster.title", "Roster", "छात्र सूची", "قائمة الطلاب"),
    ("roster.desc",
     "Enrolled students, parent contacts, and consent status. Assign students to bus stops under Routes & Buses.",
     "नामांकित छात्र, अभिभावक संपर्क और सहमति स्थिति। रूट और बसें में छात्रों को बस स्टॉप सौंपें।",
     "الطلاب المسجّلون وجهات اتصال الأهل وحالة الموافقة. عيّن الطلاب لمحطات الحافلات ضمن المسارات والحافلات."),
    ("roster.search_name", "Student name…", "छात्र का नाम…", "اسم الطالب…"),
    ("roster.empty", "No students enrolled yet.", "अभी कोई छात्र नामांकित नहीं।",
     "لا يوجد طلاب مسجّلون بعد."),
    # ---- drivers / routes ----
    ("drivers.title", "Drivers", "ड्राइवर", "السائقون"),
    ("drivers.desc", "Bus drivers for your school, their access codes, and login activity.",
     "आपके स्कूल के बस ड्राइवर, उनके एक्सेस कोड और लॉगिन गतिविधि।",
     "سائقو حافلات مدرستك ورموز الوصول الخاصة بهم ونشاط تسجيل الدخول."),
    ("drivers.empty", "No drivers yet. Add your first driver to get started.",
     "अभी कोई ड्राइवर नहीं। शुरू करने के लिए अपना पहला ड्राइवर जोड़ें।",
     "لا يوجد سائقون بعد. أضف أول سائق للبدء."),
    ("routes.title", "Routes & Buses", "रूट और बसें", "المسارات والحافلات"),
    ("routes.desc", "Bus devices, routes, stops, and student assignments.",
     "बस डिवाइस, रूट, स्टॉप और छात्र असाइनमेंट।", "أجهزة الحافلات والمسارات والمحطات وتعيينات الطلاب."),
    # ---- Flutter auth screens ----
    ("auth.enter_phone", "Enter your phone number", "अपना फ़ोन नंबर दर्ज करें",
     "أدخل رقم هاتفك"),
    ("auth.welcome", "Welcome to izyLrn", "izyLrn में आपका स्वागत है", "مرحبًا بك في izyLrn"),
    ("auth.tagline", "Keep your children safe, always", "अपने बच्चों को हमेशा सुरक्षित रखें",
     "حافظ على أمان أطفالك دائمًا"),
    ("auth.sign_in", "Sign in", "साइन इन करें", "تسجيل الدخول"),
    ("auth.send_code_sub", "We’ll send a one-time code to your phone.",
     "हम आपके फ़ोन पर एक बार का कोड भेजेंगे।", "سنرسل رمزًا لمرة واحدة إلى هاتفك."),
    ("auth.phone_hint", "Phone number", "फ़ोन नंबर", "رقم الهاتف"),
    ("auth.send_code", "Send code", "कोड भेजें", "إرسال الرمز"),
    ("auth.regions", "India & UAE numbers supported", "भारत और यूएई नंबर समर्थित",
     "أرقام الهند والإمارات مدعومة"),
    ("auth.enter_code", "Enter the code we sent you", "हमने आपको जो कोड भेजा है वह दर्ज करें",
     "أدخل الرمز الذي أرسلناه إليك"),
    ("auth.resent", "A new code has been sent", "एक नया कोड भेजा गया है", "تم إرسال رمز جديد"),
    ("auth.verify_title", "Verify your number", "अपना नंबर सत्यापित करें", "تحقّق من رقمك"),
    ("auth.verify_sub", "Enter the 6-digit code", "6-अंकीय कोड दर्ज करें",
     "أدخل الرمز المكوّن من 6 أرقام"),
    ("auth.sent_to", "Sent to", "भेजा गया", "أُرسل إلى"),
    ("auth.dev_hint",
     "Dev mode: no SMS provider configured — check the backend logs for the code.",
     "डेव मोड: कोई SMS प्रदाता कॉन्फ़िगर नहीं — कोड के लिए बैकएंड लॉग देखें।",
     "وضع التطوير: لا يوجد مزوّد رسائل — تحقّق من سجلات الخادم للحصول على الرمز."),
    ("auth.verify_continue", "Verify & continue", "सत्यापित करें और जारी रखें", "تحقّق وتابع"),
    ("auth.change_number", "Change number", "नंबर बदलें", "تغيير الرقم"),
    ("auth.resend", "Resend code", "कोड पुनः भेजें", "إعادة إرسال الرمز"),
    # ---- Alerts inbox (Slice 3) ----
    ("nav.alerts", "Alerts", "अलर्ट", "التنبيهات"),
    ("alerts.title", "Alerts", "अलर्ट", "التنبيهات"),
    ("alerts.subtitle", "Notifications for your children", "आपके बच्चों के लिए सूचनाएँ",
     "إشعارات عن أطفالك"),
    ("alerts.all", "All", "सभी", "الكل"),
    ("alerts.unread", "Unread", "अपठित", "غير مقروء"),
    ("alerts.mark_all_read", "Mark all read", "सभी को पढ़ा हुआ चिह्नित करें",
     "تعليم الكل كمقروء"),
    ("alerts.mark_read", "Mark read", "पढ़ा हुआ चिह्नित करें", "تعليم كمقروء"),
    ("alerts.empty", "You're all caught up", "आप पूरी तरह अपडेट हैं", "أنت على اطلاع بكل شيء"),
    ("alerts.empty_hint", "New alerts about your children will appear here.",
     "आपके बच्चों के बारे में नए अलर्ट यहाँ दिखाई देंगे।",
     "ستظهر التنبيهات الجديدة عن أطفالك هنا."),
    ("alerts.load_error", "Could not load alerts.", "अलर्ट लोड नहीं हो सके।",
     "تعذّر تحميل التنبيهات."),
    ("alerts.view_on_map", "View on map", "मानचित्र पर देखें", "عرض على الخريطة"),
    # alert type labels (Alert.type) — keyed by the backend's exact type names
    ("alert_type.sos", "SOS Emergency", "एसओएस आपातकाल", "طوارئ SOS"),
    ("alert_type.geofence_enter", "Entered a safe zone", "सुरक्षित क्षेत्र में प्रवेश",
     "دخل منطقة آمنة"),
    ("alert_type.geofence_exit", "Left a safe zone", "सुरक्षित क्षेत्र से बाहर",
     "غادر منطقة آمنة"),
    ("alert_type.school_arrival", "Arrived at school", "स्कूल पहुँच गए", "وصل إلى المدرسة"),
    ("alert_type.school_absent", "Marked absent", "अनुपस्थित चिह्नित", "تم تسجيل الغياب"),
    ("alert_type.low_battery", "Low battery", "कम बैटरी", "بطارية منخفضة"),
    ("alert_type.critical_battery", "Critical battery", "गंभीर बैटरी", "بطارية حرجة"),
    ("alert_type.speed", "Speed alert", "गति अलर्ट", "تنبيه السرعة"),
    ("alert_type.route_deviation", "Off route", "मार्ग से भटका", "خارج المسار"),
    ("alert_type.device_offline", "Tracker offline", "ट्रैकर ऑफ़लाइन", "جهاز التتبع غير متصل"),
    ("alert_type.watch_removed", "Watch removed", "वॉच हटाई गई", "تمت إزالة الساعة"),
    ("alert_type.bus_arrival", "Bus arriving", "बस आ रही है", "الحافلة قادمة"),
    ("alert_type.bus_boarded", "Boarded the bus", "बस में सवार हुए", "ركب الحافلة"),
    ("alert_type.pickup", "Picked up", "पिकअप हुआ", "تم الاصطحاب"),
    ("alert_type.system", "Notification", "सूचना", "إشعار"),
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
