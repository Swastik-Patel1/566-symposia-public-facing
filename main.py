"""Conference Scaffolding — Streamlit app with auth, profile, and multi-conference workspaces."""

import base64
import html
import json
import sqlite3
from datetime import date

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
    get_user_by_id,
    get_user_by_username,
    init_db,
    list_conferences,
    list_contacts,
    list_contacts_for_conference,
    row_to_dict,
    update_conference,
    update_user_profile,
)
from app.exports import (
    build_conference_ics,
    build_reflection_report_md,
    contacts_to_csv,
)
from app.llm import generate_questions, generate_reflection
from app.parser import extract_text_from_pdf_bytes, naive_session_parse
from app.prompts import QUESTION_PROMPT, REFLECTION_PROMPT

NAV_PROFILE = "Your profile"
NAV_CONFERENCES = "My conferences"
NAV_CONTACTS = "Contacts"
NAV_CALENDAR = "Calendar & exports"
NAV_PRIVACY = "Privacy & data"


def _resume_text_from_upload(uploaded) -> str:
    if uploaded is None:
        return ""
    name = uploaded.name.lower()
    data = uploaded.read()
    if name.endswith(".pdf"):
        return extract_text_from_pdf_bytes(data)[:12000]
    try:
        return data.decode("utf-8", errors="replace")[:12000]
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
        [data-testid="stDataFrame"] { border-radius: 8px; overflow: hidden; }
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


def _render_auth():
    st.title("Conference Scaffolding")
    st.caption("Sign up or log in to save your profile and conferences.")

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
                st.session_state.pop("_seed_uid", None)
                st.rerun()

    with tab_signup:
        su = st.text_input("Username", key="signup_user")
        sp = st.text_input("Password", type="password", key="signup_pass")
        sp2 = st.text_input("Confirm password", type="password", key="signup_pass2")
        if st.button("Create account", type="primary", key="signup_btn"):
            if not su.strip():
                st.error("Choose a username.")
            elif len(sp) < 6:
                st.error("Password must be at least 6 characters.")
            elif sp != sp2:
                st.error("Passwords do not match.")
            else:
                try:
                    uid = create_user(su.strip(), hash_password(sp))
                    st.session_state.auth_user_id = uid
                    st.session_state.auth_username = su.strip().lower()
                    st.session_state.pop("_seed_uid", None)
                    st.success("Account created. Loading your workspace…")
                    st.rerun()
                except sqlite3.IntegrityError:
                    st.error("That username is already taken.")


def _render_profile(user_id: int):
    st.header("Your profile")
    st.write(
        "Interests, LinkedIn, resume, and profile photo are saved to your account. "
        "Fields stay filled when you switch pages — click **Save profile** to write them to the database."
    )

    # Widget keys are cleared when this page unmounts; re-seed from stable copies.
    if "prof_interests_ui" not in st.session_state:
        st.session_state["prof_interests_ui"] = st.session_state.get("_prof_interests_stored", "")
    if "prof_linkedin_ui" not in st.session_state:
        st.session_state["prof_linkedin_ui"] = st.session_state.get("_prof_linkedin_stored", "")

    col1, col2 = st.columns(2)
    with col1:
        st.text_area(
            "Interests",
            height=120,
            key="prof_interests_ui",
            placeholder="e.g. climate policy, HCI, first-gen student support",
        )
    with col2:
        st.text_input(
            "LinkedIn profile URL (optional)",
            key="prof_linkedin_ui",
        )

    st.subheader("Profile photo")
    pic = st.file_uploader(
        "Upload a profile picture (JPG or PNG)",
        type=["png", "jpg", "jpeg"],
        key="prof_pic_uploader",
    )
    if pic is not None:
        raw = pic.read()
        if len(raw) > 500_000:
            st.error("Image must be under 500 KB. Try a smaller file.")
        else:
            b64s = base64.b64encode(raw).decode("ascii")
            mime = pic.type or "image/jpeg"
            st.session_state["_profile_image_pending"] = f"data:{mime};base64,{b64s}"
            st.success("Photo loaded — click **Save profile** to store it.")

    resume_file = st.file_uploader(
        "Resume (PDF or TXT)",
        type=["pdf", "txt"],
        key="prof_resume_file",
    )
    if resume_file is not None:
        st.session_state.resume_text = _resume_text_from_upload(resume_file)
        st.success(f"Resume loaded ({len(st.session_state.resume_text)} characters). Click Save to store.")

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


