"""Export helpers: ICS calendar, CSV, Markdown reports."""

from __future__ import annotations

import csv
import io
import re
import uuid
from datetime import date, datetime
from typing import Any


def _ics_escape(s: str) -> str:
    return (
        s.replace("\\", "\\\\")
        .replace("\n", "\\n")
        .replace(",", "\\,")
        .replace(";", "\\;")
    )


def _parse_iso_date(s: str) -> date | None:
    s = (s or "").strip()
    if not s:
        return None
    try:
        return date.fromisoformat(s[:10])
    except ValueError:
        return None


def _time_parts_from_line(line: str) -> tuple[int, int] | None:
    """Try to extract HH, MM from strings like '10:30 AM' or '14:00'."""
    line = line.strip()
    m = re.search(
        r"\b(\d{1,2}):(\d{2})\s*(AM|PM)?\b",
        line,
        re.I,
    )
    if not m:
        return None
    h, mi, ap = int(m.group(1)), int(m.group(2)), m.group(3)
    if ap:
        ap = ap.upper()
        if ap == "PM" and h != 12:
            h += 12
        if ap == "AM" and h == 12:
            h = 0
    return h, mi


def build_conference_ics(
    conference_name: str,
    event_date_str: str,
    sessions: list[dict[str, Any]],
) -> str:
    """
    Build a minimal iCalendar (.ics) file for one conference day.
    Sessions without a parseable time become all-day style blocks using noon.
    """
    d = _parse_iso_date(event_date_str)
    if not d:
        d = date.today()

    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//Conference Scaffolding//EN",
        "CALSCALE:GREGORIAN",
    ]

    for sess in sessions:
        title = str(sess.get("title") or "Session")
        time_line = str(sess.get("time") or "")
        desc = str(sess.get("description") or "")[:2000]
        speaker = str(sess.get("speaker") or "")

        uid = f"{uuid.uuid4()}@conference-scaffolding"
        tp = _time_parts_from_line(time_line)
        if tp:
            h, mi = tp
            start = datetime(d.year, d.month, d.day, h, mi, 0)
            end = datetime(d.year, d.month, d.day, min(h + 1, 23), mi, 0)
            dtstart = start.strftime("%Y%m%dT%H%M%S")
            dtend = end.strftime("%Y%m%dT%H%M%S")
            lines.extend(
                [
                    "BEGIN:VEVENT",
                    f"UID:{uid}",
                    f"DTSTAMP:{datetime.utcnow().strftime('%Y%m%dT%H%M%SZ')}",
                    f"DTSTART:{dtstart}",
                    f"DTEND:{dtend}",
                    f"SUMMARY:{_ics_escape(conference_name + ': ' + title)}",
                ]
            )
        else:
            ds = d.strftime("%Y%m%d")
            lines.extend(
                [
                    "BEGIN:VEVENT",
                    f"UID:{uid}",
                    f"DTSTAMP:{datetime.utcnow().strftime('%Y%m%dT%H%M%SZ')}",
                    f"DTSTART;VALUE=DATE:{ds}",
                    f"DTEND;VALUE=DATE:{ds}",
                    f"SUMMARY:{_ics_escape(conference_name + ': ' + title)}",
                ]
            )
        body_bits = []
        if speaker and speaker != "TBD":
            body_bits.append(f"Speaker: {speaker}")
        if time_line:
            body_bits.append(f"Time (from program): {time_line}")
        if desc:
            body_bits.append(desc)
        if body_bits:
            lines.append(f"DESCRIPTION:{_ics_escape(chr(10).join(body_bits))}")
        lines.append("END:VEVENT")

    lines.append("END:VCALENDAR")
    return "\r\n".join(lines) + "\r\n"


def contacts_to_csv(contacts: list[dict[str, Any]]) -> str:
    buf = io.StringIO()
    fieldnames = [
        "id",
        "conference_id",
        "name",
        "org",
        "email",
        "linkedin_url",
        "topics",
        "notes",
        "created_at",
    ]
    w = csv.DictWriter(buf, fieldnames=fieldnames, extrasaction="ignore")
    w.writeheader()
    for row in contacts:
        w.writerow({k: row.get(k, "") for k in fieldnames})
    return buf.getvalue()


def build_reflection_report_md(
    username: str,
    conference_name: str,
    event_date: str,
    day_notes: str,
    contacts_blob: str,
    tomorrow: str,
    ai_text: str,
) -> str:
    return "\n".join(
        [
            f"# Reflection — {conference_name}",
            "",
            f"- **Account:** {username}",
            f"- **Conference date:** {event_date or '—'}",
            "",
            "## Today",
            day_notes or "—",
            "",
            "## People & conversations",
            contacts_blob or "—",
            "",
            "## Tomorrow",
            tomorrow or "—",
            "",
            "## AI synthesis",
            ai_text or "—",
            "",
        ]
    )
