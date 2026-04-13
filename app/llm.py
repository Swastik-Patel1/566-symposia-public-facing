import json
import os
import re
from typing import Any

from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

_DEFAULT_QUESTIONS = {
    "q1": "What drew you to this topic, and what should a newcomer notice first?",
    "q2": "How could someone with my interests get involved or learn more?",
    "q3": "What’s one takeaway you hope people leave this session with?",
}


def _client() -> OpenAI | None:
    key = os.environ.get("OPENAI_API_KEY")
    if not key:
        return None
    return OpenAI(api_key=key)


def _extract_json_object(text: str) -> dict[str, Any]:
    text = text.strip()
    fence = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
    if fence:
        text = fence.group(1).strip()
    return json.loads(text)


def generate_questions(prompt: str) -> dict[str, str]:
    client = _client()
    if not client:
        return dict(_DEFAULT_QUESTIONS)

    try:
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.7,
        )
        raw = (resp.choices[0].message.content or "").strip()
        data = _extract_json_object(raw)
        out = {
            "q1": str(data.get("q1", _DEFAULT_QUESTIONS["q1"])),
            "q2": str(data.get("q2", _DEFAULT_QUESTIONS["q2"])),
            "q3": str(data.get("q3", _DEFAULT_QUESTIONS["q3"])),
        }
        return out
    except Exception:
        return dict(_DEFAULT_QUESTIONS)


def generate_reflection(prompt: str) -> str:
    client = _client()
    if not client:
        return (
            "Set **OPENAI_API_KEY** in a `.env` file (see `.env.example`) to enable "
            "AI reflection. Meanwhile, jot down: one person to follow up with, one idea "
            "you want to explore, and one question for tomorrow."
        )

    try:
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.6,
        )
        return (resp.choices[0].message.content or "").strip()
    except Exception as exc:
        return f"Could not generate reflection ({exc!r}). Check your API key and try again."
