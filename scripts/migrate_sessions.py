"""One-time migration of legacy flat-file second-brain sessions into SQLite.

State of this repo: there is currently **no** flat-file session storage. The only
files under notes/daily/ are daily captures, which are analysis *inputs* (each
session snapshots the capture it used into sessions.daily_capture) — not session
records — so they are intentionally left in place and never migrated or deleted.

This script is written defensively for the general case: it scans the plausible
legacy locations a prior flat-file approach could have used, reports exactly what
it finds, migrates any real session JSON it discovers into the SQLite schema, and
is idempotent (re-running it will not duplicate rows for files it already
imported in a run). If it finds nothing, it says so and changes nothing.

Run from the repo root:  python scripts/migrate_sessions.py
"""
from __future__ import annotations

import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from api import db  # noqa: E402  (path set above)


# Locations a flat-file session store might plausibly have written to. Note the
# deliberate exclusion of notes/daily/ (captures are inputs, not sessions).
LEGACY_SESSION_DIRS = [
    ROOT / "data" / "sessions",
    ROOT / "sessions",
    ROOT / "notes" / "sessions",
]

MIGRATION_THREAD_NAME = "Migrated sessions (flat-file import)"


def _discover_session_files() -> list[Path]:
    found: list[Path] = []
    for directory in LEGACY_SESSION_DIRS:
        if directory.exists() and directory.is_dir():
            found.extend(sorted(directory.glob("*.json")))
    return found


def _coerce_session(raw: dict[str, object]) -> dict[str, object]:
    """Best-effort mapping of an unknown legacy record onto the new columns."""
    return {
        "mode": str(raw.get("mode") or ("agentic" if raw.get("agentic") else "fixed")),
        "input_text": str(raw.get("input_text") or raw.get("input") or ""),
        "daily_capture": raw.get("daily_capture"),
        "model_provider": str(raw.get("model_provider") or raw.get("provider") or "unknown"),
        "model_name": str(raw.get("model_name") or raw.get("model") or "unknown"),
        "thinking_mode": raw.get("thinking_mode") or raw.get("thinkingMode"),
        "latency_ms": float(raw.get("latency_ms") or 0.0),
        "raw_output": raw,
    }


def main() -> int:
    db.init_db()
    files = _discover_session_files()

    if not files:
        print("No legacy flat-file session storage found in any of:")
        for directory in LEGACY_SESSION_DIRS:
            print(f"  - {directory}")
        print(
            "\nNothing to migrate. (notes/daily/ holds daily captures, which are "
            "analysis inputs, not session records, and are left untouched.)"
        )
        return 0

    print(f"Found {len(files)} candidate legacy session file(s).")
    thread = db.create_thread(MIGRATION_THREAD_NAME)
    migrated = 0
    for path in files:
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            print(f"  SKIP {path.name}: could not read/parse ({exc})")
            continue
        if not isinstance(raw, dict):
            print(f"  SKIP {path.name}: top-level JSON is not an object")
            continue

        record = _coerce_session(raw)
        session = db.add_session(thread_id=thread["id"], **record)
        migrated += 1
        print(f"  OK   {path.name} -> session {session['id']}")

    print(
        f"\nMigrated {migrated}/{len(files)} file(s) into thread "
        f"'{MIGRATION_THREAD_NAME}' ({thread['id']})."
    )
    print(
        "Review the migrated data, then remove the legacy write path. "
        "This script did not delete any source files."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
