from __future__ import annotations

import base64
import hmac
import html
import os
import uuid
from copy import deepcopy
from datetime import date, datetime, time
from pathlib import Path
from typing import Any, Dict, List

import streamlit as st

from i18n import STEPS, TRANSLATIONS
from storage import GitHubStorage, LocalStorage, StorageError, utc_now

st.set_page_config(
    page_title="Mubadara System | نظام مبادرة",
    page_icon="🎓",
    layout="wide",
    initial_sidebar_state="collapsed",
)

NAVY = "#0B2341"
NAVY_2 = "#12345B"
GOLD = "#C8A454"
SOFT = "#F6F7F9"


def secret_get(path: List[str], default: str = "") -> str:
    """Read a nested Streamlit secret and safely fall back to environment variables."""
    try:
        node: Any = st.secrets
        for key in path:
            node = node[key]
        return str(node)
    except Exception:
        env_name = "_".join(path).upper()
        return os.getenv(env_name, default)


DEFAULT_ADMIN_USER = "admin"
DEFAULT_ADMIN_PASSWORD = "Mubadara@2026"


def _clean_auth_value(value: str, default: str) -> str:
    """Ignore common placeholder values accidentally pasted into Streamlit Secrets."""
    value = (value or "").strip()
    upper = value.upper()
    placeholders = {
        "YOUR_ADMIN_USER",
        "YOUR_STRONG_PASSWORD",
        "CHANGE_ME",
        "CHANGEME",
        "ADMIN_USER",
        "ADMIN_PASSWORD",
    }
    if not value or upper in placeholders or upper.startswith("YOUR_"):
        return default
    return value


ADMIN_USER = _clean_auth_value(
    secret_get(["auth", "admin_user"], os.getenv("ADMIN_USER", DEFAULT_ADMIN_USER)),
    DEFAULT_ADMIN_USER,
)
ADMIN_PASSWORD = _clean_auth_value(
    secret_get(["auth", "admin_password"], os.getenv("ADMIN_PASSWORD", DEFAULT_ADMIN_PASSWORD)),
    DEFAULT_ADMIN_PASSWORD,
)


def admin_credentials_valid(user_id: str, password: str) -> bool:
    """Validate configured credentials, with the documented demo admin as a safe fallback.

    The fallback avoids accidental lockout when Streamlit Secrets still contain
    example/placeholder auth values. It can be disabled later with
    [auth] allow_default_admin = false.
    """
    normalized_user = (user_id or "").strip()
    normalized_password = (password or "").strip()

    configured_ok = (
        hmac.compare_digest(normalized_user.casefold(), ADMIN_USER.strip().casefold())
        and hmac.compare_digest(normalized_password, ADMIN_PASSWORD.strip())
    )

    allow_default = True
    try:
        allow_default = bool(st.secrets.get("auth", {}).get("allow_default_admin", True))
    except Exception:
        allow_default = True

    fallback_ok = (
        allow_default
        and hmac.compare_digest(normalized_user.casefold(), DEFAULT_ADMIN_USER.casefold())
        and hmac.compare_digest(normalized_password, DEFAULT_ADMIN_PASSWORD)
    )
    return configured_ok or fallback_ok


def image_data_uri(path: str) -> str:
    """Return a local image as an inline data URI for reliable centered rendering."""
    try:
        raw = Path(path).read_bytes()
        suffix = Path(path).suffix.lower().lstrip(".") or "png"
        mime = "image/jpeg" if suffix in {"jpg", "jpeg"} else f"image/{suffix}"
        return f"data:{mime};base64,{base64.b64encode(raw).decode('ascii')}"
    except Exception:
        return ""


def build_storage():
    token = secret_get(["github", "token"], os.getenv("GITHUB_TOKEN", ""))
    repo = secret_get(["github", "repo"], os.getenv("GITHUB_REPO", ""))
    branch = secret_get(["github", "branch"], os.getenv("GITHUB_BRANCH", "main"))
    if token and repo:
        return GitHubStorage(token=token, repo=repo, branch=branch)
    return LocalStorage()


@st.cache_resource(show_spinner=False)
def get_storage():
    return build_storage()


storage = get_storage()

if "lang" not in st.session_state:
    st.session_state.lang = "ar"
if "role" not in st.session_state:
    st.session_state.role = None
if "selected_event" not in st.session_state:
    st.session_state.selected_event = None
if "flash" not in st.session_state:
    st.session_state.flash = None
if "fallback_db" not in st.session_state:
    st.session_state.fallback_db = None
if "storage_error_detail" not in st.session_state:
    st.session_state.storage_error_detail = None
if "storage_persistent" not in st.session_state:
    st.session_state.storage_persistent = True

lang = st.session_state.lang
t = TRANSLATIONS[lang]
is_ar = lang == "ar"


