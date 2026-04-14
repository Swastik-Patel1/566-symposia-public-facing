# Symposia (Conference Scaffolding)

Streamlit web app for undergraduate conference attendees: one local account, multiple conferences, contacts, and lightweight AI-assisted prep. Data stays on the machine that runs the app unless you export it.

## What it does today

- **Authentication:** Sign up (account + optional profile step) and log in. Passwords are hashed (PBKDF2) in a local **SQLite** database (`data/app.db`, gitignored).
- **Your profile:** Interests, LinkedIn URL, optional **resume** (PDF or TXT — text is extracted and **up to 12,000 characters** are kept for the app, not the raw file), optional **profile photo** (stored as base64; **500 KB** max per image). Use **Save profile** so edits persist when you change pages.
- **Conferences:** Create many conferences; pick an **active** one from the **Active conference** dropdown on the Conferences page. Each has:
  - **Conference start date** and **conference end date** (for one-day events, set both to the same day). Used for labels, sorting, and exports.
  - **Prep & schedule:** Name, goals, how you feel, optional **schedule PDF** upload with **heuristic** session parsing (quality varies by PDF), an editable **session table** (add rows, edit, save).
  - **Session coach:** Enter or quick-fill a session, then generate **three discussion questions** using your saved profile and this conference’s goals/feelings. Uses **`GEMINI_API_KEY` first** if set in `.env`, otherwise **`OPENAI_API_KEY`**, otherwise **built-in fallback** text (no API required).
  - **End of day:** Reflection fields, optional **AI synthesis** of the day (same API priority as questions), save to the conference. Download **reflection markdown** and a **full conference package JSON** (conference row + contacts for that conference + question history metadata the app attaches).
- **Contacts:** Add people with optional conference link, notes, optional **business card image** (same **500 KB** image rule as profile photos). List view with **edit** and delete. Optional **AI parse of a business card image** where implemented in the add flow.
- **Calendar & exports:** Per-conference **`.ics`** download from the **saved** schedule (events are anchored on the **conference start date**; multi-day ranges are for display and metadata, not per-day session placement). **Contacts CSV** (all contacts or per conference where applicable).
- **Privacy:** Short data-handling notes, **export all account-related data as JSON**, and **delete account** (removes user, conferences, contacts in this database).

This is a **course / demo–grade** local prototype: no hosted multi-user backend, no HTTPS or production hardening. Do not point it at the public internet without a proper security review.

## Setup

```bash
cd conference-scaffolding
python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
# Optional: set GEMINI_API_KEY (recommended) and/or OPENAI_API_KEY for AI questions and reflections.
```

## Run

```bash
streamlit run main.py
```

Without API keys, session questions and reflections still run using non-model fallback copy where the code provides it; the UI notes how to enable Gemini or OpenAI.
