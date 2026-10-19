"""Seed the Parents admin screen: nav + page i18n + the sidebar menu item (Model 1).

Adds the `parents` menu_items row (admin-only, between Roster and Routes) and its
en/hi/ar strings. No DDL. Idempotent (ON CONFLICT DO NOTHING).
"""
from __future__ import annotations

from alembic import op
from sqlalchemy import text

revision = "0021_parents_menu_seed"
down_revision = "0020_chat_i18n_seed"
branch_labels = None
depends_on = None

# (key, en, hi, ar)
TRANSLATIONS: list[tuple[str, str, str, str]] = [
    ("nav.parents", "Parents", "अभिभावक", "أولياء الأمور"),
    ("parents.title", "Parents", "अभिभावक", "أولياء الأمور"),
    ("parents.desc",
     "Parents of your enrolled students. Removing a parent from the school revokes their app access.",
     "आपके नामांकित छात्रों के अभिभावक। किसी अभिभावक को स्कूल से हटाने पर उनकी ऐप पहुँच समाप्त हो जाती है।",
     "أولياء أمور طلابك المسجّلين. إزالة ولي الأمر من المدرسة تلغي وصوله إلى التطبيق."),
    ("parents.parent", "Parent", "अभिभावक", "ولي الأمر"),
    ("parents.phone", "Phone", "फ़ोन", "الهاتف"),
    ("parents.students", "Students", "छात्र", "الطلاب"),
    ("parents.last_login", "Last sign-in", "अंतिम साइन-इन", "آخر تسجيل دخول"),
    ("parents.never", "Never", "कभी नहीं", "أبدًا"),
    ("parents.no_name", "No name set", "कोई नाम नहीं", "لا يوجد اسم"),
    ("parents.edit_name", "Edit name", "नाम संपादित करें", "تعديل الاسم"),
    ("parents.remove", "Remove from school", "स्कूल से हटाएँ", "إزالة من المدرسة"),
    ("parents.remove_title", "Remove parent", "अभिभावक हटाएँ", "إزالة ولي الأمر"),
    ("parents.remove_desc",
     "Remove this parent and their students from the school? Their app access is revoked once they have no active enrollment. History is kept.",
     "इस अभिभावक और उनके छात्रों को स्कूल से हटाएँ? सक्रिय नामांकन न रहने पर उनकी ऐप पहुँच समाप्त हो जाती है। इतिहास सुरक्षित रहता है।",
     "إزالة ولي الأمر وطلابه من المدرسة؟ يُلغى وصوله إلى التطبيق عندما لا يتبقى تسجيل نشط. يُحتفظ بالسجل."),
    ("parents.empty", "No parents yet.", "अभी कोई अभिभावक नहीं।", "لا يوجد أولياء أمور بعد."),
    ("parents.search", "Name or phone…", "नाम या फ़ोन…", "الاسم أو الهاتف…"),
    ("parents.load_error", "Failed to load parents.", "अभिभावक लोड नहीं हो सके।",
     "تعذّر تحميل أولياء الأمور."),
]

# (item_key, label_key, icon, path, sort_order, visible, roles)
MENU_ITEMS: list[tuple[str, str, str, str, int, bool, str]] = [
    ("parents", "nav.parents", "UsersRound", "/parents", 55, True, '["admin"]'),
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
    for item_key, label_key, icon, path, order, visible, roles in MENU_ITEMS:
        conn.execute(
            text(
                "INSERT INTO menu_items (item_key, label_key, icon, path, sort_order, visible, roles) "
                "VALUES (:ik, :lk, :ic, :p, :o, :v, CAST(:r AS jsonb)) "
                "ON CONFLICT (item_key) DO NOTHING"
            ),
            {"ik": item_key, "lk": label_key, "ic": icon, "p": path, "o": order, "v": visible, "r": roles},
        )


def downgrade() -> None:
    conn = op.get_bind()
    conn.execute(text("DELETE FROM menu_items WHERE item_key = 'parents'"))
    keys = [t[0] for t in TRANSLATIONS]
    conn.execute(text("DELETE FROM translations WHERE key = ANY(:keys)"), {"keys": keys})
