"""SQLite persistence for second-brain threads and sessions.

Uses only the stdlib ``sqlite3`` module (no ORM, no external dependency). A new
connection is opened per operation: sqlite connections are cheap and FastAPI runs
sync endpoints across a threadpool, so per-operation connections sidestep
sqlite's single-thread affinity cleanly.

The active database file is ``data/sparse_model_theory.db`` by default and can be
redirected with the ``SMT_DB_PATH`` environment variable (used by tests to point
at a throwaway file). The schema is created lazily the first time a given path is
touched in this process, so callers never have to remember to run init_db().
"""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sqlite3
from typing import Iterator
import uuid


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB_PATH = ROOT / "data" / "sparse_model_theory.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS threads (
    id          TEXT PRIMARY KEY,
    name        TEXT NOT NULL,
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS sessions (
    id               TEXT PRIMARY KEY,
    thread_id        TEXT NOT NULL REFERENCES threads(id),
    created_at       TEXT NOT NULL,
    mode             TEXT NOT NULL,
    input_text       TEXT NOT NULL,
    daily_capture    TEXT,
    model_provider   TEXT NOT NULL,
    model_name       TEXT NOT NULL,
    thinking_mode    TEXT,
    latency_ms       REAL NOT NULL,
    raw_output_json  TEXT NOT NULL,
    summary          TEXT
);

CREATE INDEX IF NOT EXISTS idx_sessions_thread_created
    ON sessions(thread_id, created_at);

