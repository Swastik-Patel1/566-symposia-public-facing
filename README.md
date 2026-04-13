# Conference Scaffolding

A small web prototype for realistic, low-pressure support so undergraduate researchers can learn and network at conferences. The intent is to feel natural, not forced.

## What it does (MVP)

- **Before:** Profile (interests, goals, LinkedIn, how you feel), optional resume upload, PDF schedule upload with heuristic session parsing.
- **During:** Generate three short, personalized questions per session (uses your profile + session details).
- **After:** End-of-day reflection with summary and follow-up ideas (markdown).

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
