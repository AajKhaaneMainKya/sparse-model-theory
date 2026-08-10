"""One-time migration: add the sessions.summary column.

Safe, additive, and idempotent:
  1. Resolves the active DB path from SMT_DB_PATH (falling back to the local
     data/sparse_model_theory.db). This is the SAME resolution the app uses, so
     running it locally migrates the local db and running it on Railway (where
     SMT_DB_PATH points at the mounted volume) migrates the volume db.
  2. Backs up the existing db file to <db>.bak-<UTC-timestamp> BEFORE touching it.
  3. Adds the `summary TEXT` column only if missing, via ALTER TABLE ADD COLUMN,
     which SQLite performs in place — existing rows are preserved (summary = NULL),
     never dropped or rewritten.
  4. Verifies the row count is unchanged, and is a no-op on an already-migrated db.

Run from the repo root:  python scripts/migrate_add_summary.py
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import shutil
import sqlite3
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from api import db  # noqa: E402  (path set above)


def _session_columns(conn: sqlite3.Connection) -> set[str]:
    return {row[1] for row in conn.execute("PRAGMA table_info(sessions)")}


def _row_count(conn: sqlite3.Connection) -> int:
    try:
        return conn.execute("SELECT COUNT(*) FROM sessions").fetchone()[0]
    except sqlite3.OperationalError:
        return 0


def main() -> int:
    path = db._db_path()
    print(f"Active DB path (SMT_DB_PATH-aware): {path}")

    if not path.exists():
        # No existing data. A fresh db created by the app already includes the
        # column (it is in the CREATE TABLE schema), so there is nothing to migrate.
        print("No existing database file — nothing to migrate.")
        print("A newly created db will already contain the `summary` column.")
        return 0

    # 1) Back up first.
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup = path.with_name(f"{path.name}.bak-{stamp}")
    shutil.copy2(path, backup)
    print(f"Backed up existing db -> {backup}")

    conn = sqlite3.connect(path)
    try:
        before = _row_count(conn)
        cols = _session_columns(conn)
        if "sessions" not in {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )}:
            print("No `sessions` table present; nothing to migrate.")
            return 0

        if "summary" in cols:
            print(f"`summary` column already present. No-op. (sessions rows: {before})")
            return 0

        conn.execute("ALTER TABLE sessions ADD COLUMN summary TEXT")
        conn.commit()
        after = _row_count(conn)
        print(f"Added `summary TEXT` column. sessions rows before={before} after={after}")
        if before != after:
            print("WARNING: row count changed during migration — inspect the backup!")
            return 1
        print("Migration complete. Existing session data preserved (summary = NULL).")
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
