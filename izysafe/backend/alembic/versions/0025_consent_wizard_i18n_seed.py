"""Seed hi/ar i18n for the parent-app guided consent setup wizard (consent.*).

Covers every `t('consent.*', fallback)` string in the consent wizard plus the
new enrollment entry-point prompt (`enroll.setup_*`) and the missing
`common.back` label. English already works via the in-app fallbacks; this adds
Hindi + Arabic. Placeholders ({school}, {n}, {total}) are preserved verbatim so
the app's `replaceFirst` substitutions keep working in every locale.

No DDL. Idempotent (ON CONFLICT DO NOTHING) — pre-existing keys (e.g.
common.close / common.next) are left untouched.
"""
from __future__ import annotations

from alembic import op
from sqlalchemy import text

revision = "0025_consent_wizard_i18n"
down_revision = "0024_enroll_consent_i18n"
branch_labels = None
depends_on = None

# (key, en, hi, ar)
TRANSLATIONS: list[tuple[str, str, str, str]] = [
    # ---- Enrollment entry point into the wizard ----
    ("enroll.setup_prompt",
     "Review what this school can see and approve it step by step.",
     "देखें कि यह स्कूल क्या देख सकता है और चरण-दर-चरण इसे स्वीकृति दें।",
     "راجع ما يمكن لهذه المدرسة رؤيته ووافق عليه خطوة بخطوة."),
    ("enroll.setup_cta", "Review & approve", "समीक्षा करें और स्वीकृति दें",
     "مراجعة وموافقة"),
    # ---- Shared ----
    ("common.back", "Back", "वापस", "رجوع"),
    # ---- Wizard chrome ----
    ("consent.title", "Set up school access", "स्कूल एक्सेस सेट करें",
     "إعداد وصول المدرسة"),
    ("consent.step_of", "Step {n} of {total}", "चरण {n} / {total}",
     "الخطوة {n} من {total}"),
    # ---- Welcome step ----
    ("consent.welcome_title", "Welcome to {school}", "{school} में आपका स्वागत है",
     "مرحبًا بك في {school}"),
    ("consent.welcome_lead",
     "Your school added your child. In a few quick steps you decide exactly what "
     "to share — from the school seeing your student, to the ride home, to pickup "
     "& drop alerts.",
     "आपके स्कूल ने आपके बच्चे को जोड़ा है। कुछ आसान चरणों में आप तय करते हैं कि वास्तव में "
     "क्या साझा करना है — स्कूल द्वारा आपके छात्र को देखने से लेकर, घर की सवारी, और पिकअप व "
     "ड्रॉप अलर्ट तक।",
     "أضافت مدرستك طفلك. في بضع خطوات سريعة تقرر بالضبط ما تشاركه — من رؤية المدرسة "
     "لطالبك، إلى رحلة العودة إلى المنزل، إلى تنبيهات الاصطحاب والتوصيل."),
    ("consent.welcome_b1", "You are always in control — change or withdraw any time.",
     "नियंत्रण हमेशा आपके पास है — कभी भी बदलें या वापस लें।",
     "أنت المتحكم دائمًا — غيّر أو اسحب الموافقة في أي وقت."),
    ("consent.welcome_b2", "Nothing is shared until you approve it here.",
     "जब तक आप यहाँ स्वीकृति नहीं देते, कुछ भी साझा नहीं होता।",
     "لا تتم مشاركة أي شيء حتى توافق عليه هنا."),
    # ---- Approve step ----
    ("consent.approve_title", "Approve the school", "स्कूल को स्वीकृति दें",
     "الموافقة على المدرسة"),
    ("consent.approve_lead",
     "Turn this on so the school can see your student in their dashboard and "
     "roster. This is the master switch — the next steps only apply once it is on.",
     "इसे चालू करें ताकि स्कूल अपने डैशबोर्ड और रोस्टर में आपके छात्र को देख सके। यह मुख्य "
     "स्विच है — अगले चरण तभी लागू होते हैं जब यह चालू हो।",
     "فعّل هذا لتتمكن المدرسة من رؤية طالبك في لوحة التحكم والقائمة. هذا هو المفتاح "
     "الرئيسي — لا تُطبَّق الخطوات التالية إلا عند تشغيله."),
    ("consent.approve_switch", "Let {school} see this student",
     "{school} को यह छात्र देखने दें", "السماح لـ {school} برؤية هذا الطالب"),
    ("consent.approve_b1",
     "The school sees your student’s name, class and attendance only.",
     "स्कूल केवल आपके छात्र का नाम, कक्षा और उपस्थिति देखता है।",
     "ترى المدرسة اسم طالبك وصفّه وحضوره فقط."),
    ("consent.approve_b2",
     "Location and bus tracking stay off until you choose them next.",
     "स्थान और बस ट्रैकिंग तब तक बंद रहती है जब तक आप उन्हें आगे नहीं चुनते।",
     "يبقى تتبع الموقع والحافلة متوقفًا حتى تختارهما لاحقًا."),
    # ---- Location step ----
    ("consent.loc_title", "Share live location", "लाइव स्थान साझा करें",
     "مشاركة الموقع المباشر"),
    ("consent.loc_lead",
     "Let the school see where your child is during the school day and the ride "
     "home.",
     "स्कूल को यह देखने दें कि स्कूल के दिन और घर की सवारी के दौरान आपका बच्चा कहाँ है।",
     "اسمح للمدرسة برؤية مكان طفلك خلال اليوم الدراسي ورحلة العودة إلى المنزل."),
    ("consent.loc_b1", "Only while an active school day is in progress.",
     "केवल तभी जब कोई सक्रिय स्कूल दिवस चल रहा हो।", "فقط أثناء يوم دراسي نشط."),
    ("consent.loc_b2", "You can turn this off any time from School requests.",
     "आप इसे कभी भी स्कूल अनुरोध से बंद कर सकते हैं।",
     "يمكنك إيقاف هذا في أي وقت من طلبات المدرسة."),
    ("consent.loc_switch", "Share live location", "लाइव स्थान साझा करें",
     "مشاركة الموقع المباشر"),
    ("consent.needs_approve", "Approve the school first to enable this.",
     "इसे सक्षम करने के लिए पहले स्कूल को स्वीकृति दें।", "وافق على المدرسة أولاً لتفعيل هذا."),
    # ---- Bus step ----
    ("consent.bus_title", "Bus & ride tracking", "बस और सवारी ट्रैकिंग",
     "تتبع الحافلة والرحلة"),
    ("consent.bus_lead",
     "Get the bus assignment and track the ride to and from school.",
     "बस असाइनमेंट प्राप्त करें और स्कूल आने-जाने की सवारी ट्रैक करें।",
     "احصل على تعيين الحافلة وتتبع الرحلة من وإلى المدرسة."),
    ("consent.bus_b1", "See the bus on the map and its estimated arrival.",
     "मैप पर बस और उसके अनुमानित आगमन को देखें।",
     "شاهد الحافلة على الخريطة ووقت وصولها المتوقع."),
    ("consent.bus_b2", "Optional — skip it if your child does not take the bus.",
     "वैकल्पिक — यदि आपका बच्चा बस नहीं लेता तो इसे छोड़ दें।",
     "اختياري — تخطَّه إذا كان طفلك لا يستقل الحافلة."),
    ("consent.bus_switch", "Bus tracking", "बस ट्रैकिंग", "تتبع الحافلة"),
    ("consent.needs_approve_next", "Turn on approval to continue, or decline below.",
     "जारी रखने के लिए स्वीकृति चालू करें, या नीचे अस्वीकार करें।",
     "فعّل الموافقة للمتابعة، أو ارفض أدناه."),
    # ---- Pickup & drop step ----
    ("consent.pickup_title", "Pickup & drop", "पिकअप और ड्रॉप", "الاصطحاب والتوصيل"),
    ("consent.pickup_lead",
     "This is automatic. When your child reaches school in the morning and leaves "
     "at the end of the day, you get a pickup & drop alert — no setup needed.",
     "यह स्वचालित है। जब आपका बच्चा सुबह स्कूल पहुँचता है और दिन के अंत में निकलता है, तो "
     "आपको पिकअप व ड्रॉप अलर्ट मिलता है — कोई सेटअप आवश्यक नहीं।",
     "هذا تلقائي. عندما يصل طفلك إلى المدرسة صباحًا ويغادر في نهاية اليوم، تتلقى تنبيه "
     "الاصطحاب والتوصيل — دون أي إعداد."),
    ("consent.pickup_b1", "Alerts arrive around arrival and dismissal time at the school.",
     "अलर्ट स्कूल में आगमन और छुट्टी के समय के आसपास आते हैं।",
     "تصل التنبيهات حول وقت الوصول والانصراف في المدرسة."),
    ("consent.pickup_b2", "They tell you whether your child left on foot or in a vehicle.",
     "ये आपको बताते हैं कि आपका बच्चा पैदल गया या वाहन से।",
     "تخبرك بما إذا كان طفلك قد غادر سيرًا على الأقدام أو بمركبة."),
    ("consent.pickup_b3", "Find every pickup & drop in your Alerts inbox.",
     "हर पिकअप व ड्रॉप अपने अलर्ट इनबॉक्स में देखें।",
     "اعثر على كل اصطحاب وتوصيل في صندوق التنبيهات."),
    ("consent.pickup_note",
     "Pickup & drop alerts need live location on — turn it on in the previous step "
     "to get them.",
     "पिकअप व ड्रॉप अलर्ट के लिए लाइव स्थान चालू होना आवश्यक है — इन्हें पाने के लिए पिछले "
     "चरण में इसे चालू करें।",
     "تحتاج تنبيهات الاصطحاب والتوصيل إلى تشغيل الموقع المباشر — فعّله في الخطوة السابقة "
     "للحصول عليها."),
    # ---- Review step ----
    ("consent.review_title", "Review & finish", "समीक्षा करें और समाप्त करें",
     "المراجعة والإنهاء"),
    ("consent.review_lead",
     "Here is what you are sharing with the school. Tap Finish to save — you can "
     "change any of it later.",
     "यहाँ वह है जो आप स्कूल के साथ साझा कर रहे हैं। सहेजने के लिए समाप्त करें पर टैप करें — "
     "आप इसमें से कुछ भी बाद में बदल सकते हैं।",
     "إليك ما تشاركه مع المدرسة. اضغط إنهاء للحفظ — يمكنك تغيير أي منها لاحقًا."),
    ("consent.review_approve", "School can see student", "स्कूल छात्र को देख सकता है",
     "يمكن للمدرسة رؤية الطالب"),
    ("consent.automatic", "Automatic", "स्वचालित", "تلقائي"),
    ("consent.on", "On", "चालू", "تشغيل"),
    ("consent.off", "Off", "बंद", "إيقاف"),
    ("consent.finish", "Finish", "समाप्त करें", "إنهاء"),
    ("consent.decline", "Decline for now", "अभी अस्वीकार करें", "الرفض الآن"),
    # ---- Status / errors ----
    ("consent.saved", "Setup saved.", "सेटअप सहेजा गया।", "تم حفظ الإعداد."),
    ("consent.save_error", "Could not save. Please try again.",
     "सहेजा नहीं जा सका। कृपया पुनः प्रयास करें।", "تعذّر الحفظ. حاول مرة أخرى."),
    ("consent.load_error", "Could not load this request.",
     "यह अनुरोध लोड नहीं हो सका।", "تعذّر تحميل هذا الطلب."),
    ("consent.not_found", "This request is no longer available.",
     "यह अनुरोध अब उपलब्ध नहीं है।", "لم يعد هذا الطلب متاحًا."),
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
