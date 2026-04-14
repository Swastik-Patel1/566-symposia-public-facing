"""SQLite persistence for users, conferences, and contacts."""

import json
import sqlite3
from pathlib import Path
from typing import Any

_DB_PATH = Path(__file__).resolve().parent.parent / "data" / "app.db"


def _conn() -> sqlite3.Connection:
    _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(_DB_PATH)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA foreign_keys = ON")
    return c


def _ensure_user_columns(c: sqlite3.Connection) -> None:
    cur = c.execute("PRAGMA table_info(users)")
    names = {row[1] for row in cur.fetchall()}
    if "profile_image_b64" not in names:
        c.execute(
            "ALTER TABLE users ADD COLUMN profile_image_b64 TEXT DEFAULT ''"
        )


def _ensure_conference_columns(c: sqlite3.Connection) -> None:
    cur = c.execute("PRAGMA table_info(conferences)")
    names = {row[1] for row in cur.fetchall()}
    if "event_date" not in names:
        c.execute("ALTER TABLE conferences ADD COLUMN event_date TEXT DEFAULT ''")
    for col in (
        "reflection_day_notes",
        "reflection_contacts",
        "reflection_tomorrow",
        "reflection_ai",
    ):
        if col not in names:
            c.execute(f"ALTER TABLE conferences ADD COLUMN {col} TEXT DEFAULT ''")


def _ensure_contacts_table(c: sqlite3.Connection) -> None:
    c.execute(
        """
        CREATE TABLE IF NOT EXISTS contacts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            conference_id INTEGER REFERENCES conferences(id) ON DELETE SET NULL,
            name TEXT NOT NULL DEFAULT '',
            org TEXT DEFAULT '',
            email TEXT DEFAULT '',
            linkedin_url TEXT DEFAULT '',
            topics TEXT DEFAULT '',
            notes TEXT DEFAULT '',
            business_card_b64 TEXT DEFAULT '',
            created_at TEXT DEFAULT (datetime('now'))
        )
        """
    )


