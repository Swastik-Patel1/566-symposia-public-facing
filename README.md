# Conference Scaffolding

A small web prototype for realistic, low-pressure support so undergraduate researchers can learn and network at conferences. The intent is to feel natural, not forced.

## What it does (MVP)

- **Sign up / Log in:** Username and password; passwords are hashed (PBKDF2) and stored in a local SQLite database.
- **My profile:** Interests, LinkedIn URL, and resume (PDF or TXT). Click **Save profile** to persist; these load automatically on future visits.
- **My conferences:** Add as many conferences as you like. Pick the active conference from the dropdown. Each conference has:
  - **Prep & schedule:** Name, goals, how you feel, schedule PDF upload (heuristic parsing), save.
  - **Session coach:** Three personalized questions per session (uses saved profile + this conference’s goals/feelings).
  - **End of day:** Reflection and AI synthesis (if `OPENAI_API_KEY` is set).

Data is stored locally in `data/app.db` (gitignored). This is suitable for local development; for a public deployment you would add HTTPS, stronger auth, and a hosted database.

## Setup

```bash
cd conference-scaffolding
python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
# Edit .env and set OPENAI_API_KEY for AI-generated questions and reflections.
```

## Run

```bash
streamlit run main.py
```

Without `OPENAI_API_KEY`, session questions use built-in fallbacks; the reflection tab explains how to enable the API.
