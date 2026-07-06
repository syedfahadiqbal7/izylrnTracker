"""i18n foundation: translations.updated_at + menu_items + seed (Sprint 11)

Adds admin-managed localization + dynamic navigation:
  * `translations.updated_at` — surfaces the last edit in the localization editor.
  * `menu_items` — the Web Admin sidebar (and later mobile nav) rendered from the DB,
    so admins create/reorder/show-hide items and restrict them by role from the panel.

Seeds the initial en/hi/ar strings (nav labels, common actions, panel chrome) and the
current sidebar as menu rows. Idempotent: DDL is `IF NOT EXISTS`, seeds use
`ON CONFLICT DO NOTHING`, so a fresh `alembic upgrade head` (schema.sql already made the
tables) only inserts the seed and re-running never duplicates.
"""
from __future__ import annotations

from alembic import op
from sqlalchemy import text

revision = "0012_i18n_and_menus"
down_revision = "0011_child_location_consent"
branch_labels = None
depends_on = None


# (key, en, hi, ar)
TRANSLATIONS: list[tuple[str, str, str, str]] = [
    # ---- navigation (label_key of each menu_items row) ----
    ("nav.dashboard", "Dashboard", "डैशबोर्ड", "لوحة التحكم"),
    ("nav.tracking", "Live Tracking", "लाइव ट्रैकिंग", "التتبع المباشر"),
    ("nav.attendance", "Attendance", "उपस्थिति", "الحضور"),
    ("nav.reports", "Reports", "रिपोर्ट", "التقارير"),
    ("nav.roster", "Roster", "छात्र सूची", "قائمة الطلاب"),
    ("nav.routes", "Routes & Buses", "रूट और बसें", "المسارات والحافلات"),
    ("nav.drivers", "Drivers", "ड्राइवर", "السائقون"),
    ("nav.audit", "Audit", "ऑडिट लॉग", "سجل التدقيق"),
    ("nav.menus", "Menu Management", "मेन्यू प्रबंधन", "إدارة القوائم"),
    ("nav.settings", "Settings", "सेटिंग्स", "الإعدادات"),
    # ---- panel chrome ----
    ("app.panel_name", "School Admin Panel", "स्कूल एडमिन पैनल", "لوحة إدارة المدرسة"),
    ("app.administrator", "Administrator", "प्रशासक", "المسؤول"),
    ("app.staff", "Staff", "स्टाफ", "الموظفون"),
    ("app.sign_out", "Sign out", "साइन आउट", "تسجيل الخروج"),
    ("app.signing_out", "Signing out…", "साइन आउट हो रहा है…", "جارٍ تسجيل الخروج…"),
    ("app.language", "Language", "भाषा", "اللغة"),
    # ---- common actions / states ----
    ("common.save", "Save", "सहेजें", "حفظ"),
    ("common.saving", "Saving…", "सहेजा जा रहा है…", "جارٍ الحفظ…"),
    ("common.cancel", "Cancel", "रद्द करें", "إلغاء"),
    ("common.add", "Add", "जोड़ें", "إضافة"),
    ("common.edit", "Edit", "संपादित करें", "تعديل"),
    ("common.delete", "Delete", "हटाएं", "حذف"),
    ("common.search", "Search", "खोजें", "بحث"),
    ("common.loading", "Loading…", "लोड हो रहा है…", "جارٍ التحميل…"),
    ("common.actions", "Actions", "क्रियाएँ", "الإجراءات"),
    ("common.confirm", "Confirm", "पुष्टि करें", "تأكيد"),
    ("common.close", "Close", "बंद करें", "إغلاق"),
    ("common.of", "of", "में से", "من"),
    ("common.none", "None", "कोई नहीं", "لا شيء"),
    # ---- dashboard ----
    ("dashboard.title", "Dashboard", "डैशबोर्ड", "لوحة التحكم"),
    ("dashboard.welcome", "Welcome back", "वापसी पर स्वागत है", "مرحبًا بعودتك"),
    # ---- settings / localization / menu management ----
    ("settings.title", "Settings", "सेटिंग्स", "الإعدادات"),
    ("settings.localization", "Localization", "स्थानीयकरण", "الأقلمة"),
    (
        "settings.localization_desc",
        "Manage translations for every language. Changes apply across the panel.",
        "हर भाषा के लिए अनुवाद प्रबंधित करें। बदलाव पूरे पैनल पर लागू होते हैं।",
        "إدارة الترجمات لكل لغة. تُطبَّق التغييرات على اللوحة بأكملها.",
    ),
    ("localization.key", "Key", "कुंजी", "المفتاح"),
    ("localization.add_key", "Add key", "कुंजी जोड़ें", "إضافة مفتاح"),
    ("menus.title", "Menu Management", "मेन्यू प्रबंधन", "إدارة القوائم"),
    (
        "menus.desc",
        "Create, reorder, show or hide navigation items and restrict them by role.",
        "नेविगेशन आइटम बनाएँ, क्रम बदलें, दिखाएँ/छिपाएँ और भूमिका के अनुसार सीमित करें।",
        "أنشئ عناصر التنقل وأعد ترتيبها وأظهرها أو أخفها وقيّدها حسب الدور.",
    ),
    ("menus.label", "Label", "लेबल", "التسمية"),
    ("menus.icon", "Icon", "आइकन", "الأيقونة"),
    ("menus.path", "Path", "पथ", "المسار"),
    ("menus.roles", "Roles", "भूमिकाएँ", "الأدوار"),
    ("menus.visible", "Visible", "दृश्यमान", "مرئي"),
    ("menus.hidden", "Hidden", "छिपा हुआ", "مخفي"),
]