def inject_css() -> None:
    direction = "rtl" if is_ar else "ltr"
    align = "right" if is_ar else "left"
    st.markdown(
        f"""
        <style>
        @import url('https://fonts.googleapis.com/css2?family=Tajawal:wght@400;500;600;700;800&display=swap');
        html, body, [class*="css"], [data-testid="stAppViewContainer"] {{
            font-family: 'Tajawal', system-ui, sans-serif !important;
        }}
        html, body, [data-testid="stAppViewContainer"], [data-testid="stMain"] {{
            direction: {direction};
            text-align: {align};
        }}
        [data-testid="stHeader"] {{ background: transparent; }}
        .stApp {{ background: linear-gradient(180deg, #F8FAFC 0%, #F4F6F8 100%); }}
        .block-container {{ padding-top: 1.2rem; padding-bottom: 3rem; max-width: 1550px; }}
        .brand-header {{
            background: linear-gradient(135deg, {NAVY} 0%, {NAVY_2} 100%);
            border-radius: 22px;
            padding: 16px 20px;
            color: white;
            box-shadow: 0 16px 40px rgba(11,35,65,.14);
            margin-bottom: 18px;
            border-bottom: 4px solid {GOLD};
        }}
        .brand-kicker {{ color: #E6D6A9; font-size: .86rem; font-weight: 700; margin-bottom: 3px; }}
        .brand-title {{ font-size: clamp(1rem, 2vw, 1.45rem); font-weight: 800; line-height: 1.55; }}
        .brand-subtitle {{ opacity: .82; font-size: .86rem; margin-top: 2px; }}
        .kpi {{
            background:white; border:1px solid #E6E9EE; border-radius:18px; padding:18px;
            box-shadow:0 8px 24px rgba(11,35,65,.06); min-height:120px;
            transition: transform .2s ease, box-shadow .2s ease, border-color .2s ease;
        }}
        .kpi:hover {{ transform: translateY(-3px); box-shadow:0 14px 30px rgba(11,35,65,.1); border-color:#DCC98F; }}
        .kpi-label {{ color:#667085; font-weight:700; font-size:.9rem; }}
        .kpi-value {{ color:{NAVY}; font-weight:800; font-size:2rem; margin-top:8px; }}
        .section-card {{
            background:white; border:1px solid #E6E9EE; border-radius:20px; padding:20px;
            box-shadow:0 8px 24px rgba(11,35,65,.05); margin-bottom:18px;
        }}
        .section-title {{ color:{NAVY}; font-size:1.28rem; font-weight:800; margin-bottom:4px; }}
        .section-hint {{ color:#667085; font-size:.9rem; margin-bottom:12px; }}
        .step-pill {{
            display:inline-flex; align-items:center; gap:7px; padding:7px 11px; border-radius:999px;
            background:#F5EEDC; color:{NAVY}; border:1px solid #E7D8AB; font-weight:700; font-size:.78rem;
        }}
        .event-card {{
            background:#fff; border:1px solid #E5E7EB; border-top:4px solid {GOLD}; border-radius:16px;
            padding:14px; min-height:162px; box-shadow:0 6px 18px rgba(11,35,65,.05); margin-bottom:10px;
            transition: transform .18s ease, box-shadow .18s ease;
        }}
        .event-card:hover {{ transform:translateY(-2px); box-shadow:0 12px 24px rgba(11,35,65,.09); }}
        .event-name {{ font-weight:800; color:{NAVY}; font-size:1rem; line-height:1.5; margin-bottom:8px; }}
        .event-meta {{ color:#667085; font-size:.82rem; line-height:1.7; }}
        .status-dot {{ width:9px; height:9px; border-radius:50%; background:{GOLD}; display:inline-block; }}
        .timeline {{ display:flex; gap:6px; align-items:flex-start; overflow-x:auto; padding:8px 0 12px; }}
        .timeline-step {{ min-width:112px; text-align:center; }}
        .timeline-node {{ width:28px; height:28px; border-radius:50%; display:grid; place-items:center; margin:0 auto 6px; font-size:.75rem; font-weight:800; }}
        .timeline-done .timeline-node {{ background:{NAVY}; color:white; }}
        .timeline-active .timeline-node {{ background:{GOLD}; color:{NAVY}; box-shadow:0 0 0 5px rgba(200,164,84,.18); }}
        .timeline-future .timeline-node {{ background:#EEF1F4; color:#98A2B3; }}
        .timeline-label {{ font-size:.72rem; color:#667085; font-weight:700; line-height:1.35; }}
        .timeline-active .timeline-label {{ color:{NAVY}; font-weight:800; }}
        .note {{ background:#F8FAFC; border:1px solid #EAECF0; border-radius:14px; padding:11px 12px; margin-bottom:8px; }}
        .note-meta {{ color:#98A2B3; font-size:.72rem; margin-bottom:4px; }}
        .note-text {{ color:#344054; font-size:.9rem; line-height:1.65; }}
        .doc {{ display:flex; justify-content:space-between; gap:10px; padding:9px 0; border-bottom:1px dashed #EAECF0; font-size:.85rem; }}
        .muted {{ color:#667085; }}
        .gold-line {{ height:3px; background:{GOLD}; border-radius:999px; margin:8px 0 14px; }}
        div.stButton > button, div.stDownloadButton > button {{
            border-radius:12px !important; font-weight:800 !important; min-height:42px;
            transition:all .18s ease !important; border:1px solid #D0D5DD !important;
        }}
        div.stButton > button:hover, div.stDownloadButton > button:hover {{
            transform:translateY(-1px); border-color:{GOLD} !important; box-shadow:0 7px 18px rgba(11,35,65,.09) !important;
        }}
        button[kind="primary"] {{ background:{NAVY} !important; color:white !important; border-color:{NAVY} !important; }}
        button[kind="primary"]:hover {{ background:{NAVY_2} !important; color:white !important; }}
        [data-baseweb="input"] > div, [data-baseweb="select"] > div, textarea {{ border-radius:12px !important; }}
        [data-testid="stFileUploaderDropzone"] {{ border-radius:16px; border-color:#D9C483; background:#FFFCF5; }}
        [data-testid="stDialog"] > div {{ border-radius:22px !important; }}
        .login-shell {{ max-width:760px; margin:2vh auto 0; }}
        .official-logo-wrap {{ display:flex; justify-content:center; align-items:center; width:100%; padding:4px 0 8px; }}
        .official-logo {{ width:min(760px, 92vw); height:auto; object-fit:contain; display:block; margin:0 auto; }}
        .office-heading {{ text-align:center; margin:8px auto 22px; }}
        .office-title {{ color:{NAVY}; font-size:clamp(1.2rem, 2.4vw, 1.8rem); font-weight:800; line-height:1.5; }}
        .office-subtitle {{ color:{GOLD}; font-size:.98rem; font-weight:800; margin-top:2px; }}
        .login-controls {{ margin-bottom:4px; }}
        .login-title {{ color:{NAVY}; font-weight:800; font-size:1.5rem; text-align:center; margin-bottom:4px; }}
        .login-hint {{ color:#667085; text-align:center; margin-bottom:18px; }}
        .sync-ok {{ color:#137333; font-weight:700; font-size:.82rem; }}
        .sync-local {{ color:#B54708; font-weight:700; font-size:.82rem; }}
        .sync-error {{ color:#B42318; font-weight:700; font-size:.82rem; }}
        @keyframes fadein {{ from {{ opacity:0; transform:translateY(4px); }} to {{ opacity:1; transform:none; }} }}
        [data-testid="stMainBlockContainer"] {{ animation:fadein .25s ease; }}
        @media (max-width: 768px) {{
          .block-container {{ padding-left:.8rem; padding-right:.8rem; }}
          .brand-header {{ border-radius:16px; padding:13px; }}
          .official-logo {{ width:min(100%, 680px); }}
          .office-heading {{ margin-bottom:16px; }}
          .section-card {{ border-radius:16px; padding:14px; }}
          .event-card {{ min-height:auto; }}
        }}
        </style>
        """,
        unsafe_allow_html=True,
    )


