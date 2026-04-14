"""Conference Scaffolding — Streamlit app with auth, profile, and multi-conference workspaces."""

import base64
import html
import json
import sqlite3
from datetime import date, datetime
from typing import Any

import streamlit as st

from app.auth import hash_password, verify_password
from app.db import (
    add_contact,
    create_conference,
    create_user,
    delete_conference,
    delete_contact,
    delete_user,
    export_user_data,
    get_conference,
    get_contact,
    get_user_by_id,
    get_user_by_username,
    init_db,
    list_conferences,
    list_contacts,
    list_contacts_for_conference,
    row_to_dict,
    update_contact,
    update_conference,
    update_user_profile,
)
from app.exports import (
    build_conference_ics,
    build_conference_package_json,
    build_reflection_report_md,
    contacts_to_csv,
)
from app.llm import generate_questions, generate_reflection, parse_business_card
from app.parser import extract_text_from_pdf_bytes, naive_session_parse
from app.prompts import QUESTION_PROMPT, REFLECTION_PROMPT

NAV_PROFILE = "Your profile"
NAV_CONFERENCES = "Conferences"
NAV_CONTACTS = "Contacts"
NAV_CALENDAR = "Calendar & exports"
NAV_PRIVACY = "Privacy"

# Limits (shown in UI; keep in sync with parsing below)
PROFILE_PIC_MAX_BYTES = 500 * 1024  # 500 KiB — max size we accept for profile photos
RESUME_TEXT_MAX_CHARS = 12_000  # extracted text kept for storage / AI prompts

PROFILE_PIC_LIMIT_TEXT = (
    f"Profile picture must be {PROFILE_PIC_MAX_BYTES // 1024} KB or smaller. "
    "The widget may show a much larger browser upload limit (e.g. 200 MB); Symposia still only accepts files up to this size. "
    "Accepted file types: PNG, JPG, JPEG."
)
RESUME_LIMIT_TEXT = (
    f"PDF or plain text. We extract and store up to {RESUME_TEXT_MAX_CHARS:,} characters of text for this app "
    "(not the full binary PDF in the database). Very large PDFs are truncated after extraction."
)


def _resume_text_from_upload(uploaded) -> str:
    if uploaded is None:
        return ""
    name = uploaded.name.lower()
    data = uploaded.read()
    if name.endswith(".pdf"):
        return extract_text_from_pdf_bytes(data)[:RESUME_TEXT_MAX_CHARS]
    try:
        return data.decode("utf-8", errors="replace")[:RESUME_TEXT_MAX_CHARS]
    except Exception:
        return ""