CREATE TABLE IF NOT EXISTS contact_requests (
    id                  TEXT PRIMARY KEY,
    name                TEXT,
    email               TEXT NOT NULL,
    phone               TEXT,
    context_type        TEXT,
    message             TEXT NOT NULL,
    source              TEXT NOT NULL,
    notification_status TEXT NOT NULL,
    notification_error  TEXT,
    created_at          TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_contact_requests_created
    ON contact_requests(created_at);

CREATE TABLE IF NOT EXISTS public_question_logs (
    id             TEXT PRIMARY KEY,
    question       TEXT NOT NULL,
    answer_status  TEXT NOT NULL,
    evidence_count INTEGER NOT NULL,
    source_page    TEXT NOT NULL,
    contact_email  TEXT,
    contact_phone  TEXT,
    created_at     TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_public_question_logs_created
    ON public_question_logs(created_at);

CREATE TABLE IF NOT EXISTS drafts (
    id                TEXT PRIMARY KEY,
    created_at        TEXT NOT NULL,
    title             TEXT NOT NULL,
    content           TEXT NOT NULL,
    editorial_score   INTEGER,
    status            TEXT NOT NULL,
    topic_source      TEXT
);

CREATE INDEX IF NOT EXISTS idx_drafts_status_created
    ON drafts(status, created_at);
"""

# Columns added after the original schema shipped, applied idempotently to any
# already-existing sessions table via non-destructive ALTER TABLE ADD COLUMN
# (never drops data). Keep in sync with the CREATE TABLE above.
_EXPECTED_SESSION_COLUMNS: dict[str, str] = {
    "summary": "TEXT",
}

_EXPECTED_CONTACT_REQUEST_COLUMNS: dict[str, str] = {
    "notification_error": "TEXT",
}

_initialized_paths: set[str] = set()

# Thread used when a session is captured without an explicit thread_id.
UNCATEGORIZED_THREAD_NAME = "Uncategorized"


def _db_path() -> Path:
    override = os.environ.get("SMT_DB_PATH")
    return Path(override) if override else DEFAULT_DB_PATH


def _now() -> str:
    # Microsecond precision so "most recent" ordering (list_sessions,
    # recent_summaries) is deterministic for rows written in the same second.
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


@contextmanager
def _connect() -> Iterator[sqlite3.Connection]:
    path = _db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    key = str(path)
    if key not in _initialized_paths:
        conn.executescript(SCHEMA)
        _ensure_session_columns(conn)
        _ensure_contact_request_columns(conn)
        conn.commit()
        _initialized_paths.add(key)
    try:
        with conn:  # commits on success, rolls back on exception
            yield conn
    finally:
        conn.close()


def _ensure_session_columns(conn: sqlite3.Connection) -> list[str]:
    """Additively bring an existing sessions table up to the current column set.

    Only ever runs ``ALTER TABLE ... ADD COLUMN`` for missing columns, which SQLite
    performs in-place without touching existing rows (they get NULL). Never drops or
    rewrites data. Returns the list of columns it added (empty if already current).
    """
    # PRAGMA table_info columns: (cid, name, type, ...). Index by position so this
    # works regardless of the connection's row_factory.
    existing = {row[1] for row in conn.execute("PRAGMA table_info(sessions)")}
    added: list[str] = []
    for column, decl in _EXPECTED_SESSION_COLUMNS.items():
        if column not in existing:
            conn.execute(f"ALTER TABLE sessions ADD COLUMN {column} {decl}")
            added.append(column)
    return added


def _ensure_contact_request_columns(conn: sqlite3.Connection) -> list[str]:
    existing = {row[1] for row in conn.execute("PRAGMA table_info(contact_requests)")}
    added: list[str] = []
    for column, decl in _EXPECTED_CONTACT_REQUEST_COLUMNS.items():
        if column not in existing:
            conn.execute(f"ALTER TABLE contact_requests ADD COLUMN {column} {decl}")
            added.append(column)
    return added


def init_db() -> None:
    """Ensure the schema exists for the active database path."""
    with _connect():
        pass


def add_contact_request(
    *,
    name: str | None,
    email: str,
    phone: str | None,
    context_type: str | None,
    message: str,
    source: str,
    notification_status: str = "pending",
    notification_error: str | None = None,
) -> dict[str, str | None]:
    request_id = str(uuid.uuid4())
    now = _now()
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO contact_requests (
                id, name, email, phone, context_type, message, source,
                notification_status, notification_error, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                request_id,
                name,
                email,
                phone,
                context_type,
                message,
                source,
                notification_status,
                notification_error,
                now,
            ),
        )
    return {
        "id": request_id,
        "name": name,
        "email": email,
        "phone": phone,
        "context_type": context_type,
        "message": message,
        "source": source,
        "notification_status": notification_status,
        "notification_error": notification_error,
        "created_at": now,
    }


def update_contact_notification_status(request_id: str, status: str, error: str | None = None) -> None:
    with _connect() as conn:
        conn.execute(
            "UPDATE contact_requests SET notification_status = ?, notification_error = ? WHERE id = ?",
            (status, error, request_id),
        )


def list_contact_requests(limit: int = 100) -> list[dict[str, object]]:
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT id, name, email, phone, context_type, message, source,
                   notification_status, notification_error, created_at
            FROM contact_requests
            ORDER BY created_at DESC, id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    return [dict(row) for row in rows]


def add_public_question_log(
    *,
    question: str,
    answer_status: str,
    evidence_count: int,
    source_page: str,
    contact_email: str | None,
    contact_phone: str | None,
) -> dict[str, str | int | None]:
    log_id = str(uuid.uuid4())
    now = _now()
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO public_question_logs (
                id, question, answer_status, evidence_count, source_page,
                contact_email, contact_phone, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                log_id,
                question,
                answer_status,
                evidence_count,
                source_page,
                contact_email,
                contact_phone,
                now,
            ),
        )
    return {
        "id": log_id,
        "question": question,
        "answer_status": answer_status,
        "evidence_count": evidence_count,
        "source_page": source_page,
        "contact_email": contact_email,
        "contact_phone": contact_phone,
        "created_at": now,
    }


def list_public_question_logs(limit: int = 100) -> list[dict[str, object]]:
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT id, question, answer_status, evidence_count, source_page,
                   contact_email, contact_phone, created_at
            FROM public_question_logs
            ORDER BY created_at DESC, id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    return [dict(row) for row in rows]


# ---------- Drafts (daily Akshar-generated content, gated by Telegram approval) ----------

def add_draft(
    *,
    title: str,
    content: str,
    editorial_score: int | None,
    status: str = "pending",
    topic_source: str | None = None,
) -> dict[str, object]:
    draft_id = str(uuid.uuid4())
    now = _now()
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO drafts (id, created_at, title, content, editorial_score, status, topic_source)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (draft_id, now, title, content, editorial_score, status, topic_source),
        )
    return {
        "id": draft_id,
        "created_at": now,
        "title": title,
        "content": content,
        "editorial_score": editorial_score,
        "status": status,
        "topic_source": topic_source,
    }


def get_draft(draft_id: str) -> dict[str, object] | None:
    with _connect() as conn:
        row = conn.execute("SELECT * FROM drafts WHERE id = ?", (draft_id,)).fetchone()
    return dict(row) if row else None


def update_draft_status(draft_id: str, status: str) -> bool:
    with _connect() as conn:
        cur = conn.execute("UPDATE drafts SET status = ? WHERE id = ?", (status, draft_id))
    return cur.rowcount > 0


def list_drafts_by_status(status: str, limit: int = 100) -> list[dict[str, object]]:
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT id, created_at, title, content, editorial_score, status, topic_source
            FROM drafts
            WHERE status = ?
            ORDER BY created_at DESC, id DESC
            LIMIT ?
            """,
            (status, limit),
        ).fetchall()
    return [dict(row) for row in rows]


def create_thread(name: str) -> dict[str, str]:
    thread_id = str(uuid.uuid4())
    now = _now()
    with _connect() as conn:
        conn.execute(
            "INSERT INTO threads (id, name, created_at, updated_at) VALUES (?, ?, ?, ?)",
            (thread_id, name, now, now),
        )
    return {"id": thread_id, "name": name, "created_at": now, "updated_at": now}


def get_or_create_uncategorized_thread() -> dict[str, str]:
    """Return the shared "Uncategorized" thread, creating it once if absent.

    Reuses the earliest-created thread with that name so repeated thread-less
    captures all land in the same bucket rather than spawning duplicates.
    """
    with _connect() as conn:
        row = conn.execute(
            "SELECT id, name, created_at, updated_at FROM threads "
            "WHERE name = ? ORDER BY created_at ASC, id ASC LIMIT 1",
            (UNCATEGORIZED_THREAD_NAME,),
        ).fetchone()
        if row is not None:
            return {
                "id": row["id"],
                "name": row["name"],
                "created_at": row["created_at"],
                "updated_at": row["updated_at"],
            }

        thread_id = str(uuid.uuid4())
        now = _now()
        conn.execute(
            "INSERT INTO threads (id, name, created_at, updated_at) VALUES (?, ?, ?, ?)",
            (thread_id, UNCATEGORIZED_THREAD_NAME, now, now),
        )
    return {
        "id": thread_id,
        "name": UNCATEGORIZED_THREAD_NAME,
        "created_at": now,
        "updated_at": now,
    }


def thread_exists(thread_id: str) -> bool:
    with _connect() as conn:
        row = conn.execute(
            "SELECT 1 FROM threads WHERE id = ?", (thread_id,)
        ).fetchone()
    return row is not None


def _thread_row_to_dict(row: sqlite3.Row) -> dict[str, object]:
    return {
        "id": row["id"],
        "name": row["name"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "session_count": row["session_count"],
    }


def get_thread(thread_id: str) -> dict[str, object] | None:
    with _connect() as conn:
        row = conn.execute(
            """
            SELECT t.id, t.name, t.created_at, t.updated_at,
                   (SELECT COUNT(*) FROM sessions s WHERE s.thread_id = t.id) AS session_count
            FROM threads t
            WHERE t.id = ?
            """,
            (thread_id,),
        ).fetchone()
    return _thread_row_to_dict(row) if row else None


def list_threads() -> list[dict[str, object]]:
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT t.id, t.name, t.created_at, t.updated_at,
                   (SELECT COUNT(*) FROM sessions s WHERE s.thread_id = t.id) AS session_count
            FROM threads t
            ORDER BY t.updated_at DESC, t.created_at DESC
            """
        ).fetchall()
    return [_thread_row_to_dict(row) for row in rows]


def add_session(
    *,
    thread_id: str,
    mode: str,
    input_text: str,
    daily_capture: str | None,
    model_provider: str,
    model_name: str,
    thinking_mode: str | None,
    latency_ms: float,
    raw_output: object,
    summary: str | None = None,
) -> dict[str, str]:
    """Insert a session record and bump its thread's updated_at, atomically."""
    session_id = str(uuid.uuid4())
    now = _now()
    raw_output_json = json.dumps(raw_output, ensure_ascii=False)
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO sessions (
                id, thread_id, created_at, mode, input_text, daily_capture,
                model_provider, model_name, thinking_mode, latency_ms, raw_output_json,
                summary
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                session_id,
                thread_id,
                now,
                mode,
                input_text,
                daily_capture,
                model_provider,
                model_name,
                thinking_mode,
                latency_ms,
                raw_output_json,
                summary,
            ),
        )
        conn.execute(
            "UPDATE threads SET updated_at = ? WHERE id = ?", (now, thread_id)
        )
    return {"id": session_id, "thread_id": thread_id, "created_at": now}


def move_session(session_id: str, thread_id: str) -> dict[str, str] | None:
    """Re-thread an existing session. Returns None if the session doesn't exist.

    The caller is responsible for confirming the target thread exists (the FK
    would also reject a bad target). The destination thread's updated_at is
    bumped so it surfaces as recently touched.
    """
    now = _now()
    with _connect() as conn:
        cursor = conn.execute(
            "UPDATE sessions SET thread_id = ? WHERE id = ?", (thread_id, session_id)
        )
        if cursor.rowcount == 0:
            return None
        conn.execute(
            "UPDATE threads SET updated_at = ? WHERE id = ?", (now, thread_id)
        )
    return {"id": session_id, "thread_id": thread_id}


def list_sessions(thread_id: str, truncate: int = 100) -> list[dict[str, object]]:
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT id, created_at, mode, input_text, latency_ms
            FROM sessions
            WHERE thread_id = ?
            ORDER BY created_at DESC, id DESC
            """,
            (thread_id,),
        ).fetchall()

    sessions: list[dict[str, object]] = []
    for row in rows:
        text = row["input_text"]
        if truncate and len(text) > truncate:
            text = text[:truncate].rstrip() + "..."
        sessions.append(
            {
                "id": row["id"],
                "created_at": row["created_at"],
                "mode": row["mode"],
                "input_text": text,
                "latency_ms": row["latency_ms"],
            }
        )
    return sessions


def get_session(session_id: str) -> dict[str, object] | None:
    with _connect() as conn:
        row = conn.execute(
            "SELECT * FROM sessions WHERE id = ?", (session_id,)
        ).fetchone()
    if row is None:
        return None

    record = dict(row)
    # Return the stored blob parsed back into a real object, not a JSON string.
    record["raw_output"] = json.loads(record.pop("raw_output_json"))
    return record


def recent_summaries(thread_id: str, limit: int = 2) -> list[str]:
    """Most-recent stored session summaries for a thread (newest first).

    Returns only non-empty summaries and never the raw_output_json — this is the
    cheap, compressed source used for opt-in thread-context injection.
    """
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT summary FROM sessions
            WHERE thread_id = ? AND summary IS NOT NULL AND TRIM(summary) != ''
            ORDER BY created_at DESC, id DESC
            LIMIT ?
            """,
            (thread_id, limit),
        ).fetchall()
    return [row["summary"] for row in rows]


def find_thread_by_name(name: str) -> dict[str, str] | None:
    """Case-insensitive exact thread lookup (trimmed). Returns earliest match."""
    target = name.strip().lower()
    with _connect() as conn:
        row = conn.execute(
            "SELECT id, name, created_at, updated_at FROM threads "
            "WHERE LOWER(TRIM(name)) = ? ORDER BY created_at ASC, id ASC LIMIT 1",
            (target,),
        ).fetchone()
    return dict(row) if row else None


def all_thread_names() -> list[str]:
    with _connect() as conn:
        rows = conn.execute("SELECT name FROM threads ORDER BY name ASC").fetchall()
    return [row["name"] for row in rows]