inject_css()


def tx(key: str) -> str:
    return t.get(key, key)


def event_text(event: Dict[str, Any], field: str) -> str:
    localized = event.get(f"{field}_{lang}")
    return str(localized or event.get(field) or event.get(f"{field}_ar") or event.get(f"{field}_en") or "—")


def role_label(role: str) -> str:
    return tx({
        "studentGroup": "student_group",
        "assistantDean": "assistant_dean",
        "studentAffairs": "student_affairs",
        "finance": "finance",
    }.get(role, role))


def step_label(step: int) -> str:
    step = max(1, min(7, int(step or 1)))
    return tx(STEPS[step - 1])


def _remember_unsynced_db(db: Dict[str, Any], detail: str) -> Dict[str, Any]:
    """Keep the current session usable without pretending data is persisted."""
    st.session_state.fallback_db = deepcopy(db)
    st.session_state.storage_error_detail = detail
    st.session_state.storage_persistent = False
    return st.session_state.fallback_db


def load_db() -> Dict[str, Any]:
    try:
        db = storage.load_db()
        st.session_state.storage_error_detail = None
        st.session_state.storage_persistent = True
        st.session_state.fallback_db = deepcopy(db)
        return db
    except Exception as exc:
        detail = str(exc)
        if st.session_state.fallback_db is None:
            st.session_state.fallback_db = deepcopy({"schema_version": 1, "events": [], "notes": [], "audit": []})
        return _remember_unsynced_db(st.session_state.fallback_db, detail)


def save_db(db: Dict[str, Any], message: str) -> bool:
    try:
        storage.save_db(db, message)
        st.session_state.fallback_db = deepcopy(db)
        st.session_state.storage_error_detail = None
        st.session_state.storage_persistent = True
        return True
    except Exception as exc:
        _remember_unsynced_db(db, str(exc))
        detail = str(exc)
        st.error(
            ("تعذر الحفظ في GitHub. الاتصال للقراءة يعمل، لكن صلاحية الكتابة غير متاحة أو غير صحيحة. "
             "راجع صلاحية Contents: Read and write للتوكن على نفس المستودع."
             if is_ar else
             "Could not save to GitHub. Read access works, but write access is missing or misconfigured. "
             "Grant the token Contents: Read and write for this exact repository.")
        )
        with st.expander("تفاصيل خطأ الحفظ" if is_ar else "Save error details"):
            st.code(detail)
        return False


