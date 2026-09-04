"""Daily scheduled draft generation: pick a topic, call Akshar, store as
pending, notify Telegram.

Mirrors the scheduling pattern already used in
~/Dev/claude-writing-agent/hermes/main.py (apscheduler BackgroundScheduler,
cron trigger, same 6am IST schedule) -- implemented fresh here, not by
importing that repo.
"""
from __future__ import annotations

import logging
import queue
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

# --- Sequential draft queue -------------------------------------------------
#
# Every trigger path (daily cron, admin HTTP trigger, Telegram /draft command)
# funnels through enqueue_draft() rather than spawning its own thread. Jobs
# run one at a time, in submission order, via a single long-lived worker
# thread. Deliberately NOT concurrent: each job is a blocking call into
# Akshar taking up to ~16 minutes, and Akshar has its own per-account
# rate/cap limits -- firing several jobs at once risks tripping those limits
# or producing partial/rejected results, for a time saving that mostly
# doesn't matter here (these are background drafts, not something a user is
# waiting on synchronously). A sequential queue also means "send 3 topics in
# a row" from Telegram just works, in order, without any extra coordination.
_draft_queue: "queue.Queue[str | None]" = queue.Queue()
_queue_worker_started = False
_queue_worker_lock = threading.Lock()
_jobs_in_flight = 0  # includes the job currently running, not just queued
_jobs_in_flight_lock = threading.Lock()


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


def run_draft(topic: str | None = None) -> dict[str, object]:
    """Generates one draft end to end: uses `topic` if given, otherwise picks
    the next one from the rotating topic list, calls Akshar (blocking, up to
    ~16 minutes), stores the result as a pending draft, and notifies
    Telegram. Callers should normally go through enqueue_draft() rather than
    calling this directly, so concurrent triggers serialize instead of
    racing each other against Akshar's rate limits."""
    if topic is None:
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


def run_daily_draft() -> dict[str, object]:
    """Back-compat name for run_draft(None) -- the rotating-topic case.
    Kept as a thin wrapper since it's a clearer name for the cron/no-topic
    path than a bare run_draft() call would be."""
    return run_draft(None)


def _queue_worker() -> None:
    global _jobs_in_flight
    logger.info("draft_queue_worker_started")
    while True:
        topic = _draft_queue.get()
        try:
            run_draft(topic)
        except Exception:
            logger.exception("draft_queue_job_unhandled_error topic=%s", topic)
        finally:
            with _jobs_in_flight_lock:
                _jobs_in_flight -= 1
            _draft_queue.task_done()


def enqueue_draft(topic: str | None = None) -> int:
    """Adds one draft job to the sequential queue and returns its 1-based
    position (1 = will start immediately, since nothing else is running).
    Starts the single background worker thread on first use -- safe to call
    even if start_scheduler() was never called (e.g. Telegram configured
    without the cron job ever firing)."""
    global _queue_worker_started, _jobs_in_flight
    with _queue_worker_lock:
        if not _queue_worker_started:
            threading.Thread(target=_queue_worker, daemon=True).start()
            _queue_worker_started = True
    with _jobs_in_flight_lock:
        _jobs_in_flight += 1
        position = _jobs_in_flight
        # put() happens inside the same lock as the increment so the
        # reported position always matches actual queue order under
        # concurrent submitters (e.g. Telegram + admin trigger at once).
        _draft_queue.put(topic)
    logger.info("draft_job_enqueued topic=%s position=%d", topic, position)
    return position


def _scheduled_job() -> None:
    logger.info("draft_scheduled_job_firing")
    try:
        enqueue_draft(None)
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
