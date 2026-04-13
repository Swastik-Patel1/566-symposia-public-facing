"""Conference Scaffolding — Streamlit prototype."""

import streamlit as st

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


def _ensure_defaults():
    if "resume_text" not in st.session_state:
        st.session_state.resume_text = ""
    if "sessions" not in st.session_state:
        st.session_state.sessions = []


def main():
    st.set_page_config(page_title="Conference Scaffolding", layout="wide")
    _ensure_defaults()

    st.title("Conference Scaffolding")
    st.caption(
        "Realistic, low-pressure support for undergrads exploring conferences — "
        "goals, questions, and reflection."
    )

    tab_before, tab_during, tab_after = st.tabs(["Before", "During", "After"])

    with tab_before:
        st.header("Set your profile")
        col1, col2 = st.columns(2)
        with col1:
            st.text_area(
                "Interests",
                placeholder="e.g. climate policy, HCI, first-gen student support",
                height=100,
                key="interests",
            )
            st.text_area(
                "Conference goals",
                placeholder="e.g. meet 2 people in sustainability, attend one poster session",
                height=100,
                key="goals",
            )
        with col2:
            st.text_input(
                "LinkedIn profile URL (optional)",
                key="linkedin",
            )
            st.selectbox(
                "How are you feeling?",
                ["Calm", "A little nervous", "Very anxious"],
                key="anxiety",
            )

        resume_file = st.file_uploader(
            "Resume (PDF or TXT) — optional, improves question relevance",
            type=["pdf", "txt"],
        )
        if resume_file is not None:
            st.session_state.resume_text = _resume_text_from_upload(resume_file)
            st.success(f"Loaded resume text ({len(st.session_state.resume_text)} chars).")

        st.subheader("Schedule (PDF)")
        schedule_pdf = st.file_uploader(
            "Upload a conference schedule PDF",
            type=["pdf"],
        )
        if schedule_pdf is not None:
            raw = extract_text_from_pdf_bytes(schedule_pdf.read())
            st.session_state.sessions = naive_session_parse(raw)
            st.success(f"Parsed {len(st.session_state.sessions)} session blocks (heuristic).")
            if st.session_state.sessions:
                st.dataframe(st.session_state.sessions[:50], use_container_width=True)

    with tab_during:
        st.header("Session coach")
        st.write(
            "Before a session starts, generate three short questions that connect "
            "the topic to your interests."
        )

        c1, c2 = st.columns(2)
        with c1:
            st.text_input("Session title", key="sess_title")
            st.text_input("Speaker", key="sess_speaker")
        with c2:
            pass

        st.text_area(
            "Session description (paste from program or website)",
            key="sess_desc",
            height=140,
        )

        resume_preview = (
            st.session_state.resume_text
            or "(no resume uploaded — questions still work)"
        )
        if st.button("Generate three questions", type="primary"):
            prompt = QUESTION_PROMPT.format(
                interests=st.session_state.get("interests") or "(not specified)",
                goals=st.session_state.get("goals") or "(not specified)",
                resume_text=resume_preview,
                anxiety_note=st.session_state.get("anxiety", "A little nervous"),
                title=st.session_state.get("sess_title") or "(untitled)",
                speaker=st.session_state.get("sess_speaker") or "(unknown)",
                description=st.session_state.get("sess_desc") or "(no description)",
            )
            qs = generate_questions(prompt)
            st.markdown("**You could ask:**")
            st.markdown(f"- {qs['q1']}")
            st.markdown(f"- {qs['q2']}")
            st.markdown(f"- {qs['q3']}")

        if st.session_state.sessions:
            st.subheader("Quick pick from parsed schedule")
            labels = [
                f"{s.get('time', '')} — {s.get('title', '')}"
                for s in st.session_state.sessions
            ]
            pick = st.selectbox(
                "Session",
                range(len(labels)),
                format_func=lambda i: labels[i],
                key="session_pick",
            )
            if st.button("Fill fields from selection"):
                s = st.session_state.sessions[pick]
                st.session_state.sess_title = s.get("title", "")
                st.session_state.sess_speaker = s.get("speaker", "")
                st.session_state.sess_desc = s.get("description", "")
                st.rerun()

    with tab_after:
        st.header("End-of-day reflection")
        st.text_area(
            "What happened today? (sessions, feelings, sparks of interest)",
            height=120,
            key="day_notes",
        )
        st.text_area(
            "Who did you meet? (names, orgs, topics)",
            height=100,
            key="day_contacts",
        )
        st.text_area(
            "Tomorrow’s sessions or goals",
            height=80,
            key="day_tomorrow",
        )

        if st.button("Synthesize my day", type="primary"):
            prompt = REFLECTION_PROMPT.format(
                notes=st.session_state.get("day_notes") or "(nothing yet)",
                contacts=st.session_state.get("day_contacts") or "(none noted)",
                tomorrow_sessions=st.session_state.get("day_tomorrow") or "(not specified)",
            )
            result = generate_reflection(prompt)
            st.markdown(result)

    st.divider()
    st.caption(
        "Tip: copy `.env.example` to `.env` and add `OPENAI_API_KEY` for AI-generated "
        "questions and reflections. Without a key, questions use built-in fallbacks."
    )


if __name__ == "__main__":
    main()