def audit(db: Dict[str, Any], event_id: str, action: str, details: str, actor_role: str | None = None) -> None:
    db.setdefault("audit", []).append({
        "id": uuid.uuid4().hex[:12],
        "event_id": event_id,
        "action": action,
        "details": details,
        "actor_role": actor_role or st.session_state.role or "system",
        "created_at": utc_now(),
    })


def find_event(db: Dict[str, Any], event_id: str) -> Dict[str, Any] | None:
    return next((e for e in db.get("events", []) if e.get("id") == event_id), None)


def ensure_seed(db: Dict[str, Any]) -> Dict[str, Any]:
    if db.get("events"):
        return db
    now = utc_now()
    seed_events = [
        ("EVT-26001", "أسبوع ريادة الأعمال", "Entrepreneurship Week", "جماعة ريادة الأعمال", "Entrepreneurship Group", 2, "2026-09-15T09:00"),
        ("EVT-26002", "حلقة عمل في القيادة", "Leadership Workshop", "جماعة الإدارة", "Management Group", 3, "2026-09-19T10:00"),
        ("EVT-26003", "ملتقى الاقتصاد المستدام", "Sustainable Economics Forum", "جماعة الاقتصاد", "Economics Group", 4, "2026-09-22T11:00"),
        ("EVT-26004", "زيارة قطاع الاستثمار", "Investment Sector Visit", "جماعة المالية والاستثمار", "Finance & Investment Group", 5, "2026-09-25T08:00"),
        ("EVT-26005", "لقاء الابتكار الطلابي", "Student Innovation Meetup", "جماعة الابتكار", "Innovation Group", 6, "2026-09-28T12:00"),
        ("EVT-26006", "ملتقى الخريجين", "Alumni Forum", "نادي الخريجين", "Alumni Club", 7, "2026-10-05T17:00"),
    ]
    for event_id, ar_name, en_name, ar_group, en_group, step, dt in seed_events:
        db["events"].append({
            "id": event_id,
            "name_ar": ar_name,
            "name_en": en_name,
            "group_name_ar": ar_group,
            "group_name_en": en_group,
            "supervisor": "د. أحمد / Dr. Ahmed",
            "datetime": dt,
            "location": "main_hall",
            "step": step,
            "status": "active",
            "created_by": "demo",
            "created_at": now,
            "updated_at": now,
            "attachments": [],
            "approvals": [],
        })
        audit(db, event_id, "seed_created", f"Demo event initialized at step {step}", "system")
    # Demo cards are for preview only. Do NOT auto-write them to GitHub on page load.
    # Real user actions (new requests, approvals, notes, uploads, etc.) still save automatically.
    st.session_state.fallback_db = deepcopy(db)
    return db


def storage_status() -> tuple[bool, str]:
    try:
        if hasattr(storage, "healthcheck"):
            return storage.healthcheck()
        return True, storage.mode
    except Exception as exc:
        return False, str(exc)


def render_official_brand() -> None:
    logo_uri = image_data_uri("assets/official-logo.png")
    if logo_uri:
        st.markdown(
            f'<div class="official-logo-wrap"><img class="official-logo" src="{logo_uri}" alt="Official logo"></div>',
            unsafe_allow_html=True,
        )
    else:
        st.image("assets/official-logo.png", use_container_width=True)
    brand_html = (
        '<div class="office-heading">'
        f'<div class="office-title">{html.escape(tx("title"))}</div>'
        f'<div class="office-subtitle">{html.escape(tx("subtitle"))}</div>'
        '</div>'
    )
    st.markdown(brand_html, unsafe_allow_html=True)


def header() -> None:
    # Keep controls compact while the supplied official logo stays centered.
    c_lang, c_space, c_sync = st.columns([1.2, 5.6, 1.5], vertical_alignment="center")
    with c_lang:
        if st.button(tx("language"), use_container_width=True, key="lang_toggle"):
            st.session_state.lang = "en" if lang == "ar" else "ar"
            st.rerun()
        if st.session_state.role and st.button(tx("logout"), use_container_width=True, key="logout"):
            st.session_state.role = None
            st.session_state.selected_event = None
            st.rerun()
    with c_sync:
        ok, detail = storage_status()
        if storage.mode == "local":
            css_class = "sync-local"
            sync_text = tx("local_mode")
        elif not st.session_state.storage_persistent:
            css_class = "sync-error"
            sync_text = "غير متزامن" if is_ar else "Not synced"
        elif ok:
            css_class = "sync-ok"
            sync_text = tx("connected")
        else:
            css_class = "sync-error"
            sync_text = "غير متصل" if is_ar else "Not connected"
        st.markdown(f'<div class="{css_class}">● {tx("github_sync")}: {sync_text}</div>', unsafe_allow_html=True)
        if not ok and storage.mode == "github":
            with st.expander("تفاصيل الاتصال" if is_ar else "Connection details"):
                st.caption(detail)

    render_official_brand()


