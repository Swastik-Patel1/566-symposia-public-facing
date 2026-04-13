"""Conference Scaffolding — Streamlit app with auth, profile, and multi-conference workspaces."""

import json
import sqlite3

import streamlit as st

from app.auth import hash_password, verify_password
from app.db import (
    create_conference,
    create_user,
    delete_conference,
    get_conference,
    get_user_by_id,
    get_user_by_username,
    init_db,
    list_conferences,
    update_conference,
    update_user_profile,
)
from app.llm import generate_questions, generate_reflection
from app.parser import extract_text_from_pdf_bytes, naive_session_parse
from app.prompts import QUESTION_PROMPT, REFLECTION_PROMPT


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
            background: linear-gradient(
                135deg,
                #ff9ecf 0%,
                #ffb347 45%,
                #1faa59 100%
            );
            background-attachment: fixed;
        }
        .block-container {
            background: rgba(255, 255, 255, 0.82);
            border-radius: 16px;
            padding: 2rem 2rem 2.5rem 2rem;
            margin-top: 1.5rem;
            margin-bottom: 1.5rem;
        }
        h1, h2, h3, p, label, div {
            color: #1f2937;
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
    if st.session_state.get("_seed_uid") == user_id:
        return
    u = get_user_by_id(user_id)
    if not u:
        return
    st.session_state["prof_interests"] = u["interests"] or ""
    st.session_state["prof_linkedin"] = u["linkedin"] or ""
    st.session_state["resume_text"] = u["resume_text"] or ""
    st.session_state["_seed_uid"] = user_id


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
    st.write("Interests, LinkedIn, and resume are saved to your account and reused for every conference.")

    col1, col2 = st.columns(2)
    with col1:
        st.text_area(
            "Interests",
            height=120,
            key="prof_interests",
            placeholder="e.g. climate policy, HCI, first-gen student support",
        )
    with col2:
        st.text_input(
            "LinkedIn profile URL (optional)",
            key="prof_linkedin",
        )

    resume_file = st.file_uploader(
        "Resume (PDF or TXT)",
        type=["pdf", "txt"],
        key="prof_resume_file",
    )
    if resume_file is not None:
        st.session_state.resume_text = _resume_text_from_upload(resume_file)
        st.success(f"Resume loaded ({len(st.session_state.resume_text)} characters). Click Save to store.")

    if st.button("Save profile", type="primary", key="prof_save"):
        update_user_profile(
            user_id,
            st.session_state.get("prof_interests") or "",
            st.session_state.get("prof_linkedin") or "",
            st.session_state.get("resume_text") or "",
        )
        st.success("Profile saved.")

    rt = st.session_state.get("resume_text") or ""
    if rt:
        with st.expander("Saved resume preview (first 800 characters)"):
            st.text(rt[:800] + ("…" if len(rt) > 800 else ""))


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
        if st.button("Create conference", key="new_conf_btn"):
            if not nn.strip():
                st.error("Enter a name.")
            else:
                cid = create_conference(user_id, nn.strip())
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
            update_conference(
                conf_id,
                user_id,
                name=cname,
                goals=cgoals,
                feelings=cfeel,
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
        interests = (u["interests"] if u else "") or "(not specified)"
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
        if st.button("Synthesize my day", type="primary", key=f"refl_{conf_id}"):
            prompt = REFLECTION_PROMPT.format(
                notes=st.session_state.get(f"day_notes_{conf_id}") or "(nothing yet)",
                contacts=st.session_state.get(f"day_contacts_{conf_id}") or "(none noted)",
                tomorrow_sessions=st.session_state.get(f"day_tomorrow_{conf_id}")
                or "(not specified)",
            )
            st.session_state[f"refl_out_{conf_id}"] = generate_reflection(prompt)

        out = st.session_state.get(f"refl_out_{conf_id}")
        if out:
            st.markdown(out)


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

    with st.sidebar:
        st.markdown("### Account")
        st.write(f"Signed in as **{username}**")
        if st.button("Log out"):
            _logout()
        st.divider()
        page = st.radio(
            "Go to",
            ["My profile", "My conferences"],
            label_visibility="collapsed",
        )

    st.title("Conference Scaffolding")
    st.caption(
        "Realistic, low-pressure support for undergrads exploring conferences — "
        "saved profile and one workspace per conference."
    )

    if page == "My profile":
        _render_profile(user_id)
    else:
        _render_conference_workspace(user_id)

    st.divider()
    st.caption(
        "Tip: copy `.env.example` to `.env` and add `OPENAI_API_KEY` for AI-generated "
        "questions and reflections. Data is stored locally in `data/app.db`."
    )


if __name__ == "__main__":
    main()
