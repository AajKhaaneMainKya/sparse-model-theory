"""Daily scheduled draft generation: pick a topic, call Akshar, store as
pending, notify Telegram.

Mirrors the scheduling pattern already used in
~/Dev/claude-writing-agent/hermes/main.py (apscheduler BackgroundScheduler,
cron trigger, same 6am IST schedule) -- implemented fresh here, not by
importing that repo.
"""
from __future__ import annotations

import logging
import threading
from pathlib import Path

from apscheduler.schedulers.background import BackgroundScheduler

from . import db
from . import telegram_bot
from .akshar_client import AksharError, generate_draft

logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parents[1]
TOPICS_FILE = ROOT / "config" / "draft_topics.txt"
_TOPIC_INDEX_FILE = ROOT / "data" / ".draft_topic_index"

_scheduler = BackgroundScheduler()
_topic_lock = threading.Lock()


def _load_topics() -> list[str]:
    if not TOPICS_FILE.exists():
        return []
    lines = [line.strip() for line in TOPICS_FILE.read_text(encoding="utf-8").splitlines()]
    return [line for line in lines if line and not line.startswith("#")]


def _next_topic() -> str | None:
    """Simple round-robin rotation through config/draft_topics.txt -- a plain
    text file Rahul can edit directly, per the explicit choice to skip
    AMA-question-pattern topic analysis given limited time. Position is
    tracked in a small local cursor file, not the SQLite db (it's a rotation
    index, not data worth querying)."""
    topics = _load_topics()
    if not topics:
        return None
    with _topic_lock:
        idx = 0
        if _TOPIC_INDEX_FILE.exists():
            try:
                idx = int(_TOPIC_INDEX_FILE.read_text().strip())
            except ValueError:
                idx = 0
        topic = topics[idx % len(topics)]
        _TOPIC_INDEX_FILE.parent.mkdir(parents=True, exist_ok=True)
        _TOPIC_INDEX_FILE.write_text(str(idx + 1))
    return topic


def _derive_title(article: str, topic: str) -> str:
    """Akshar's headless output has no separate title field -- derive one
    from the article's first line (strip a leading markdown '#'), falling
    back to the topic if the first line is missing or implausibly long."""
    first_line = article.strip().splitlines()[0].strip() if article.strip() else ""
    first_line = first_line.lstrip("#").strip()
    if first_line and len(first_line) <= 120:
        return first_line
    return topic[:120]


def run_daily_draft() -> dict[str, object]:
    """Generates one draft end to end: picks a topic, calls Akshar (blocking,
    up to ~16 minutes), stores the result as a pending draft, and notifies
    Telegram. Safe to call directly for a manual trigger -- callers invoking
    this from a request handler MUST run it in a background thread."""
    topic = _next_topic()
    if not topic:
        logger.error("draft_job_no_topics config_file=%s", TOPICS_FILE)
        telegram_bot.send_message(f"⚠️ Daily draft failed: no topics configured in {TOPICS_FILE}")
        return {"status": "error", "error": "no_topics"}

    logger.info("draft_job_started topic=%s", topic)
    try:
        result = generate_draft(topic)
    except AksharError as exc:
        logger.error("draft_job_failed topic=%s error=%s", topic, exc)
        telegram_bot.send_message(f"⚠️ Daily draft failed for topic \"{topic}\":\n{exc}")
        return {"status": "error", "error": str(exc)}

    article = result["article"]
    title = _derive_title(article, topic)
    draft = db.add_draft(
        title=title,
        content=article,
        editorial_score=result.get("editorial_score"),
        status="pending",
        topic_source=topic,
    )
    logger.info("draft_job_stored draft_id=%s title=%s", draft["id"], title)
    telegram_bot.send_draft_notification(draft)
    return {"status": "done", "draft_id": draft["id"]}


def _scheduled_job() -> None:
    logger.info("draft_scheduled_job_firing")
    try:
        run_daily_draft()
    except Exception:
        logger.exception("draft_scheduled_job_unhandled_error")


def start_scheduler() -> None:
    """Starts the daily cron job -- 6am IST (00:30 UTC), matching Hermes's
    own schedule. Safe to call more than once: APScheduler replaces the
    existing job for a repeated id rather than double-scheduling."""
    _scheduler.add_job(_scheduled_job, "cron", hour=0, minute=30, id="daily_draft", replace_existing=True)
    if not _scheduler.running:
        _scheduler.start()
    logger.info("draft_scheduler_started")