def _apply_theme():
    st.markdown(
        """
        <style>
        .stApp {
            background: linear-gradient(160deg, #020617 0%, #0f172a 40%, #020617 100%);
            background-attachment: fixed;
            color: #e2e8f0;
        }
        .block-container {
            background: rgba(15, 23, 42, 0.94);
            border-radius: 16px;
            padding: 2rem 2rem 2.5rem 2rem;
            margin-top: 1.5rem;
            margin-bottom: 1.5rem;
            border: 1px solid #1e293b;
        }
        .main h1, .main h2, .main h3, .main p, .main label, .main span, .main li {
            color: #e2e8f0 !important;
        }
        .stCaption, [data-testid="stCaption"] {
            color: #94a3b8 !important;
        }
        .stTextInput input,
        .stTextArea textarea,
        [data-baseweb="input"] input,
        [data-baseweb="textarea"] textarea {
            background-color: #020617 !important;
            color: #f8fafc !important;
            border: 1px solid #334155 !important;
            caret-color: #f8fafc !important;
        }
        .stSelectbox [data-baseweb="select"] > div {
            background-color: #020617 !important;
            color: #f8fafc !important;
            border-color: #334155 !important;
        }
        [data-testid="stSidebar"] {
            background: linear-gradient(180deg, #000000 0%, #0f172a 100%) !important;
            border-right: 1px solid #1e293b !important;
        }
        [data-testid="stSidebar"] p, [data-testid="stSidebar"] span, [data-testid="stSidebar"] label {
            color: #e2e8f0 !important;
        }
        [data-testid="stSidebar"] .stButton > button[kind="primary"],
        [data-testid="stSidebar"] .stButton > button[kind="primary"] * {
            background-color: #ffffff !important;
            color: #020617 !important;
            border: none !important;
            font-weight: 600 !important;
        }
        [data-testid="stSidebar"] .stButton > button[kind="primary"] p,
        [data-testid="stSidebar"] .stButton > button[kind="primary"] span {
            color: #020617 !important;
            background: transparent !important;
        }
        [data-testid="stSidebar"] .stButton > button[kind="secondary"] {
            background-color: #1e293b !important;
            color: #f1f5f9 !important;
            border: 1px solid #334155 !important;
        }
        [data-testid="stSidebar"] .stButton > button:hover {
            background-color: #a3b18a !important;
            color: #0b0f14 !important;
            border-color: #a3b18a !important;
        }
        [data-testid="stExpander"] details {
            background-color: #0f172a !important;
            border: 1px solid #334155 !important;
            border-radius: 8px !important;
        }
        [data-testid="stExpander"] summary, [data-testid="stExpander"] summary span {
            color: #f8fafc !important;
        }
        .streamlit-expanderContent {
            background-color: #020617 !important;
            color: #e2e8f0 !important;
        }
        .resume-pre {
            color: #f1f5f9 !important;
            background: #020617 !important;
            padding: 1rem 1.1rem;
            border-radius: 8px;
            overflow-x: auto;
            font-size: 0.9rem;
            line-height: 1.45;
            border: 1px solid #334155;
        }
        .cs-avatar-wrap {
            position: fixed;
            top: 0.85rem;
            right: 1rem;
            z-index: 1000000;
            display: flex;
            align-items: center;
            justify-content: center;
        }
        .cs-avatar-wrap a {
            text-decoration: none;
            line-height: 0;
        }
        .cs-avatar-wrap a:focus {
            outline: 2px solid #38bdf8;
            outline-offset: 2px;
            border-radius: 50%;
        }
        .cs-avatar, .cs-avatar-placeholder {
            width: 56px;
            height: 56px;
            border-radius: 50%;
            object-fit: cover;
            border: 3px solid #e2e8f0;
            box-shadow: 0 2px 12px rgba(0,0,0,0.45);
        }
        .cs-avatar-placeholder {
            background: #334155;
            color: #f8fafc;
            display: flex;
            align-items: center;
            justify-content: center;
            font-weight: 700;
            font-size: 1.25rem;
            font-family: system-ui, sans-serif;
        }
        .brand-hero {
            background: linear-gradient(90deg, #7a8f66 0%, #97ab7d 100%);
            color: #0d1117;
            padding: 1rem 1.1rem;
            border-radius: 14px;
            margin-bottom: 1rem;
            border: 1px solid #c8d5b9;
            box-shadow: 0 5px 16px rgba(0,0,0,0.2);
        }
        .brand-title { font-size: 2rem; font-weight: 800; margin-bottom: 0.2rem; }
        .brand-tag { font-size: 1.1rem; font-weight: 700; margin-bottom: 0.2rem; }
        .brand-sub { font-size: 0.95rem; color: #111827; margin: 0; }
        .contact-card {
            background: #111827;
            border: 1px solid #334155;
            border-radius: 12px;
            padding: 0.9rem;
            margin-bottom: 0.7rem;
        }
        .optional-note {
            text-align: right;
            color: #aab3bf;
            margin-top: 0.4rem;
            font-size: 0.9rem;
        }
        [data-testid="stDataFrame"] { border-radius: 8px; overflow: hidden; }
        /* Hide Streamlit default "200MB per file • …" line; we show Symposia limits in captions instead */
        [data-testid="stFileUploaderDropzoneInstructions"],
        [data-testid="stFileUploader"] section small,
        [data-testid="stFileUploader"] small {
            display: none !important;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def _logout():
    for k in list(st.session_state.keys()):
        del st.session_state[k]
    st.rerun()


def _seed_profile_from_db(user_id: int) -> None:
    """Load DB profile into stable session keys (widgets unmount when switching pages)."""
    if st.session_state.get("_seed_uid") == user_id:
        return
    u = get_user_by_id(user_id)
    if not u:
        return
    st.session_state["_prof_interests_stored"] = u["interests"] or ""
    st.session_state["_prof_linkedin_stored"] = u["linkedin"] or ""
    st.session_state["resume_text"] = u["resume_text"] or ""
    img = u["profile_image_b64"] if "profile_image_b64" in u.keys() else ""
    img = img or ""
    st.session_state["_profile_image_data_url_stored"] = img
    st.session_state.pop("_profile_image_pending", None)
    st.session_state["_seed_uid"] = user_id


def _profile_image_url() -> str:
    return (
        st.session_state.get("_profile_image_pending")
        or st.session_state.get("_profile_image_data_url_stored")
        or ""
    )


def _render_avatar_top_right(username: str) -> None:
    url = _profile_image_url()
    initial = (username[:1] or "?").upper()
    if url:
        inner = f'<img class="cs-avatar" src="{html.escape(url)}" alt="Profile photo" />'
    else:
        inner = f'<div class="cs-avatar-placeholder">{html.escape(initial)}</div>'
    st.markdown(
        f'<div class="cs-avatar-wrap">'
        f'<a href="?nav=profile" title="Go to Your profile">{inner}</a>'
        f"</div>",
        unsafe_allow_html=True,
    )


def _consume_nav_query_param() -> None:
    try:
        nav = st.query_params.get("nav")
        if isinstance(nav, list):
            nav = nav[0] if nav else None
        if nav == "profile":
            st.session_state.nav_page = NAV_PROFILE
            del st.query_params["nav"]
    except Exception:
        pass


def _row_val(row, key: str, default: str = "") -> str:
    if row is None:
        return default
    try:
        if key in row.keys():
            return row[key] or default
    except Exception:
        pass
    return default


def _safe_json_list(raw: str) -> list[dict[str, Any]]:
    try:
        value = json.loads(raw or "[]")
        if isinstance(value, list):
            return value
    except json.JSONDecodeError:
        pass
    return []


def _render_brand_banner(page: str) -> None:
    descriptions = {
        NAV_PROFILE: "Built for undergraduates who want conferences to feel approachable, not overwhelming. Symposia keeps your core profile in one place so every conference starts with context and convenience.",
        NAV_CONFERENCES: "Plan each conference in a single workspace with schedule parsing, goals, and live question coaching. It is designed to compile your learning journey and networking steps in one organized repository.",
        NAV_CONTACTS: "Capture people you meet as editable cards so follow-up is simple and intentional. This page is optimized for convenience during busy conference days when details are easy to forget.",
        NAV_CALENDAR: "Export calendars, contacts, reflections, and conference packages in one click. Symposia helps you carry everything forward after the event without digging through scattered notes.",
        NAV_PRIVACY: "Your profile and conference records are yours, with local-first storage and explicit export/delete controls. This section centralizes data management so you can share only what you intend.",
        "auth": "Symposia helps undergraduate attendees turn conference chaos into clear, actionable learning. It is built with convenience in mind so networking notes, sessions, and reflections live in one reliable place.",
    }
    sub = descriptions.get(page, descriptions[NAV_CONFERENCES])
    st.markdown(
        f"""
        <div class="brand-hero">
            <div class="brand-title">🌿 Symposia 🌿</div>
            <div class="brand-tag">Networking made easy</div>
            <p class="brand-sub">{html.escape(sub)}</p>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _fmt_mdy(d: date) -> str:
    return d.strftime("%m-%d-%Y")


def _parse_mdy(s: str) -> date:
    s = (s or "").strip()
    if not s:
        return date.today()
    for fmt in ("%m-%d-%Y", "%Y-%m-%d"):
        try:
            from datetime import datetime

            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return date.today()


def _conf_dates_caption(start_s: str, end_s: str) -> str:
    """Human-readable stored MM-DD-YYYY (or legacy) range for UI copy."""
    start_s = (start_s or "").strip()
    end_s = (end_s or "").strip()
    if not start_s:
        return "set dates in My conferences → Prep"
    if not end_s or end_s == start_s:
        return start_s
    return f"{start_s} – {end_s}"


def _render_auth():
    _render_brand_banner("auth")
    tab_login, tab_signup = st.tabs(["Log in", "Sign up"])

    with tab_login:
        lu = st.text_input("Username", key="login_user")
        lp = st.text_input("Password", type="password", key="login_pass")
        if st.button("Log in", type="primary", key="login_btn"):
            row = get_user_by_username(lu)
            if not row or not verify_password(lp, row["password_hash"]):
                st.error("Invalid username or password.")
            else:
                st.session_state.auth_user_id = int(row["id"])
                st.session_state.auth_username = row["username"]
                st.rerun()

    with tab_signup:
        if "signup_step" not in st.session_state:
            st.session_state.signup_step = 1
        with st.expander("Step 1: Account credentials", expanded=st.session_state.signup_step == 1):
            su = st.text_input("Username", key="signup_user")
            sp = st.text_input("Password", type="password", key="signup_pass")
            sp2 = st.text_input("Confirm password", type="password", key="signup_pass2")
            if st.button("Continue Sign Up", key="signup_continue"):
                if not su.strip():
                    st.error("Choose a username.")
                elif len(sp) < 6:
                    st.error("Password must be at least 6 characters.")
                elif sp != sp2:
                    st.error("Passwords do not match.")
                else:
                    st.session_state.signup_step = 2
                    st.rerun()

        if st.session_state.signup_step >= 2:
            with st.expander("Step 2: Profile setup", expanded=True):
                interests = st.text_area("Interests", key="signup_interests", height=100)
                linkedin = st.text_input("LinkedIn Profile *optional", key="signup_linkedin")
                resume = st.file_uploader(
                    "Resume *optional",
                    key="signup_resume",
                    type=["pdf", "txt"],
                )
                st.caption(RESUME_LIMIT_TEXT)
                pic = st.file_uploader(
                    "Profile picture *optional",
                    key="signup_pic",
                    type=["png", "jpg", "jpeg"],
                )
                st.caption(PROFILE_PIC_LIMIT_TEXT)
                if resume is not None:
                    st.session_state.signup_resume_text = _resume_text_from_upload(resume)
                if pic is not None:
                    raw = pic.read()
                    if len(raw) <= PROFILE_PIC_MAX_BYTES:
                        b64s = base64.b64encode(raw).decode("ascii")
                        mime = pic.type or "image/jpeg"
                        st.session_state.signup_pic_b64 = f"data:{mime};base64,{b64s}"
                    else:
                        st.error(f"Profile image must be {PROFILE_PIC_MAX_BYTES // 1024} KB or smaller.")
                ready = st.checkbox("I completed this setup and can edit it later in Your profile.")
                if st.button("Create account", type="primary", key="signup_btn"):
                    if not interests.strip():
                        st.error("Interests are required.")
                    elif not ready:
                        st.error("Please confirm setup completion.")
                    else:
                        try:
                            uid = create_user(su.strip(), hash_password(sp))
                            update_user_profile(
                                uid,
                                interests.strip(),
                                linkedin.strip(),
                                st.session_state.get("signup_resume_text", ""),
                                profile_image_b64=st.session_state.get("signup_pic_b64", ""),
                            )
                            st.session_state.auth_user_id = uid
                            st.session_state.auth_username = su.strip().lower()
                            st.success("Account created.")
                            st.rerun()
                        except sqlite3.IntegrityError:
                            st.error("That username is already taken.")


def _render_profile(user_id: int):
    _render_brand_banner(NAV_PROFILE)
    st.write(
        "Interests, LinkedIn, resume, and profile photo are saved to your account. "
        "Fields stay filled when you switch pages. Click **Save profile** to persist changes."
    )

    # Widget keys are cleared when this page unmounts; re-seed from stable copies.
    if "prof_interests_ui" not in st.session_state:
        st.session_state["prof_interests_ui"] = st.session_state.get("_prof_interests_stored", "")
    if "prof_linkedin_ui" not in st.session_state:
        st.session_state["prof_linkedin_ui"] = st.session_state.get("_prof_linkedin_stored", "")

    st.text_area(
        "Interests",
        height=130,
        key="prof_interests_ui",
        placeholder="e.g. climate policy, HCI, first-gen student support",
    )
    st.text_input(
        "LinkedIn profile URL *optional",
        key="prof_linkedin_ui",
    )

    st.subheader("Profile photo")
    pic = st.file_uploader(
        "Upload a profile picture *optional (JPG or PNG)",
        type=["png", "jpg", "jpeg"],
        key="prof_pic_uploader",
    )
    st.caption(PROFILE_PIC_LIMIT_TEXT)
    if pic is not None:
        raw = pic.read()
        if len(raw) > PROFILE_PIC_MAX_BYTES:
            st.error(f"Image must be {PROFILE_PIC_MAX_BYTES // 1024} KB or smaller.")
        else:
            b64s = base64.b64encode(raw).decode("ascii")
            mime = pic.type or "image/jpeg"
            st.session_state["_profile_image_pending"] = f"data:{mime};base64,{b64s}"
            st.success("Photo loaded — click **Save profile** to store it.")

    resume_file = st.file_uploader(
        "Resume *optional (PDF or TXT)",
        type=["pdf", "txt"],
        key="prof_resume_file",
    )
    st.caption(RESUME_LIMIT_TEXT)
    if resume_file is not None:
        st.session_state.resume_text = _resume_text_from_upload(resume_file)
        n = len(st.session_state.resume_text)
        cap_note = f" (capped at {RESUME_TEXT_MAX_CHARS:,} chars)" if n >= RESUME_TEXT_MAX_CHARS else ""
        st.success(f"Resume loaded: **{n:,}** characters stored for this app{cap_note}. Click **Save profile** to persist.")

    if st.button("Save profile", type="primary", key="prof_save"):
        interests_val = st.session_state.get(
            "prof_interests_ui", st.session_state.get("_prof_interests_stored", "")
        )
        linkedin_val = st.session_state.get(
            "prof_linkedin_ui", st.session_state.get("_prof_linkedin_stored", "")
        )
        st.session_state["_prof_interests_stored"] = interests_val
        st.session_state["_prof_linkedin_stored"] = linkedin_val
        resume_val = st.session_state.get("resume_text") or ""
        img_val = _profile_image_url()
        update_user_profile(
            user_id,
            interests_val,
            linkedin_val,
            resume_val,
            profile_image_b64=img_val,
        )
        st.session_state["_profile_image_data_url_stored"] = img_val
        st.session_state.pop("_profile_image_pending", None)
        st.success("Profile saved.")

    st.session_state["_prof_interests_stored"] = st.session_state.get(
        "prof_interests_ui", st.session_state.get("_prof_interests_stored", "")
    )
    st.session_state["_prof_linkedin_stored"] = st.session_state.get(
        "prof_linkedin_ui", st.session_state.get("_prof_linkedin_stored", "")
    )

    rt = st.session_state.get("resume_text") or ""
    if rt:
        with st.expander("Saved resume preview (first 800 characters)"):
            snippet = rt[:800] + ("…" if len(rt) > 800 else "")
            st.markdown(
                f'<pre class="resume-pre">{html.escape(snippet)}</pre>',
                unsafe_allow_html=True,
            )
    st.markdown('<div class="optional-note">* = optional</div>', unsafe_allow_html=True)


def _sessions_from_row(row) -> list:
    try:
        return json.loads(row["sessions_json"] or "[]")
    except json.JSONDecodeError:
        return []


def _render_conference_workspace(user_id: int):
    _render_brand_banner(NAV_CONFERENCES)
    st.write(
        "Each conference has its own schedule, goals, and feelings. "
        "Upload the event program PDF in Prep, then click Save buttons after autofill actions so data persists."
    )

    pdel = st.session_state.get("conference_delete_pending")
    if pdel is not None:
        cid_pending = int(pdel)
        crow = get_conference(cid_pending, user_id)
        if crow is None:
            st.session_state.pop("conference_delete_pending", None)
        else:
            cnm = (crow["name"] or "").strip() or f"Conference #{cid_pending}"
            st.warning(
                f'Are you sure you want to delete **"{cnm}"**? This removes its schedule, reflections, '
                "and saved session questions from Symposia. Contacts linked only to this conference will lose that link. "
                "This cannot be undone."
            )
            c_yes, c_no = st.columns(2)
            with c_yes:
                if st.button("Yes, delete conference", type="primary", key="conference_delete_confirm_yes"):
                    delete_conference(cid_pending, user_id)
                    if st.session_state.get("sel_conf") == cid_pending:
                        st.session_state.pop("sel_conf", None)
                    st.session_state.pop("conference_delete_pending", None)
                    st.rerun()
            with c_no:
                if st.button("Cancel", key="conference_delete_confirm_no"):
                    st.session_state.pop("conference_delete_pending", None)
                    st.rerun()
            st.stop()

    rows = list_conferences(user_id)

    if "add_conf_expander_expanded" not in st.session_state:
        st.session_state.add_conf_expander_expanded = not rows
    elif not rows:
        st.session_state.add_conf_expander_expanded = True

    if "add_conf_form_id" not in st.session_state:
        st.session_state.add_conf_form_id = 0
    _acf = int(st.session_state.add_conf_form_id)

    with st.expander("➕ Add a conference", expanded=st.session_state.add_conf_expander_expanded):
        nn = st.text_input(
            "Conference name",
            key=f"new_conf_name_{_acf}",
            placeholder="e.g. ACM CHI 2026",
        )
        nd_start = st.date_input(
            "Conference start date",
            key=f"new_conf_date_start_{_acf}",
            value=date.today(),
            help="Used for sorting, labels, and as the default day when building .ics events from your schedule.",
        )
        nd_end = st.date_input(
            "Conference end date",
            key=f"new_conf_date_end_{_acf}",
            value=nd_start,
            min_value=nd_start,
            help="Last day of the symposium or multi-day event (can match the start date for a one-day event).",
        )
        if st.button("Create conference", key=f"new_conf_btn_{_acf}"):
            if not nn.strip():
                st.error("Enter a name.")
            else:
                cid = create_conference(
                    user_id,
                    nn.strip(),
                    event_date=_fmt_mdy(nd_start),
                    event_end_date=_fmt_mdy(nd_end),
                )
                st.session_state.sel_conf = cid
                st.session_state.add_conf_expander_expanded = False
                for _base in ("new_conf_name", "new_conf_date_start", "new_conf_date_end"):
                    st.session_state.pop(f"{_base}_{_acf}", None)
                st.session_state.pop(f"new_conf_btn_{_acf}", None)
                st.session_state.add_conf_form_id = _acf + 1
                st.rerun()

    if not rows:
        st.info("Create your first conference above.")
        return

    ids = [int(r["id"]) for r in rows]
    labels = {i: (r["name"] or f"Conference #{r['id']}") for i, r in zip(ids, rows)}

    if st.session_state.get("sel_conf") not in ids:
        st.session_state.sel_conf = ids[0]

    conf_id = st.selectbox(
        "Active conference",
        options=ids,
        format_func=lambda i: labels[i],
        key="sel_conf",
    )

    row = get_conference(conf_id, user_id)
    if not row:
        st.error("Conference not found.")
        return

    if st.button("Delete this conference", key=f"del_conf_{conf_id}"):
        st.session_state.conference_delete_pending = conf_id
        st.rerun()

    sub_prep, sub_during, sub_after = st.tabs(["Prep & schedule", "Session coach", "End of day"])

    with sub_prep:
        st.subheader(labels[conf_id])
        cname = st.text_input(
            "Conference name",
            value=row["name"] or "",
            key=f"cname_{conf_id}",
        )
        cdate = st.date_input(
            "Conference start date",
            value=_parse_mdy(_row_val(row, "event_date")),
            key=f"edate_{conf_id}",
            help="First day of the conference or symposium.",
        )
        end_raw = _row_val(row, "event_end_date")
        c_end_default = _parse_mdy(end_raw) if end_raw.strip() else _parse_mdy(_row_val(row, "event_date"))
        c_end = st.date_input(
            "Conference end date",
            value=max(cdate, c_end_default),
            min_value=cdate,
            key=f"eendate_{conf_id}",
            help="Last day of the event (same as start for a single-day conference).",
        )
        cgoals = st.text_area(
            "Goals for this conference",
            value=row["goals"] or "",
            height=100,
            key=f"cgoals_{conf_id}",
        )
        cfeel = st.selectbox(
            "How are you feeling about this conference?",
            ["Calm", "A little nervous", "Very anxious"],
            index=["Calm", "A little nervous", "Very anxious"].index(row["feelings"])
            if row["feelings"] in ["Calm", "A little nervous", "Very anxious"]
            else 1,
            key=f"cfeel_{conf_id}",
        )

        up = st.file_uploader(
            "Schedule PDF (upload the event program PDF for this conference)",
            type=["pdf"],
            key=f"cpdf_{conf_id}",
        )
        st.caption(
            "PDF only. The uploader may show a large max file size; Symposia only uses the PDF you choose here."
        )
        if up is not None:
            raw = extract_text_from_pdf_bytes(up.read())
            sessions = naive_session_parse(raw)
            update_conference(conf_id, user_id, sessions=sessions)
            st.success(f"Parsed {len(sessions)} session blocks. Saved to this conference.")

        sessions = _sessions_from_row(get_conference(conf_id, user_id) or row)
        if st.button("+ Add empty session row", key=f"add_sess_row_{conf_id}"):
            sessions.append({"time": "", "title": "", "speaker": "", "description": ""})
        sessions_edited = st.data_editor(
            sessions,
            use_container_width=True,
            num_rows="dynamic",
            key=f"sessions_editor_{conf_id}",
        )
        if st.button("Save conference details", type="primary", key=f"csave_{conf_id}"):
            if not cgoals.strip():
                st.error("Goals for this conference is required.")
                return
            if not cfeel.strip():
                st.error("Feeling is required.")
                return
            update_conference(
                conf_id,
                user_id,
                name=cname,
                goals=cgoals,
                feelings=cfeel,
                event_date=_fmt_mdy(cdate),
                event_end_date=_fmt_mdy(max(cdate, c_end)),
                sessions=sessions_edited,
            )
            st.success("Saved.")

    with sub_during:
        st.write(
            "Generate three questions for the current session using your **saved profile** "
            "and this conference’s goals and feelings."
        )
        u = get_user_by_id(user_id)
        interests = (
            st.session_state.get("_prof_interests_stored")
            or (u["interests"] if u else "")
            or "(not specified)"
        )
        resume_preview = st.session_state.get("resume_text") or (
            (u["resume_text"] if u else "") or "(no resume saved — add one in Profile)"
        )

        r2 = get_conference(conf_id, user_id) or row
        goals = r2["goals"] or "(not specified)"
        anxiety = r2["feelings"] or "A little nervous"

        st.text_input("Session title", key=f"sess_title_{conf_id}")
        st.text_input("Speaker", key=f"sess_speaker_{conf_id}")
        st.text_area(
            "Session description",
            key=f"sess_desc_{conf_id}",
            height=140,
        )

        sess_list = _sessions_from_row(r2)
        if sess_list:
            labels2 = [
                f"{s.get('time', '')} — {s.get('title', '')}" for s in sess_list
            ]
            pick = st.selectbox(
                "Quick pick from schedule",
                range(len(labels2)),
                format_func=lambda i: labels2[i],
                key=f"spick_{conf_id}",
            )
            if st.button("Fill session fields from schedule", key=f"sfill_{conf_id}"):
                s = sess_list[pick]
                st.session_state[f"sess_title_{conf_id}"] = s.get("title", "")
                st.session_state[f"sess_speaker_{conf_id}"] = s.get("speaker", "")
                st.session_state[f"sess_desc_{conf_id}"] = s.get("description", "")
                st.rerun()

        if st.button("Generate three questions", type="primary", key=f"qgen_{conf_id}"):
            prompt = QUESTION_PROMPT.format(
                interests=interests,
                goals=goals,
                resume_text=resume_preview,
                anxiety_note=anxiety,
                title=st.session_state.get(f"sess_title_{conf_id}") or "(untitled)",
                speaker=st.session_state.get(f"sess_speaker_{conf_id}") or "(unknown)",
                description=st.session_state.get(f"sess_desc_{conf_id}") or "(no description)",
            )
            qs, q_source = generate_questions(prompt)
            st.session_state[f"last_q_{conf_id}"] = qs
            st.session_state[f"last_q_source_{conf_id}"] = q_source
            history = _safe_json_list(_row_val(r2, "questions_json", "[]"))
            history.append(
                {
                    "generated_at": datetime.utcnow().isoformat() + "Z",
                    "session_title": st.session_state.get(f"sess_title_{conf_id}") or "",
                    "speaker": st.session_state.get(f"sess_speaker_{conf_id}") or "",
                    "q1": qs["q1"],
                    "q2": qs["q2"],
                    "q3": qs["q3"],
                }
            )
            update_conference(conf_id, user_id, questions=history)

        last = st.session_state.get(f"last_q_{conf_id}")
        if last:
            q_src = st.session_state.get(f"last_q_source_{conf_id}")
            if q_src:
                st.caption(q_src)
            st.markdown("**You could ask:**")
            st.markdown(f"- {last['q1']}")
            st.markdown(f"- {last['q2']}")
            st.markdown(f"- {last['q3']}")

    with sub_after:
        r_ref = get_conference(conf_id, user_id) or row
        dn0 = _row_val(r_ref, "reflection_day_notes")
        dc0 = _row_val(r_ref, "reflection_contacts")
        dt0 = _row_val(r_ref, "reflection_tomorrow")
        dai0 = _row_val(r_ref, "reflection_ai")
        if f"day_notes_{conf_id}" not in st.session_state:
            st.session_state[f"day_notes_{conf_id}"] = dn0
        if f"day_contacts_{conf_id}" not in st.session_state:
            st.session_state[f"day_contacts_{conf_id}"] = dc0
        if f"day_tomorrow_{conf_id}" not in st.session_state:
            st.session_state[f"day_tomorrow_{conf_id}"] = dt0
        if f"refl_out_{conf_id}" not in st.session_state and dai0:
            st.session_state[f"refl_out_{conf_id}"] = dai0

        st.text_area(
            "What happened today?",
            height=100,
            key=f"day_notes_{conf_id}",
        )
        st.text_area(
            "Who did you meet?",
            height=80,
            key=f"day_contacts_{conf_id}",
        )
        st.text_area(
            "Tomorrow’s sessions or goals",
            height=60,
            key=f"day_tomorrow_{conf_id}",
        )
        b1, b2 = st.columns(2)
        with b1:
            if st.button("Save reflection notes", key=f"rsave_{conf_id}"):
                update_conference(
                    conf_id,
                    user_id,
                    reflection_day_notes=st.session_state.get(f"day_notes_{conf_id}") or "",
                    reflection_contacts=st.session_state.get(f"day_contacts_{conf_id}") or "",
                    reflection_tomorrow=st.session_state.get(f"day_tomorrow_{conf_id}") or "",
                    reflection_ai=st.session_state.get(f"refl_out_{conf_id}") or "",
                )
                st.success("Reflection saved.")
        with b2:
            if st.button("Synthesize my day (AI)", type="primary", key=f"refl_{conf_id}"):
                prompt = REFLECTION_PROMPT.format(
                    notes=st.session_state.get(f"day_notes_{conf_id}") or "(nothing yet)",
                    contacts=st.session_state.get(f"day_contacts_{conf_id}") or "(none noted)",
                    tomorrow_sessions=st.session_state.get(f"day_tomorrow_{conf_id}")
                    or "(not specified)",
                )
                out = generate_reflection(prompt)
                st.session_state[f"refl_out_{conf_id}"] = out
                update_conference(
                    conf_id,
                    user_id,
                    reflection_day_notes=st.session_state.get(f"day_notes_{conf_id}") or "",
                    reflection_contacts=st.session_state.get(f"day_contacts_{conf_id}") or "",
                    reflection_tomorrow=st.session_state.get(f"day_tomorrow_{conf_id}") or "",
                    reflection_ai=out,
                )

        out = st.session_state.get(f"refl_out_{conf_id}")
        if out:
            st.markdown(out)
            u = get_user_by_id(user_id)
            uname = u["username"] if u else "user"
            cnm = _row_val(r_ref, "name") or labels[conf_id]
            ed = _row_val(r_ref, "event_date")
            eed = _row_val(r_ref, "event_end_date")
            md = build_reflection_report_md(
                uname,
                cnm,
                ed,
                st.session_state.get(f"day_notes_{conf_id}") or "",
                st.session_state.get(f"day_contacts_{conf_id}") or "",
                st.session_state.get(f"day_tomorrow_{conf_id}") or "",
                out,
                event_end_date=eed,
            )
            st.download_button(
                "Download reflection (.md)",
                md,
                file_name=f"reflection_{conf_id}.md",
                mime="text/markdown",
                key=f"dl_refl_{conf_id}",
            )
            conf_payload = row_to_dict(r_ref)
            conf_payload["questions_history"] = _safe_json_list(_row_val(r_ref, "questions_json", "[]"))
            conf_contacts = [row_to_dict(x) for x in list_contacts_for_conference(user_id, conf_id)]
            st.download_button(
                "Download full conference package (.json)",
                build_conference_package_json(conf_payload, conf_contacts),
                file_name=f"conference_package_{conf_id}.json",
                mime="application/json",
                key=f"dl_package_{conf_id}",
            )


def _render_contacts(user_id: int) -> None:
    _render_brand_banner(NAV_CONTACTS)

    pdel = st.session_state.get("contact_delete_pending")
    if pdel is not None:
        crow = get_contact(int(pdel), user_id)
        if crow is None:
            st.session_state.pop("contact_delete_pending", None)
        else:
            dnm = (crow["name"] or "").strip() or "this contact"
            st.warning(f'Are you sure you want to delete **"{dnm}"**? This cannot be undone.')
            c_yes, c_no = st.columns(2)
            with c_yes:
                if st.button("Yes, delete contact", type="primary", key="contact_delete_confirm_yes"):
                    delete_contact(int(pdel), user_id)
                    st.session_state.pop("contact_delete_pending", None)
                    st.rerun()
            with c_no:
                if st.button("Cancel", key="contact_delete_confirm_no"):
                    st.session_state.pop("contact_delete_pending", None)
                    st.rerun()
            st.stop()

    confs = list_conferences(user_id)
    cmap: dict[int, str] = {int(c["id"]): (c["name"] or f"#{c['id']}") for c in confs}
    cmap[0] = "(No conference)"

    if st.session_state.pop("contact_saved_flash", False):
        st.success("Contact saved.")

    conf_options = [0] + [int(c["id"]) for c in confs]
    with st.expander("Add a contact", expanded=True):
        cid_pick = st.selectbox(
            "Conference",
            options=conf_options,
            format_func=lambda i: cmap.get(i, "?"),
            key="add_contact_conf",
        )
        st.text_input("Name *", key="add_contact_name")
        st.text_input("Organization", key="add_contact_org")
        st.text_input("Email", key="add_contact_email")
        st.text_input("LinkedIn URL", key="add_contact_li")
        st.text_input("Topics / how you met", key="add_contact_topics")
        st.text_area("Notes", key="add_contact_notes", height=80)
        card = st.file_uploader(
            "Business card (image)",
            type=["png", "jpg", "jpeg"],
            key="add_contact_card",
        )
        st.caption(PROFILE_PIC_LIMIT_TEXT)
        if card is not None:
            raw = card.read()
            st.session_state["new_card_raw"] = raw
            st.session_state["new_card_mime"] = card.type or "image/jpeg"
            if st.button("Autofill from business card image", key="autofill_card_btn"):
                inferred = parse_business_card(raw, st.session_state["new_card_mime"])
                if inferred:
                    st.session_state["add_contact_name"] = inferred.get("name", st.session_state.get("add_contact_name", ""))
                    st.session_state["add_contact_org"] = inferred.get("org", st.session_state.get("add_contact_org", ""))
                    st.session_state["add_contact_email"] = inferred.get("email", st.session_state.get("add_contact_email", ""))
                    st.session_state["add_contact_li"] = inferred.get("linkedin_url", st.session_state.get("add_contact_li", ""))
                    st.session_state["add_contact_topics"] = inferred.get("topics", st.session_state.get("add_contact_topics", ""))
                    st.success("Autofill applied. Review and save.")
                    st.rerun()
                else:
                    st.info("Could not autofill. You can still enter details manually.")
        if st.button("Save contact", key="add_contact_btn"):
            name = st.session_state.get("add_contact_name", "")
            if not name.strip():
                st.error("Name is required.")
            else:
                raw = st.session_state.get("new_card_raw")
                mime = st.session_state.get("new_card_mime", "image/jpeg")
                card_b64 = ""
                if raw:
                    card_b64 = f"data:{mime};base64,{base64.b64encode(raw).decode('ascii')}"
                add_contact(
                    user_id,
                    None if cid_pick == 0 else int(cid_pick),
                    name.strip(),
                    org=st.session_state.get("add_contact_org", ""),
                    email=st.session_state.get("add_contact_email", ""),
                    linkedin_url=st.session_state.get("add_contact_li", ""),
                    topics=st.session_state.get("add_contact_topics", ""),
                    notes=st.session_state.get("add_contact_notes", ""),
                    business_card_b64=card_b64,
                )
                for key in [
                    "add_contact_name",
                    "add_contact_org",
                    "add_contact_email",
                    "add_contact_li",
                    "add_contact_topics",
                    "add_contact_notes",
                    "add_contact_card",
                    "new_card_raw",
                    "new_card_mime",
                ]:
                    st.session_state.pop(key, None)
                st.session_state.contact_saved_flash = True
                st.rerun()

    rows = [row_to_dict(r) for r in list_contacts(user_id)]
    if not rows:
        st.info("No contacts yet.")
        return

    for r in rows:
        cid = int(r["id"])
        edit_key = f"edit_contact_{cid}"
        ccid = r["conference_id"]
        clabel = cmap.get(int(ccid), f"Conference {ccid}") if ccid is not None else "(No conference)"
        st.markdown('<div class="contact-card">', unsafe_allow_html=True)
        st.markdown(f"**{r['name']}**")
        st.caption(f"Conference: {clabel}")
        if r.get("org"):
            st.caption(f"Org: {r['org']}")
        if r.get("email"):
            st.caption(f"Email: {r['email']}")
        if r.get("linkedin_url"):
            st.caption(f"LinkedIn: {r['linkedin_url']}")
        if r.get("topics"):
            st.caption(f"Topics: {r['topics']}")
        if r.get("notes"):
            st.text(str(r["notes"])[:400])

        c1, c2, c3 = st.columns([3, 2, 1])
        with c2:
            if st.button("✏️ EDIT CONTACT", key=f"toggle_edit_{cid}"):
                st.session_state[edit_key] = not st.session_state.get(edit_key, False)
                st.rerun()
        with c3:
            if st.button("Delete", key=f"delcon_{cid}"):
                st.session_state.contact_delete_pending = cid
                st.rerun()

        if st.session_state.get(edit_key, False):
            opts = [0] + [int(c["id"]) for c in confs]
            current_conf = int(r["conference_id"]) if r.get("conference_id") else 0
            e_name = st.text_input("Name", value=r.get("name", ""), key=f"e_name_{cid}")
            e_conf = st.selectbox(
                "Conference",
                opts,
                index=opts.index(current_conf) if current_conf in opts else 0,
                format_func=lambda i: cmap.get(i, "(No conference)"),
                key=f"e_conf_{cid}",
            )
            e_org = st.text_input("Organization", value=r.get("org", ""), key=f"e_org_{cid}")
            e_email = st.text_input("Email", value=r.get("email", ""), key=f"e_email_{cid}")
            e_li = st.text_input("LinkedIn", value=r.get("linkedin_url", ""), key=f"e_li_{cid}")
            e_topics = st.text_input("Topics", value=r.get("topics", ""), key=f"e_topics_{cid}")
            e_notes = st.text_area("Notes", value=r.get("notes", ""), key=f"e_notes_{cid}", height=80)
            up = st.file_uploader(
                "Replace business card image (optional)",
                type=["png", "jpg", "jpeg"],
                key=f"e_card_{cid}",
            )
            st.caption(PROFILE_PIC_LIMIT_TEXT)
            card_b64 = None
            if up is not None:
                raw = up.read()
                if len(raw) <= PROFILE_PIC_MAX_BYTES:
                    mime = up.type or "image/jpeg"
                    card_b64 = f"data:{mime};base64,{base64.b64encode(raw).decode('ascii')}"
                else:
                    st.error(f"Business card image must be {PROFILE_PIC_MAX_BYTES // 1024} KB or smaller.")
            if st.button("Save contact changes", type="primary", key=f"save_edit_{cid}"):
                if not e_name.strip():
                    st.error("Name is required.")
                else:
                    update_contact(
                        cid,
                        user_id,
                        conference_id=None if e_conf == 0 else int(e_conf),
                        name=e_name.strip(),
                        org=e_org,
                        email=e_email,
                        linkedin_url=e_li,
                        topics=e_topics,
                        notes=e_notes,
                        business_card_b64=card_b64,
                    )
                    st.success("Contact updated.")
                    st.session_state[edit_key] = False
                    st.rerun()
        st.markdown("</div>", unsafe_allow_html=True)


def _render_calendar_exports(user_id: int) -> None:
    _render_brand_banner(NAV_CALENDAR)
    st.write(
        "Download an **.ics** calendar for each conference (from its saved schedule). "
        "Export **contacts** as CSV — all contacts, or per conference when applicable."
    )

    confs = list_conferences(user_id)
    conf_map = {int(c["id"]): (c["name"] or f"Conference {c['id']}") for c in confs}
    if confs:
        st.subheader("Conference schedules (.ics)")
        for c in confs:
            cid = int(c["id"])
            nm = c["name"] or f"Conference #{cid}"
            ed = _row_val(c, "event_date")
            eed = _row_val(c, "event_end_date")
            st.markdown(f"**{nm}** — _{_conf_dates_caption(ed, eed)}_")
            sess: list = []
            try:
                sess = json.loads(c["sessions_json"] or "[]")
            except json.JSONDecodeError:
                sess = []
            if not sess:
                st.caption("Upload and parse a schedule PDF under **My conferences** first.")
            ics = build_conference_ics(nm, ed, sess)
            st.download_button(
                f"Download .ics — {nm}",
                ics,
                file_name=f"conference_{cid}.ics",
                mime="text/calendar",
                key=f"ics_{cid}",
            )


    st.subheader("Contacts (CSV)")
    contacts_list = [row_to_dict(r) for r in list_contacts(user_id)]
    st.download_button(
        "Download all contacts (.csv)",
        contacts_to_csv(contacts_list, conf_map),
        file_name="contacts.csv",
        mime="text/csv",
        key="dl_csv_all",
    )

    if confs:
        st.subheader("Per-conference contacts (CSV)")
        for c in confs:
            cid = int(c["id"])
            rows_c = [
                row_to_dict(r)
                for r in list_contacts_for_conference(user_id, cid)
            ]
            if not rows_c:
                continue
            nm = c["name"] or f"Conference #{cid}"
            st.download_button(
                f"CSV — {nm}",
                contacts_to_csv(rows_c, conf_map),
                file_name=f"contacts_conference_{cid}.csv",
                mime="text/csv",
                key=f"csv_cc_{cid}",
            )


def _render_privacy(user_id: int, username: str) -> None:
    _render_brand_banner(NAV_PRIVACY)
    with st.expander("How your data is handled", expanded=False):
        st.markdown(
            """
- Data is stored in a **local SQLite** file (`data/app.db`) on the machine running Streamlit.
- **Passwords** are hashed (PBKDF2). Do not reuse an important password for this demo.
- **Resumes, reflections, contacts, and photos** are sensitive. Do not expose this app or the database on the public internet without proper security review, HTTPS, and hosting policies.
- Use **Export** below for a portable JSON copy. **Delete account** removes your user row and related conferences and contacts in this database.
            """
        )
    bundle = export_user_data(user_id)
    st.subheader("Export a copy of your data")
    st.download_button(
        "Download my data (.json)",
        json.dumps(bundle, indent=2, default=str),
        file_name=f"conference_scaffolding_export_{user_id}.json",
        mime="application/json",
        key="dl_json_privacy",
    )
    st.subheader("Delete account")
    st.warning(
        "Permanently deletes your profile, conferences, contacts, and saved reflections."
    )
    check1 = st.checkbox("I understand this action cannot be undone.", key="del_chk_1")
    check2 = st.checkbox("I understand all conferences and contacts will be deleted.", key="del_chk_2")
    phrase = st.text_input("Type DELETE to confirm", key="del_phrase")
    confirm = st.text_input(
        f"Type your username (`{username}`) to confirm deletion",
        key="del_account_confirm",
    )
    if st.button("Delete my account permanently", type="primary", key="del_account_btn"):
        if not (check1 and check2):
            st.error("Please check both confirmation boxes.")
        elif phrase.strip() != "DELETE":
            st.error("Type DELETE exactly.")
        elif confirm.strip().lower() == username.lower():
            delete_user(user_id)
            st.success("Account deleted.")
            _logout()
        else:
            st.error("Username does not match — nothing was deleted.")


def main():
    st.set_page_config(page_title="Symposia", layout="wide")
    init_db()
    _apply_theme()

    if "auth_user_id" not in st.session_state:
        _render_auth()
        st.divider()
        st.caption(
            "Tip: set `OPENAI_API_KEY` in `.env` for AI-generated questions and reflections."
        )
        return

    user_id = int(st.session_state.auth_user_id)
    username = st.session_state.get("auth_username", "user")
    _seed_profile_from_db(user_id)

    if st.session_state.get("nav_page") == "My profile":
        st.session_state.nav_page = NAV_PROFILE

    if "nav_page" not in st.session_state:
        st.session_state.nav_page = NAV_PROFILE

    _consume_nav_query_param()

    nav_labels = [
        NAV_PROFILE,
        NAV_CONFERENCES,
        NAV_CONTACTS,
        NAV_CALENDAR,
        NAV_PRIVACY,
    ]

    with st.sidebar:
        st.markdown("### Account")
        st.write(f"Signed in as **{username}**")
        if st.button("Log out"):
            _logout()
        st.divider()
        st.markdown("**Pages**")
        for i, label in enumerate(nav_labels):
            if st.button(
                label,
                key=f"sidebar_nav_{i}",
                use_container_width=True,
                type="primary" if st.session_state.nav_page == label else "secondary",
            ):
                st.session_state.nav_page = label
                st.rerun()

    _render_avatar_top_right(username)

    pg = st.session_state.nav_page
    if pg != NAV_CONTACTS:
        st.session_state.pop("contact_delete_pending", None)
    if pg != NAV_CONFERENCES:
        st.session_state.pop("conference_delete_pending", None)

    if pg == NAV_PROFILE:
        _render_profile(user_id)
    elif pg == NAV_CONFERENCES:
        _render_conference_workspace(user_id)
    elif pg == NAV_CONTACTS:
        _render_contacts(user_id)
    elif pg == NAV_CALENDAR:
        _render_calendar_exports(user_id)
    elif pg == NAV_PRIVACY:
        _render_privacy(user_id, username)

    st.divider()
    st.caption(
        "Tip: copy `.env.example` to `.env` and add `GEMINI_API_KEY` (recommended) or "
        "`OPENAI_API_KEY` for AI features. Data is stored locally in `data/app.db`."
    )


if __name__ == "__main__":
    main()
