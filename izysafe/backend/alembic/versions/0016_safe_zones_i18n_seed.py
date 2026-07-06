"""Seed i18n strings for the parent-app Safe Zones (geofences) screen (Sprint 11, Slice 5)

zones.* (list + editor: shape, radius, notify enter/exit, tier gating) + zonetype.* labels
in en/hi/ar. Idempotent (ON CONFLICT DO NOTHING).
"""
from __future__ import annotations

from alembic import op
from sqlalchemy import text

revision = "0016_safe_zones_i18n_seed"
down_revision = "0015_settings_i18n_seed"
branch_labels = None
depends_on = None

# (key, en, hi, ar)
TRANSLATIONS: list[tuple[str, str, str, str]] = [
    ("zones.title", "Safe zones", "सुरक्षित क्षेत्र", "المناطق الآمنة"),
    ("zones.add", "Add zone", "क्षेत्र जोड़ें", "إضافة منطقة"),
    ("zones.empty", "No safe zones yet", "अभी कोई सुरक्षित क्षेत्र नहीं", "لا توجد مناطق آمنة بعد"),
    ("zones.empty_hint", "Add a zone to get alerts when your child enters or leaves.",
     "अपने बच्चे के आने या जाने पर अलर्ट पाने के लिए एक क्षेत्र जोड़ें।",
     "أضف منطقة لتصلك تنبيهات عند دخول طفلك أو خروجه."),
    ("zones.new", "New safe zone", "नया सुरक्षित क्षेत्र", "منطقة آمنة جديدة"),
    ("zones.edit", "Edit zone", "क्षेत्र संपादित करें", "تعديل المنطقة"),
    ("zones.name", "Zone name", "क्षेत्र का नाम", "اسم المنطقة"),
    ("zones.name_hint", "e.g. Home, School", "उदा. घर, स्कूल", "مثال: المنزل، المدرسة"),
    ("zones.name_required", "Please name the zone.", "कृपया क्षेत्र का नाम दें।",
     "يرجى تسمية المنطقة."),
    ("zones.type", "Type", "प्रकार", "النوع"),
    ("zones.shape", "Shape", "आकार", "الشكل"),
    ("zones.circle", "Circle", "वृत्त", "دائرة"),
    ("zones.polygon", "Polygon", "बहुभुज", "مضلّع"),
    ("zones.points", "points", "बिंदु", "نقاط"),
    ("zones.radius", "Radius", "त्रिज्या", "نصف القطر"),
    ("zones.undo", "Undo", "पूर्ववत करें", "تراجع"),
    ("zones.clear", "Clear", "साफ़ करें", "مسح"),
    ("zones.color", "Colour", "रंग", "اللون"),
    ("zones.tap_center", "Tap the map to set the centre", "केंद्र सेट करने के लिए मानचित्र पर टैप करें",
     "انقر على الخريطة لتعيين المركز"),
    ("zones.tap_points", "Tap the map to add points", "बिंदु जोड़ने के लिए मानचित्र पर टैप करें",
     "انقر على الخريطة لإضافة نقاط"),
    ("zones.center_required", "Tap the map to set the centre.", "केंद्र सेट करने के लिए मानचित्र पर टैप करें।",
     "انقر على الخريطة لتعيين المركز."),
    ("zones.min_points", "Add at least 3 points.", "कम से कम 3 बिंदु जोड़ें।",
     "أضف 3 نقاط على الأقل."),
    ("zones.polygon_premium", "Polygon zones are a Premium feature.",
     "बहुभुज क्षेत्र एक प्रीमियम सुविधा है।", "المناطق المضلّعة ميزة مميّزة."),
    ("zones.notify_enter", "Alert on enter", "प्रवेश पर अलर्ट", "تنبيه عند الدخول"),
    ("zones.notify_enter_desc", "Notify me when my child arrives.",
     "मेरे बच्चे के पहुँचने पर मुझे सूचित करें।", "أعلمني عند وصول طفلي."),
    ("zones.notify_exit", "Alert on exit", "निकास पर अलर्ट", "تنبيه عند الخروج"),
    ("zones.notify_exit_desc", "Notify me when my child leaves.",
     "मेरे बच्चे के जाने पर मुझे सूचित करें।", "أعلمني عند مغادرة طفلي."),
    ("zones.active", "Zone active", "क्षेत्र सक्रिय", "المنطقة نشطة"),
    ("zones.enter", "Enter", "प्रवेश", "دخول"),
    ("zones.exit", "Exit", "निकास", "خروج"),
    ("zones.muted", "Muted", "म्यूट", "صامت"),
    ("zones.paused", "Paused", "रुका हुआ", "متوقّف"),
    ("zones.delete_confirm", "Delete this safe zone?", "इस सुरक्षित क्षेत्र को हटाएं?",
     "حذف هذه المنطقة الآمنة؟"),
    # zone types
    ("zonetype.home", "Home", "घर", "المنزل"),
    ("zonetype.school", "School", "स्कूल", "المدرسة"),
    ("zonetype.tuition", "Tuition", "ट्यूशन", "الدروس"),
    ("zonetype.grandparents", "Grandparents", "दादा-दादी", "الأجداد"),
    ("zonetype.sports", "Sports", "खेल", "الرياضة"),
    ("zonetype.other", "Other", "अन्य", "أخرى"),
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