# (item_key, label_key, icon, path, sort_order, visible, roles_json)
MENU_ITEMS: list[tuple[str, str, str, str, int, bool, str]] = [
    ("dashboard", "nav.dashboard", "LayoutDashboard", "/", 10, True, '["admin","staff"]'),
    ("tracking", "nav.tracking", "MapPin", "/tracking", 20, True, '["admin","staff"]'),
    ("attendance", "nav.attendance", "ClipboardCheck", "/attendance", 30, True, '["admin","staff"]'),
    ("reports", "nav.reports", "FileBarChart", "/reports", 40, True, '["admin","staff"]'),
    ("roster", "nav.roster", "Users", "/roster", 50, True, '["admin","staff"]'),
    ("routes", "nav.routes", "Route", "/routes", 60, True, '["admin","staff"]'),
    ("drivers", "nav.drivers", "Truck", "/drivers", 70, True, '["admin","staff"]'),
    ("audit", "nav.audit", "ScrollText", "/audit", 80, True, '["admin"]'),
    ("menus", "nav.menus", "ListTree", "/menus", 90, True, '["admin"]'),
    ("settings", "nav.settings", "Settings", "/settings", 100, True, '["admin","staff"]'),
]


def upgrade() -> None:
    op.execute(
        "ALTER TABLE translations "
        "ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()"
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS menu_items (
            id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            item_key    VARCHAR(60)  NOT NULL UNIQUE,
            label_key   VARCHAR(120) NOT NULL,
            icon        VARCHAR(40),
            path        VARCHAR(120) NOT NULL,
            platform    VARCHAR(10)  NOT NULL DEFAULT 'web' CHECK (platform IN ('web','mobile')),
            sort_order  INTEGER      NOT NULL DEFAULT 0,
            visible     BOOLEAN      NOT NULL DEFAULT TRUE,
            roles       JSONB        NOT NULL DEFAULT '["admin","staff"]'::jsonb,
            created_at  TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
            updated_at  TIMESTAMPTZ  NOT NULL DEFAULT NOW()
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_menu_items_platform ON menu_items (platform, sort_order)"
    )

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
    op.execute("DROP TABLE IF EXISTS menu_items")
    op.execute("ALTER TABLE translations DROP COLUMN IF EXISTS updated_at")