def _sessions_from_row(row) -> list:
    try:
        return json.loads(row["sessions_json"] or "[]")
    except json.JSONDecodeError:
        return []


def _render_conference_workspace(user_id: int):
    st.header("My conferences")
    st.write(
        "Each conference has its own schedule, goals, and feelings. "
        "Switch conferences below; open the tabs inside a conference for prep, questions, and reflection."
    )

    rows = list_conferences(user_id)

    with st.expander("➕ Add a conference", expanded=not rows):
        nn = st.text_input("Conference name", key="new_conf_name", placeholder="e.g. ACM CHI 2026")
        nd = st.text_input(
            "Conference date (YYYY-MM-DD), optional",
            key="new_conf_date",
            placeholder="2026-06-15",
            help="Used for calendar sorting and .ics export.",
        )
        if st.button("Create conference", key="new_conf_btn"):
            if not nn.strip():
                st.error("Enter a name.")
            else:
                dpart = nd.strip()[:10] if nd.strip() else ""
                if dpart:
                    try:
                        date.fromisoformat(dpart)
                    except ValueError:
                        st.error("Date must be YYYY-MM-DD (e.g. 2026-06-15).")
                        return
                cid = create_conference(user_id, nn.strip(), event_date=dpart)
                st.session_state.sel_conf = cid
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
        delete_conference(conf_id, user_id)
        st.session_state.pop("sel_conf", None)
        st.rerun()

    sub_prep, sub_during, sub_after = st.tabs(["Prep & schedule", "Session coach", "End of day"])

    with sub_prep:
        st.subheader(labels[conf_id])
        cname = st.text_input(
            "Conference name",
            value=row["name"] or "",
            key=f"cname_{conf_id}",
        )
        edate_val = _row_val(row, "event_date")
        cdate_str = st.text_input(
            "Conference date (YYYY-MM-DD), optional",
            value=edate_val,
            key=f"edate_{conf_id}",
            help="Shown on the Calendar page and used when exporting your schedule to .ics.",
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
            "Schedule PDF",
            type=["pdf"],
            key=f"cpdf_{conf_id}",
        )
        if up is not None:
            raw = extract_text_from_pdf_bytes(up.read())
            sessions = naive_session_parse(raw)
            update_conference(conf_id, user_id, sessions=sessions)
            st.success(f"Parsed {len(sessions)} session blocks. Saved to this conference.")

        sessions = _sessions_from_row(get_conference(conf_id, user_id) or row)
        if st.button("Save conference details", type="primary", key=f"csave_{conf_id}"):
            dpart = (cdate_str or "").strip()[:10]
            if dpart:
                try:
                    date.fromisoformat(dpart)
                except ValueError:
                    st.error("Date must be YYYY-MM-DD or leave blank.")
                    return
            update_conference(
                conf_id,
                user_id,
                name=cname,
                goals=cgoals,
                feelings=cfeel,
                event_date=dpart,
            )
            st.success("Saved.")

        if sessions:
            st.subheader("Parsed schedule (heuristic)")
            st.dataframe(sessions[:50], use_container_width=True)

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
            qs = generate_questions(prompt)
            st.session_state[f"last_q_{conf_id}"] = qs

        last = st.session_state.get(f"last_q_{conf_id}")
        if last:
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
            md = build_reflection_report_md(
                uname,
                cnm,
                ed,
                st.session_state.get(f"day_notes_{conf_id}") or "",
                st.session_state.get(f"day_contacts_{conf_id}") or "",
                st.session_state.get(f"day_tomorrow_{conf_id}") or "",
                out,
            )
            st.download_button(
                "Download reflection (.md)",
                md,
                file_name=f"reflection_{conf_id}.md",
                mime="text/markdown",
                key=f"dl_refl_{conf_id}",
            )


