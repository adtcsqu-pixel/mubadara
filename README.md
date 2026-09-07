# Mubadara System — Streamlit + GitHub Persistence

نظام مبادرة لإدارة الفعاليات الأكاديمية، مبني بالكامل بـ **Streamlit** مع دعم العربية/الإنجليزية و RTL/LTR وهوية جامعة السلطان قابوس.

## أهم الخصائص

- تسجيل دخول إداري فعلي لمكتب مساعد العميد، مع أزرار تجريبية لبقية الصلاحيات أثناء التطوير.
- لوحة مكتب مساعد العميد: KPI + مسار 7 مراحل + تفاصيل الفعالية + الموافقة/نقل المرحلة + الملاحظات والتتبع.
- بوابة الجماعة الطلابية: إنشاء طلب، رفع تصور الفعالية، متابعة Timeline، ورفع رسائل الدعم والفواتير عند الحاجة.
- تقرير/إخلاء طرف قابل للتنزيل والطباعة من المتصفح.
- كل عملية حفظ، ملاحظة، تغيير مرحلة، موافقة، ومستند مرفوع تُحفظ تلقائياً في GitHub عند إعداد الاتصال.
- سجل تدقيق داخل `data/db.json` بالإضافة إلى Git commit history.

## تشغيل محلي

```bash
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\\Scripts\\activate
pip install -r requirements.txt
streamlit run app.py
```

بدون إعداد GitHub يعمل النظام في وضع تطوير محلي داخل `.local_data/`.

## تفعيل الحفظ التلقائي في GitHub

يوصى بإنشاء **مستودع خاص Private منفصل للبيانات** مثل `mubadara-data`، ثم:

1. أنشئ Fine-grained GitHub Personal Access Token بصلاحية **Contents: Read and write** للمستودع فقط.
2. انسخ `.streamlit/secrets.toml.example` إلى `.streamlit/secrets.toml` للتشغيل المحلي، أو أضف القيم في Streamlit Cloud > App Settings > Secrets.
3. ضع:

```toml
[github]
token = "YOUR_TOKEN"
repo = "owner/mubadara-data"
branch = "main"
```

> مهم: لا تضع التوكن داخل GitHub أو داخل ملفات المشروع المنشورة.

بعد الإعداد، النظام ينشئ تلقائياً:

- `data/db.json` — كل الفعاليات والملاحظات وسجل التدقيق.
- `data/uploads/<event-id>/...` — ملفات تصور الفعالية، رسائل الدعم، الفواتير ومستندات التسوية.
- كل تعديل ينتج Git commit جديد تلقائياً، لذلك يبقى تاريخ التغييرات محفوظاً في GitHub.

## النشر على Streamlit Community Cloud

1. ارفع هذا المشروع إلى GitHub.
2. من Streamlit Community Cloud اختر `app.py` كنقطة التشغيل.
3. أضف GitHub secrets كما في الأعلى.
4. Deploy.

## ملاحظة مهمة للبيانات المؤسسية

لأن GitHub يحتفظ بتاريخ commits، حذف ملف من النسخة الحالية لا يعني زواله من التاريخ. هذا مناسب للأرشفة والتتبع، لكن يجب استخدام مستودع **Private** وسياسة صلاحيات واضحة إذا كانت المستندات حساسة.


## بيانات دخول المشرف الافتراضية

في النسخة التجريبية:

```text
User: admin
Password: Mubadara@2026
```

يمكن تغييرها دون تعديل الكود من Streamlit Secrets:

```toml
[auth]
admin_user = "YOUR_ADMIN_USER"
admin_password = "YOUR_STRONG_PASSWORD"
```

> قبل الاستخدام الرسمي يجب تغيير كلمة المرور الافتراضية وعدم نشرها داخل المستودع.


## تسجيل دخول الإدارة - Admin Login

بيانات الدخول الافتراضية للتجربة:

```text
Username: admin
Password: Mubadara@2026
```

إذا كانت Streamlit Secrets تحتوي قيماً تجريبية مثل `YOUR_ADMIN_USER` أو `YOUR_STRONG_PASSWORD`،
يتجاهلها النظام تلقائياً ويستخدم البيانات الافتراضية أعلاه لمنع قفل حساب الإدارة.

للاستخدام الرسمي، عيّن بياناتك الخاصة ثم عطّل الحساب الافتراضي:

```toml
[auth]
admin_user = "your-admin"
admin_password = "your-strong-password"
allow_default_admin = false
```
