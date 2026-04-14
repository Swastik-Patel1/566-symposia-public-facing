"""SQLite persistence for users and conferences."""

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
        # Stores a full data URL (data:image/...;base64,...) for <img src="...">
        c.execute("ALTER TABLE users ADD COLUMN profile_image_b64 TEXT DEFAULT ''")


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
                created_at TEXT DEFAULT (datetime('now')),
                updated_at TEXT DEFAULT (datetime('now'))
            )
            """
        )
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
            "SELECT * FROM conferences WHERE user_id = ? ORDER BY updated_at DESC, id DESC",
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


def create_conference(user_id: int, name: str) -> int:
    with _conn() as c:
        cur = c.execute(
            """
            INSERT INTO conferences (user_id, name, goals, feelings, sessions_json)
            VALUES (?, ?, '', 'A little nervous', '[]')
            """,
            (user_id, name.strip() or "Untitled conference"),
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