def login_view() -> None:
    st.markdown('<div class="login-shell">', unsafe_allow_html=True)
    st.markdown(f'<div class="login-title">{tx("login")}</div><div class="login-hint">{tx("login_hint")}</div>', unsafe_allow_html=True)
    with st.container(border=True):
        user_id = st.text_input(tx("user_id"), placeholder=tx("user_id"))
        password = st.text_input(tx("password"), type="password", placeholder="••••••••")
        if st.button(tx("sign_in"), type="primary", use_container_width=True):
            if admin_credentials_valid(user_id, password):
                st.session_state.role = "assistantDean"
                st.session_state.selected_event = None
                st.session_state.flash = None
                st.rerun()
            else:
                # Keep this message explicit so an older translation file can never
                # expose the internal key "invalid_credentials" to end users.
                st.error("اسم المستخدم أو كلمة المرور غير صحيحة." if is_ar else "Incorrect username or password.")
        st.markdown(f"**{tx('demo_roles')}**")
        cols = st.columns(2)
        roles = [
            ("studentGroup", "🎓"),
            ("assistantDean", "🏛️"),
            ("studentAffairs", "👥"),
            ("finance", "💰"),
        ]
        for idx, (role, icon) in enumerate(roles):
            with cols[idx % 2]:
                if st.button(f"{icon} {role_label(role)}", key=f"role_{role}", use_container_width=True):
                    st.session_state.role = role
                    st.rerun()
    st.markdown('</div>', unsafe_allow_html=True)


def kpi_card(label: str, value: int) -> None:
    st.markdown(f'<div class="kpi"><div class="kpi-label">{html.escape(label)}</div><div class="kpi-value">{value}</div></div>', unsafe_allow_html=True)


def event_card_html(event: Dict[str, Any]) -> str:
    dt = str(event.get("datetime", "")).replace("T", " ")
    return f"""
    <div class="event-card">
      <div class="event-name">{html.escape(event_text(event, 'name'))}</div>
      <div class="event-meta"><b>{html.escape(tx('group'))}:</b> {html.escape(event_text(event, 'group_name'))}</div>
      <div class="event-meta"><b>{html.escape(tx('date'))}:</b> {html.escape(dt or '—')}</div>
      <div style="margin-top:9px"><span class="step-pill"><span class="status-dot"></span>{html.escape(step_label(event.get('step',1)))}</span></div>
    </div>
    """


def render_timeline(current: int) -> None:
    parts = ['<div class="timeline">']
    for idx, key in enumerate(STEPS, start=1):
        cls = "timeline-done" if idx < current else "timeline-active" if idx == current else "timeline-future"
        parts.append(
            f'<div class="timeline-step {cls}"><div class="timeline-node">{idx}</div>'
            f'<div class="timeline-label">{html.escape(tx(key))}</div></div>'
        )
    parts.append("</div>")
    st.markdown("".join(parts), unsafe_allow_html=True)


def make_report(event: Dict[str, Any], db: Dict[str, Any]) -> bytes:
    notes = [n for n in db.get("notes", []) if n.get("event_id") == event.get("id")]
    docs = event.get("attachments", [])
    rows = "".join(
        f"<tr><td>{html.escape(str(d.get('kind','')))}</td><td>{html.escape(str(d.get('name','')))}</td><td>{html.escape(str(d.get('uploaded_at','')))}</td></tr>"
        for d in docs
    ) or "<tr><td colspan='3'>—</td></tr>"
    notes_html = "".join(
        f"<li><b>{html.escape(str(n.get('created_at','')))}</b> — {html.escape(str(n.get('text','')))}</li>" for n in notes
    ) or "<li>—</li>"
    direction = "rtl" if is_ar else "ltr"
    content = f"""<!doctype html><html dir="{direction}"><head><meta charset="utf-8"><title>{html.escape(tx('event_report'))}</title>
    <style>body{{font-family:Arial,sans-serif;margin:36px;color:#0B2341}}h1{{border-bottom:3px solid #C8A454;padding-bottom:10px}}table{{width:100%;border-collapse:collapse}}td,th{{border:1px solid #ddd;padding:8px;text-align:{'right' if is_ar else 'left'}}}.meta{{line-height:1.9}}@media print{{button{{display:none}}}}</style></head>
    <body><button onclick="window.print()">🖨️ {html.escape(tx('print_report'))}</button><h1>{html.escape(tx('event_report'))}</h1>
    <div class="meta"><b>{html.escape(tx('event_id'))}:</b> {html.escape(str(event.get('id')))}<br>
    <b>{html.escape(tx('event_name'))}:</b> {html.escape(event_text(event,'name'))}<br>
    <b>{html.escape(tx('group_name'))}:</b> {html.escape(event_text(event,'group_name'))}<br>
    <b>{html.escape(tx('supervisor'))}:</b> {html.escape(str(event.get('supervisor','—')))}<br>
    <b>{html.escape(tx('event_datetime'))}:</b> {html.escape(str(event.get('datetime','—')))}<br>
    <b>{html.escape(tx('current_step'))}:</b> {html.escape(step_label(event.get('step',1)))}</div>
    <h2>{html.escape(tx('documents'))}</h2><table><tr><th>{html.escape(tx('attachment_type'))}</th><th>Name</th><th>Date</th></tr>{rows}</table>
    <h2>{html.escape(tx('tracking_notes'))}</h2><ul>{notes_html}</ul></body></html>"""
    return content.encode("utf-8")


