import io
import re
from typing import Any

from pypdf import PdfReader


def extract_text_from_pdf_bytes(data: bytes) -> str:
    reader = PdfReader(io.BytesIO(data))
    return "\n".join((page.extract_text() or "") for page in reader.pages)


def naive_session_parse(text: str) -> list[dict[str, Any]]:
    """Heuristic parser for schedule-like PDF text. Replace with LLM extraction later."""
    sessions: list[dict[str, Any]] = []
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    time_re = re.compile(r"\b\d{1,2}:\d{2}\s?(AM|PM)\b", re.I)
    for i, line in enumerate(lines):
        if time_re.search(line):
            title = lines[i + 1] if i + 1 < len(lines) else "Untitled session"
            desc = lines[i + 2] if i + 2 < len(lines) else ""
            sessions.append(
                {
                    "time": line,
                    "title": title,
                    "speaker": "TBD",
                    "description": desc[:500] if desc else "",
                }
            )
    return sessions
