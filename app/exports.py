"""Export helpers: calendar, CSV, markdown and conference package."""

from __future__ import annotations

import csv
import io
import json
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


def parse_event_date(s: str) -> date | None:
    s = (s or "").strip()
    if not s:
        return None
    for fmt in ("%Y-%m-%d", "%m-%d-%Y"):
        try:
            return datetime.strptime(s[:10], fmt).date()
        except ValueError:
            continue
    return None


def _time_parts_from_line(line: str) -> tuple[int, int] | None:
    m = re.search(r"\b(\d{1,2}):(\d{2})\s*(AM|PM)?\b", line.strip(), re.I)
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
    d = parse_event_date(event_date_str) or date.today()
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//Symposia//EN",
        "CALSCALE:GREGORIAN",
    ]
    for sess in sessions:
        title = str(sess.get("title") or "Session")
        time_line = str(sess.get("time") or "")
        desc = str(sess.get("description") or "")[:2000]
        speaker = str(sess.get("speaker") or "")
        uid = f"{uuid.uuid4()}@symposia"
        tp = _time_parts_from_line(time_line)
        if tp:
            h, mi = tp
            start = datetime(d.year, d.month, d.day, h, mi, 0)
            end = datetime(d.year, d.month, d.day, min(h + 1, 23), mi, 0)
            lines.extend(
                [
                    "BEGIN:VEVENT",
                    f"UID:{uid}",
                    f"DTSTAMP:{datetime.utcnow().strftime('%Y%m%dT%H%M%SZ')}",
                    f"DTSTART:{start.strftime('%Y%m%dT%H%M%S')}",
                    f"DTEND:{end.strftime('%Y%m%dT%H%M%S')}",
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
        bits = []
        if speaker and speaker != "TBD":
            bits.append(f"Speaker: {speaker}")
        if time_line:
            bits.append(f"Time: {time_line}")
        if desc:
            bits.append(desc)
        if bits:
            lines.append(f"DESCRIPTION:{_ics_escape(chr(10).join(bits))}")
        lines.append("END:VEVENT")
    lines.append("END:VCALENDAR")
    return "\r\n".join(lines) + "\r\n"


def contacts_to_csv(
    contacts: list[dict[str, Any]],
    conference_names: dict[int, str] | None = None,
) -> str:
    conference_names = conference_names or {}
    buf = io.StringIO()
    fieldnames = [
        "id",
        "conference_name",
        "name",
        "org",
        "email",
        "linkedin_url",
        "topics",
        "notes",
        "created_at",
    ]
    writer = csv.DictWriter(buf, fieldnames=fieldnames, extrasaction="ignore")
    writer.writeheader()
    for row in contacts:
        cid = row.get("conference_id")
        if cid is not None and str(cid).isdigit():
            cname = conference_names.get(int(cid), f"Conference {cid}")
        else:
            cname = ""
        out = dict(row)
        out["conference_name"] = cname
        writer.writerow({k: out.get(k, "") for k in fieldnames})
    return buf.getvalue()


def build_reflection_report_md(
    username: str,
    conference_name: str,
    event_date: str,
    day_notes: str,
    contacts_blob: str,
    tomorrow: str,
    ai_text: str,
    event_end_date: str = "",
) -> str:
    start = (event_date or "").strip()
    end = (event_end_date or "").strip()
    if not start:
        dates_line = "—"
    elif not end or end == start:
        dates_line = start
    else:
        dates_line = f"{start} – {end}"
    return "\n".join(
        [
            f"# Reflection — {conference_name}",
            "",
            f"- **Account:** {username}",
            f"- **Conference dates:** {dates_line}",
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


def build_conference_package_json(
    conference: dict[str, Any],
    contacts: list[dict[str, Any]],
) -> str:
    payload = {
        "conference": conference,
        "contacts": contacts,
        "generated_at": datetime.utcnow().isoformat() + "Z",
    }
    return json.dumps(payload, indent=2, default=str)