@st.dialog("Event Details", width="large")
def event_details_dialog(event_id: str):
    db = load_db()
    event = find_event(db, event_id)
    if not event:
        st.error("Event not found")
        return

    top1, top2 = st.columns([3, 1])
    with top1:
        st.markdown(f"### {tx('details')} — {event_text(event, 'name')}")
        st.caption(f"{tx('event_id')}: {event.get('id')} · {tx('current_step')}: {step_label(event.get('step', 1))}")
    with top2:
        st.download_button(
            f"🖨️ {tx('print_report')}",
            data=make_report(event, db),
            file_name=f"{event.get('id','event')}_report.html",
            mime="text/html",
            use_container_width=True,
        )

    render_timeline(int(event.get("step", 1)))
    left, right = st.columns([1, 1.1], gap="large")

    with right:
        st.markdown(f"#### {tx('details')}")
        st.write(f"**{tx('event_name')}:** {event_text(event, 'name')}")
        st.write(f"**{tx('group_name')}:** {event_text(event, 'group_name')}")
        st.write(f"**{tx('supervisor')}:** {event.get('supervisor','—')}")
        st.write(f"**{tx('event_datetime')}:** {event.get('datetime','—')}")
        st.write(f"**{tx('location')}:** {tx(event.get('location','main_hall'))}")
        st.write(f"**{tx('status')}:** {step_label(event.get('step', 1))}")
        st.markdown('<div class="gold-line"></div>', unsafe_allow_html=True)

        st.markdown(f"#### {tx('documents')}")
        docs = event.get("attachments", [])
        if not docs:
            st.caption(tx("no_documents"))
        for doc in docs:
            st.markdown(
                f'<div class="doc"><span>📎 {html.escape(str(doc.get("name","file")))}</span><span class="muted">{html.escape(str(doc.get("kind","")))}</span></div>',
                unsafe_allow_html=True,
            )

        if int(event.get("step", 1)) >= 3:
            st.markdown(f"#### {tx('logistics_requests')}")
            logistics_docs = [d for d in docs if d.get("kind") == "support_letters"]
            if logistics_docs:
                for d in logistics_docs:
                    st.write(f"✅ {d.get('name')}")
            else:
                st.caption(tx("no_documents"))

        if int(event.get("step", 1)) >= 5:
            st.markdown(f"#### {tx('financial_settlements')}")
            finance_docs = [d for d in docs if d.get("kind") in {"invoices", "settlement"}]
            if finance_docs:
                for d in finance_docs:
                    st.write(f"✅ {d.get('name')}")
            else:
                st.caption(tx("no_documents"))

        c1, c2 = st.columns(2)
        with c1:
            if st.button(f"✓ {tx('approve')}", type="primary", use_container_width=True, key=f"approve_{event_id}"):
                event.setdefault("approvals", []).append({"role": st.session_state.role, "at": utc_now()})
                event["updated_at"] = utc_now()
                audit(db, event_id, "approved", f"Approved at step {event.get('step')}")
                if save_db(db, f"Approve event {event_id} at step {event.get('step')}"):
                    st.toast(tx("approved_saved"))
                    st.rerun()
        with c2:
            disabled = int(event.get("step", 1)) >= 7
            if st.button(f"→ {tx('move_next')}", use_container_width=True, disabled=disabled, key=f"next_{event_id}"):
                old_step = int(event.get("step", 1))
                event["step"] = min(7, old_step + 1)
                event["updated_at"] = utc_now()
                audit(db, event_id, "moved_step", f"Moved from step {old_step} to {event['step']}")
                if save_db(db, f"Move event {event_id} to step {event['step']}"):
                    st.toast(tx("moved_saved"))
                    st.rerun()

    with left:
        st.markdown(f"#### {tx('tracking_notes')}")
        notes = sorted([n for n in db.get("notes", []) if n.get("event_id") == event_id], key=lambda n: n.get("created_at", ""))
        if not notes:
            st.caption(tx("no_notes"))
        for note in notes[-8:]:
            st.markdown(
                f'<div class="note"><div class="note-meta">{html.escape(role_label(note.get("author_role","assistantDean")))} · {html.escape(str(note.get("created_at","")))} · {html.escape(str(note.get("audience","")))}</div><div class="note-text">{html.escape(str(note.get("text","")))}</div></div>',
                unsafe_allow_html=True,
            )
        audience = st.selectbox(tx("audience"), [tx("student"), tx("departments"), tx("all")], key=f"audience_{event_id}")
        note_text = st.text_area(tx("note_placeholder"), label_visibility="collapsed", key=f"note_{event_id}")
        if st.button(f"💬 {tx('send_note')}", use_container_width=True, key=f"send_note_{event_id}") and note_text.strip():
            db.setdefault("notes", []).append({
                "id": uuid.uuid4().hex[:12],
                "event_id": event_id,
                "text": note_text.strip(),
                "author_role": st.session_state.role,
                "audience": audience,
                "created_at": utc_now(),
            })
            audit(db, event_id, "note_added", f"Note added for {audience}")
            if save_db(db, f"Add note to event {event_id}"):
                st.toast(tx("saved"))
                st.rerun()

        with st.expander(tx("history")):
            history = sorted([a for a in db.get("audit", []) if a.get("event_id") == event_id], key=lambda a: a.get("created_at", ""), reverse=True)
            for item in history[:30]:
                st.caption(f"{item.get('created_at','')} · {item.get('actor_role','')} · {item.get('action','')}")
                st.write(item.get("details", ""))