def _render_contacts(user_id: int) -> None:
    st.header("Contacts")
    st.write(
        "Track people you meet. Tie each contact to a conference when it helps you remember context. "
        "Export CSVs from **Calendar & exports**."
    )
    confs = list_conferences(user_id)
    cmap: dict[int, str] = {int(c["id"]): (c["name"] or f"#{c['id']}") for c in confs}
    cmap[0] = "(No conference)"

    conf_options = [0] + [int(c["id"]) for c in confs]
    with st.expander("Add a contact", expanded=True):
        cid_pick = st.selectbox(
            "Conference",
            options=conf_options,
            format_func=lambda i: cmap.get(i, "?"),
            key="add_contact_conf",
        )
        cn = st.text_input("Name *", key="add_contact_name")
        co = st.text_input("Organization", key="add_contact_org")
        ce = st.text_input("Email", key="add_contact_email")
        cl = st.text_input("LinkedIn URL", key="add_contact_li")
        ct = st.text_input("Topics / how you met", key="add_contact_topics")
        cnotes = st.text_area("Notes", key="add_contact_notes", height=80)
        card = st.file_uploader(
            "Business card (image)", type=["png", "jpg", "jpeg"], key="add_contact_card"
        )
        card_b64 = ""
        if card is not None:
            raw = card.read()
            if len(raw) > 400_000:
                st.error("Image too large (max ~400 KB).")
            else:
                mime = card.type or "image/jpeg"
                card_b64 = (
                    f"data:{mime};base64,{base64.b64encode(raw).decode('ascii')}"
                )
        if st.button("Save contact", key="add_contact_btn"):
            if not cn.strip():
                st.error("Name is required.")
            else:
                add_contact(
                    user_id,
                    None if cid_pick == 0 else int(cid_pick),
                    cn.strip(),
                    org=co,
                    email=ce,
                    linkedin_url=cl,
                    topics=ct,
                    notes=cnotes,
                    business_card_b64=card_b64,
                )
                st.success("Contact saved.")
                st.rerun()

    rows = list_contacts(user_id)
    if not rows:
        st.info("No contacts yet.")
        return

    for r in rows:
        ccid = r["conference_id"]
        if ccid is not None:
            clabel = cmap.get(int(ccid), f"Conference {ccid}")
        else:
            clabel = "(No conference)"
        with st.container():
            st.markdown(f"**{r['name']}** — _{clabel}_")
            cols = st.columns([4, 1])
            with cols[0]:
                if r["org"]:
                    st.caption(r["org"])
                if r["email"]:
                    st.caption(r["email"])
                if r["linkedin_url"]:
                    st.caption(r["linkedin_url"])
                if r["topics"]:
                    st.caption(r["topics"])
                if r["notes"]:
                    st.text(str(r["notes"])[:500])
            with cols[1]:
                if st.button("Delete", key=f"delcon_{r['id']}"):
                    delete_contact(int(r["id"]), user_id)
                    st.rerun()
            st.divider()


def _render_calendar_exports(user_id: int) -> None:
    st.header("Calendar & exports")
    st.write(
        "Download an **.ics** calendar for each conference (from its saved schedule). "
        "Export **contacts** as CSV — all contacts, or per conference when applicable."
    )

    confs = list_conferences(user_id)
    if confs:
        st.subheader("Conference schedules (.ics)")
        for c in confs:
            cid = int(c["id"])
            nm = c["name"] or f"Conference #{cid}"
            ed = _row_val(c, "event_date")
            st.markdown(f"**{nm}** — _{ed or 'set date in My conferences → Prep'}_")
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
        contacts_to_csv(contacts_list),
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
                contacts_to_csv(rows_c),
                file_name=f"contacts_conference_{cid}.csv",
                mime="text/csv",
                key=f"csv_cc_{cid}",
            )


def _render_privacy(user_id: int, username: str) -> None:
    st.header("Privacy & data")
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
    confirm = st.text_input(
        f"Type your username (`{username}`) to confirm deletion",
        key="del_account_confirm",
    )
    if st.button("Delete my account permanently", type="primary", key="del_account_btn"):
        if confirm.strip().lower() == username.lower():
            delete_user(user_id)
            st.success("Account deleted.")
            _logout()
        else:
            st.error("Username does not match — nothing was deleted.")


def main():
    st.set_page_config(page_title="Conference Scaffolding", layout="wide")
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

    st.title("Conference Scaffolding")
    st.caption(
        "Realistic, low-pressure support for undergrads exploring conferences — "
        "saved profile and one workspace per conference."
    )

    pg = st.session_state.nav_page
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
        "Tip: copy `.env.example` to `.env` and add `OPENAI_API_KEY` for AI-generated "
        "questions and reflections. Data is stored locally in `data/app.db`."
    )


if __name__ == "__main__":
    main()
