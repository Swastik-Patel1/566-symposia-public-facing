import json
import os
import re
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from openai import OpenAI

_APP_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(_APP_ROOT / ".env")
load_dotenv()

_DEFAULT_QUESTIONS = {
    "q1": "What drew you to this topic, and what should a newcomer notice first?",
    "q2": "How could someone with my interests get involved or learn more?",
    "q3": "What’s one takeaway you hope people leave this session with?",
}


def _openai_client() -> OpenAI | None:
    key = os.environ.get("OPENAI_API_KEY")
    if not key:
        return None
    return OpenAI(api_key=key)


GEMINI_QUESTIONS_MODEL = "gemini-2.5-flash"


def _gemini_client():
    key = (os.environ.get("GEMINI_API_KEY") or "").strip()
    if not key:
        return None
    try:
        from google import genai  # type: ignore

        return genai.Client(api_key=key)
    except Exception:
        return None


def _extract_json_object(text: str) -> dict[str, Any]:
    text = text.strip()
    fence = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
    if fence:
        text = fence.group(1).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end > start:
            return json.loads(text[start : end + 1])
        raise


def _gemini_generate_text(prompt: str, temperature: float) -> str | None:
    client = _gemini_client()
    if not client:
        return None
    try:
        resp = client.models.generate_content(
            model=GEMINI_QUESTIONS_MODEL,
            contents=prompt,
            config={"temperature": temperature},
        )
        return (resp.text or "").strip()
    except Exception:
        return None


def _questions_dict_from_parsed(data: dict[str, Any]) -> dict[str, str]:
    return {
        "q1": str(data.get("q1", _DEFAULT_QUESTIONS["q1"])),
        "q2": str(data.get("q2", _DEFAULT_QUESTIONS["q2"])),
        "q3": str(data.get("q3", _DEFAULT_QUESTIONS["q3"])),
    }


def generate_questions(prompt: str) -> tuple[dict[str, str], str]:
    """
    Returns (questions dict, source_label for UI).
    Tries Gemini 2.5 Flash first, then OpenAI, then built-in defaults.
    """
    key = (os.environ.get("GEMINI_API_KEY") or "").strip()
    gemini_issue: str | None = None

    if key:
        gclient = _gemini_client()
        if not gclient:
            gemini_issue = (
                "GEMINI_API_KEY is set but the Gemini client could not be created "
                "(check `pip install google-genai` and that the key is valid)."
            )
        else:
            try:
                resp = gclient.models.generate_content(
                    model=GEMINI_QUESTIONS_MODEL,
                    contents=prompt,
                    config={"temperature": 0.7},
                )
                gem_txt = (resp.text or "").strip()
            except Exception as exc:
                gemini_issue = f"Gemini API error (`{GEMINI_QUESTIONS_MODEL}`): {exc!s}"
            else:
                if gem_txt:
                    try:
                        data = _extract_json_object(gem_txt)
                        return (
                            _questions_dict_from_parsed(data),
                            f"Google **{GEMINI_QUESTIONS_MODEL}** (Gemini API)",
                        )
                    except Exception as exc:
                        gemini_issue = (
                            f"Gemini returned text from **`{GEMINI_QUESTIONS_MODEL}`** but JSON parsing failed "
                            f"({type(exc).__name__})."
                        )
                else:
                    gemini_issue = f"Gemini returned empty text (`{GEMINI_QUESTIONS_MODEL}`)."

    oclient = _openai_client()
    if oclient:
        try:
            resp = oclient.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.7,
            )
            raw = (resp.choices[0].message.content or "").strip()
            data = _extract_json_object(raw)
            out = _questions_dict_from_parsed(data)
            if gemini_issue:
                return out, f"{gemini_issue} Used **OpenAI gpt-4o-mini** instead."
            return out, "OpenAI **gpt-4o-mini**."
        except Exception as exc:
            if gemini_issue:
                return dict(_DEFAULT_QUESTIONS), (
                    f"{gemini_issue} OpenAI also failed ({exc!s}). Using built-in placeholder questions."
                )
            return dict(_DEFAULT_QUESTIONS), f"OpenAI failed ({exc!s}). Using built-in placeholder questions."

    if not key:
        return dict(_DEFAULT_QUESTIONS), (
            "No **GEMINI_API_KEY** or **OPENAI_API_KEY** in `.env` (project root) — using built-in placeholder questions."
        )
    if gemini_issue:
        return dict(_DEFAULT_QUESTIONS), (
            f"{gemini_issue} No **OPENAI_API_KEY** fallback — using built-in placeholder questions."
        )
    return dict(_DEFAULT_QUESTIONS), "Using built-in placeholder questions."


def generate_reflection(prompt: str) -> str:
    gem_txt = _gemini_generate_text(prompt, 0.6)
    if gem_txt:
        return gem_txt

    client = _openai_client()
    if not client:
        return (
            "Set **GEMINI_API_KEY** (recommended) or **OPENAI_API_KEY** in `.env` "
            "to enable AI reflection."
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


def parse_business_card(
    image_bytes: bytes,
    mime_type: str,
) -> dict[str, str]:
    """
    Try to infer contact fields from a business-card photo.
    Returns keys: name, org, email, linkedin_url, topics.
    """
    client = _gemini_client()
    if not client:
        return {}
    prompt = (
        "Extract contact details from this business card image. "
        "Return ONLY JSON with keys: name, org, email, linkedin_url, topics. "
        "If unknown, use empty string."
    )
    try:
        resp = client.models.generate_content(
            model=GEMINI_QUESTIONS_MODEL,
            contents=[
                prompt,
                {"mime_type": mime_type, "data": image_bytes},
            ],
            config={"temperature": 0.1},
        )
        txt = (resp.text or "").strip()
        data = _extract_json_object(txt)
        return {
            "name": str(data.get("name", "")),
            "org": str(data.get("org", "")),
            "email": str(data.get("email", "")),
            "linkedin_url": str(data.get("linkedin_url", "")),
            "topics": str(data.get("topics", "")),
        }
    except Exception:
        return {}