def assistant_dashboard(db: Dict[str, Any]) -> None:
    events = db.get("events", [])
    st.markdown(f'<div class="section-title">{tx("dashboard")}</div><div class="section-hint">{tx("workflow")}</div>', unsafe_allow_html=True)
    c1, c2, c3 = st.columns(3)
    with c1:
        kpi_card(tx("pending_requests"), sum(1 for e in events if int(e.get("step", 1)) <= 2))
    with c2:
        kpi_card(tx("active_events"), sum(1 for e in events if int(e.get("step", 1)) < 7))
    with c3:
        kpi_card(tx("pending_settlements"), sum(1 for e in events if int(e.get("step", 1)) >= 6))

    st.markdown(f"### {tx('workflow')}")
    # 7 columns on desktop. On mobile Streamlit stacks them, keeping the board usable.
    cols = st.columns(7, gap="small")
    for idx, col in enumerate(cols, start=1):
        with col:
            st.markdown(f'<div class="step-pill">{idx}. {html.escape(step_label(idx))}</div>', unsafe_allow_html=True)
            stage_events = [e for e in events if int(e.get("step", 1)) == idx]
            if not stage_events:
                st.caption(tx("no_events"))
            for event in stage_events:
                st.markdown(event_card_html(event), unsafe_allow_html=True)
                if st.button(tx("view_details"), key=f"detail_{event['id']}", use_container_width=True):
                    event_details_dialog(event["id"])


def create_event(db: Dict[str, Any], name: str, group_name: str, supervisor: str, event_dt: str, location: str, proposal) -> bool:
    event_id = f"EVT-{datetime.now().strftime('%y%m%d')}-{uuid.uuid4().hex[:4].upper()}"
    now = utc_now()
    event = {
        "id": event_id,
        "name": name.strip(),
        "group_name": group_name.strip(),
        "supervisor": supervisor.strip(),
        "datetime": event_dt,
        "location": location,
        "step": 1,
        "status": "active",
        "created_by": "studentGroup",
        "created_at": now,
        "updated_at": now,
        "attachments": [],
        "approvals": [],
    }
    if proposal is not None:
        try:
            path = storage.save_attachment(event_id, "proposal", proposal.name, proposal.getvalue())
            event["attachments"].append({
                "id": uuid.uuid4().hex[:10], "kind": "proposal", "name": proposal.name,
                "path": path, "uploaded_at": now, "uploaded_by": "studentGroup"
            })
        except StorageError as exc:
            st.error(f"{tx('storage_error')}: {exc}")
            return False
    db.setdefault("events", []).append(event)
    audit(db, event_id, "event_created", "Student Group submitted a new event", "studentGroup")
    if proposal is not None:
        audit(db, event_id, "attachment_uploaded", f"Proposal uploaded: {proposal.name}", "studentGroup")
    return save_db(db, f"Create event {event_id}: {name}")


def upload_event_file(db: Dict[str, Any], event: Dict[str, Any], kind: str, file) -> bool:
    try:
        path = storage.save_attachment(event["id"], kind, file.name, file.getvalue())
    except StorageError as exc:
        st.error(f"{tx('storage_error')}: {exc}")
        return False
    now = utc_now()
    event.setdefault("attachments", []).append({
        "id": uuid.uuid4().hex[:10], "kind": kind, "name": file.name, "path": path,
        "uploaded_at": now, "uploaded_by": "studentGroup",
    })
    event["updated_at"] = now
    audit(db, event["id"], "attachment_uploaded", f"{kind}: {file.name}", "studentGroup")
    return save_db(db, f"Upload {kind} for event {event['id']}")