def init_db() -> None:
    with _conn() as c:
        c.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                interests TEXT DEFAULT '',
                linkedin TEXT DEFAULT '',
                resume_text TEXT DEFAULT '',
                profile_image_b64 TEXT DEFAULT '',
                created_at TEXT DEFAULT (datetime('now'))
            )
            """
        )
        _ensure_user_columns(c)
        c.execute(
            """
            CREATE TABLE IF NOT EXISTS conferences (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                name TEXT NOT NULL DEFAULT '',
                goals TEXT DEFAULT '',
                feelings TEXT DEFAULT 'A little nervous',
                sessions_json TEXT DEFAULT '[]',
                event_date TEXT DEFAULT '',
                reflection_day_notes TEXT DEFAULT '',
                reflection_contacts TEXT DEFAULT '',
                reflection_tomorrow TEXT DEFAULT '',
                reflection_ai TEXT DEFAULT '',
                created_at TEXT DEFAULT (datetime('now')),
                updated_at TEXT DEFAULT (datetime('now'))
            )
            """
        )
        _ensure_conference_columns(c)
        _ensure_contacts_table(c)
        c.commit()


def create_user(username: str, password_hash: str) -> int:
    with _conn() as c:
        cur = c.execute(
            "INSERT INTO users (username, password_hash) VALUES (?, ?)",
            (username.strip().lower(), password_hash),
        )
        c.commit()
        return int(cur.lastrowid)


def get_user_by_username(username: str) -> sqlite3.Row | None:
    with _conn() as c:
        cur = c.execute(
            "SELECT * FROM users WHERE username = ?",
            (username.strip().lower(),),
        )
        return cur.fetchone()


def get_user_by_id(user_id: int) -> sqlite3.Row | None:
    with _conn() as c:
        cur = c.execute("SELECT * FROM users WHERE id = ?", (user_id,))
        return cur.fetchone()


def delete_user(user_id: int) -> None:
    with _conn() as c:
        c.execute("DELETE FROM users WHERE id = ?", (user_id,))
        c.commit()


def update_user_profile(
    user_id: int,
    interests: str,
    linkedin: str,
    resume_text: str,
    profile_image_b64: str = "",
) -> None:
    with _conn() as c:
        c.execute(
            """
            UPDATE users SET interests = ?, linkedin = ?, resume_text = ?,
            profile_image_b64 = ?
            WHERE id = ?
            """,
            (interests, linkedin, resume_text, profile_image_b64, user_id),
        )
        c.commit()


def list_conferences(user_id: int) -> list[sqlite3.Row]:
    with _conn() as c:
        cur = c.execute(
            """
            SELECT * FROM conferences WHERE user_id = ?
            ORDER BY COALESCE(NULLIF(event_date, ''), '9999-12-31') ASC,
                     updated_at DESC, id DESC
            """,
            (user_id,),
        )
        return list(cur.fetchall())


def get_conference(conf_id: int, user_id: int) -> sqlite3.Row | None:
    with _conn() as c:
        cur = c.execute(
            "SELECT * FROM conferences WHERE id = ? AND user_id = ?",
            (conf_id, user_id),
        )
        return cur.fetchone()


def create_conference(user_id: int, name: str, event_date: str = "") -> int:
    with _conn() as c:
        cur = c.execute(
            """
            INSERT INTO conferences (user_id, name, goals, feelings, sessions_json, event_date)
            VALUES (?, ?, '', 'A little nervous', '[]', ?)
            """,
            (user_id, name.strip() or "Untitled conference", event_date.strip()),
        )
        c.commit()
        return int(cur.lastrowid)


def update_conference(
    conf_id: int,
    user_id: int,
    *,
    name: str | None = None,
    goals: str | None = None,
    feelings: str | None = None,
    sessions: list[dict[str, Any]] | None = None,
    event_date: str | None = None,
    reflection_day_notes: str | None = None,
    reflection_contacts: str | None = None,
    reflection_tomorrow: str | None = None,
    reflection_ai: str | None = None,
) -> None:
    parts: list[str] = []
    vals: list[Any] = []
    if name is not None:
        parts.append("name = ?")
        vals.append(name)
    if goals is not None:
        parts.append("goals = ?")
        vals.append(goals)
    if feelings is not None:
        parts.append("feelings = ?")
        vals.append(feelings)
    if sessions is not None:
        parts.append("sessions_json = ?")
        vals.append(json.dumps(sessions))
    if event_date is not None:
        parts.append("event_date = ?")
        vals.append(event_date)
    if reflection_day_notes is not None:
        parts.append("reflection_day_notes = ?")
        vals.append(reflection_day_notes)
    if reflection_contacts is not None:
        parts.append("reflection_contacts = ?")
        vals.append(reflection_contacts)
    if reflection_tomorrow is not None:
        parts.append("reflection_tomorrow = ?")
        vals.append(reflection_tomorrow)
    if reflection_ai is not None:
        parts.append("reflection_ai = ?")
        vals.append(reflection_ai)
    if not parts:
        return
    parts.append("updated_at = datetime('now')")
    vals.extend([conf_id, user_id])
    sql = f"UPDATE conferences SET {', '.join(parts)} WHERE id = ? AND user_id = ?"
    with _conn() as c:
        c.execute(sql, vals)
        c.commit()


def delete_conference(conf_id: int, user_id: int) -> None:
    with _conn() as c:
        c.execute(
            "DELETE FROM conferences WHERE id = ? AND user_id = ?",
            (conf_id, user_id),
        )
        c.commit()


# --- Contacts ---


def list_contacts(user_id: int) -> list[sqlite3.Row]:
    with _conn() as c:
        cur = c.execute(
            "SELECT * FROM contacts WHERE user_id = ? ORDER BY created_at DESC",
            (user_id,),
        )
        return list(cur.fetchall())


def list_contacts_for_conference(user_id: int, conference_id: int) -> list[sqlite3.Row]:
    with _conn() as c:
        cur = c.execute(
            """
            SELECT * FROM contacts
            WHERE user_id = ? AND conference_id = ?
            ORDER BY created_at DESC
            """,
            (user_id, conference_id),
        )
        return list(cur.fetchall())


def add_contact(
    user_id: int,
    conference_id: int | None,
    name: str,
    org: str = "",
    email: str = "",
    linkedin_url: str = "",
    topics: str = "",
    notes: str = "",
    business_card_b64: str = "",
) -> int:
    with _conn() as c:
        cur = c.execute(
            """
            INSERT INTO contacts (
                user_id, conference_id, name, org, email, linkedin_url,
                topics, notes, business_card_b64
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                user_id,
                conference_id,
                name.strip(),
                org,
                email,
                linkedin_url,
                topics,
                notes,
                business_card_b64,
            ),
        )
        c.commit()
        return int(cur.lastrowid)


def delete_contact(contact_id: int, user_id: int) -> None:
    with _conn() as c:
        c.execute(
            "DELETE FROM contacts WHERE id = ? AND user_id = ?",
            (contact_id, user_id),
        )
        c.commit()


def row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    """Convert a sqlite3.Row to a plain dict (all columns)."""
    return {k: row[k] for k in row.keys()}


def _row_as_dict(row: sqlite3.Row) -> dict[str, Any]:
    return row_to_dict(row)


def export_user_data(user_id: int) -> dict[str, Any]:
    """Structured export for GDPR-style portability (local demo)."""
    u = get_user_by_id(user_id)
    if not u:
        return {}
    user_d = _row_as_dict(u)
    user_d.pop("password_hash", None)
    confs = [_row_as_dict(r) for r in list_conferences(user_id)]
    contacts = [_row_as_dict(r) for r in list_contacts(user_id)]
    return {
        "user": user_d,
        "conferences": confs,
        "contacts": contacts,
        "export_note": "Local SQLite export; remove sensitive fields before sharing publicly.",
    }