def student_dashboard(db: Dict[str, Any]) -> None:
    st.markdown(f"### {tx('new_request')}")
    with st.form("new_event_form", clear_on_submit=True, border=True):
        r1c1, r1c2 = st.columns(2)
        with r1c1:
            name = st.text_input(tx("event_name"))
            supervisor = st.text_input(tx("supervisor"))
        with r1c2:
            group_name = st.text_input(tx("group_name"))
            location = st.selectbox(tx("location"), ["main_hall", "auditorium", "classroom", "outdoor", "off_campus"], format_func=lambda x: tx(x))
        dcol, tcol = st.columns(2)
        with dcol:
            event_date = st.date_input(tx("event_datetime"), value=date.today())
        with tcol:
            event_time = st.time_input("Time" if not is_ar else "الوقت", value=time(10, 0))
        proposal = st.file_uploader(tx("proposal"), type=["pdf", "doc", "docx"], key="proposal_upload")
        submitted = st.form_submit_button(tx("submit"), type="primary", use_container_width=True)
        if submitted:
            if not all([name.strip(), group_name.strip(), supervisor.strip()]):
                st.error(tx("required_fields"))
            else:
                event_dt = datetime.combine(event_date, event_time).isoformat(timespec="minutes")
                if create_event(db, name, group_name, supervisor, event_dt, location, proposal):
                    st.success(tx("event_created"))
                    st.rerun()

    st.markdown(f"### {tx('my_events')}")
    student_events = [e for e in db.get("events", []) if e.get("created_by") in {"studentGroup", "demo"}]
    if not student_events:
        st.info(tx("no_events"))
    for event in sorted(student_events, key=lambda e: e.get("created_at", ""), reverse=True):
        with st.container(border=True):
            h1, h2 = st.columns([4, 1])
            with h1:
                st.markdown(f"#### {event_text(event, 'name')}")
                st.caption(f"{event_text(event, 'group_name')} · {event.get('datetime','—')} · {tx('event_id')}: {event.get('id')}")
            with h2:
                st.markdown(f'<span class="step-pill">{html.escape(step_label(event.get("step",1)))}</span>', unsafe_allow_html=True)
            render_timeline(int(event.get("step", 1)))

            step = int(event.get("step", 1))
            if step == 3:
                st.markdown(f"**{tx('action_required')}: {tx('support_letters')}**")
                file = st.file_uploader(tx("support_letters"), type=["pdf", "doc", "docx"], key=f"support_{event['id']}")
                if file is not None and st.button(tx("support_letters"), key=f"save_support_{event['id']}"):
                    if upload_event_file(db, event, "support_letters", file):
                        st.success(tx("upload_saved"))
                        st.rerun()
            elif step in {5, 7}:
                st.markdown(f"**{tx('action_required')}: {tx('invoices')}**")
                file = st.file_uploader(tx("invoices"), type=["pdf", "jpg", "jpeg", "png", "xlsx"], key=f"invoice_{event['id']}")
                if file is not None and st.button(tx("invoices"), key=f"save_invoice_{event['id']}"):
                    kind = "settlement" if step == 7 else "invoices"
                    if upload_event_file(db, event, kind, file):
                        st.success(tx("upload_saved"))
                        st.rerun()


def placeholder_role(db: Dict[str, Any]) -> None:
    st.markdown(f"### {role_label(st.session_state.role)}")
    st.info(tx("admin_placeholder"))
    relevant = db.get("events", [])
    if st.session_state.role == "finance":
        relevant = [e for e in relevant if int(e.get("step", 1)) >= 5]
    elif st.session_state.role == "studentAffairs":
        relevant = [e for e in relevant if int(e.get("step", 1)) <= 3]
    for event in relevant:
        with st.container(border=True):
            st.markdown(f"**{event_text(event, 'name')}**")
            st.caption(f"{event_text(event,'group_name')} · {step_label(event.get('step',1))}")
            if st.button(tx("view_details"), key=f"placeholder_detail_{event['id']}"):
                event_details_dialog(event["id"])


header()

if st.session_state.storage_error_detail:
    if is_ar:
        st.warning(
            "⚠️ النظام يعمل حالياً في وضع مؤقت لأن الحفظ في GitHub غير متاح. "
            "لن يتم اعتبار أي تغيير محفوظاً نهائياً حتى يتم إصلاح المستودع أو الصلاحيات."
        )
        with st.expander("تفاصيل مشكلة GitHub"):
            st.code(st.session_state.storage_error_detail)
            st.markdown(
                "تأكد من أن `repo` مكتوب بصيغة `owner/repository` وأن Fine-grained token "
                "مسموح له بالمستودع نفسه وبصلاحية **Contents: Read and write**."
            )
    else:
        st.warning(
            "⚠️ The app is running in temporary mode because GitHub persistence is unavailable. "
            "Changes are not permanently saved until repository permissions are fixed."
        )
        with st.expander("GitHub error details"):
            st.code(st.session_state.storage_error_detail)
            st.markdown(
                "Verify `repo` is `owner/repository` and the fine-grained token is explicitly allowed "
                "to that repository with **Contents: Read and write**."
            )

if st.session_state.flash:
    st.success(st.session_state.flash)
    st.session_state.flash = None

if not st.session_state.role:
    login_view()
else:
    db = ensure_seed(load_db())
    role = st.session_state.role
    if role == "assistantDean":
        assistant_dashboard(db)
    elif role == "studentGroup":
        student_dashboard(db)
    else:
        placeholder_role(db)

st.markdown(
    f"<div style='text-align:center;color:#98A2B3;font-size:.78rem;margin-top:30px'>{html.escape(tx('title'))} · {html.escape(tx('subtitle'))}</div>",
    unsafe_allow_html=True,
)
