"""Telegram notifications for pending drafts, with inline Approve/Reject buttons.

A fresh implementation for sparse-model-theory. Mirrors the pattern already
used in ~/Dev/claude-writing-agent/hermes/telegram_bot.py -- raw Telegram
Bot API calls (no python-telegram-bot dependency), long-polling for
callback_query updates in a background thread -- but does not import from
or call into that repo; this is a separate integration in this repo, as
the task asked.
"""
from __future__ import annotations

import json
import logging
import os
import re
import threading
import time
from urllib import request as urlrequest
from urllib.error import HTTPError, URLError

from . import db

logger = logging.getLogger(__name__)

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")

_API_BASE = "https://api.telegram.org"


def _call(method: str, payload: dict, timeout: int = 15) -> dict | None:
    if not TELEGRAM_BOT_TOKEN:
        logger.warning("telegram_not_configured method=%s", method)
        return None
    url = f"{_API_BASE}/bot{TELEGRAM_BOT_TOKEN}/{method}"
    data = json.dumps(payload).encode("utf-8")
    req = urlrequest.Request(url, data=data, headers={"content-type": "application/json"}, method="POST")
    try:
        with urlrequest.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except (HTTPError, URLError, TimeoutError, OSError) as exc:
        logger.error("telegram_request_failed method=%s error=%s", method, exc)
        return None


def send_message(text: str) -> bool:
    """Plain-text notification -- used for failure alerts."""
    if not TELEGRAM_CHAT_ID:
        return False
    result = _call("sendMessage", {"chat_id": TELEGRAM_CHAT_ID, "text": text, "parse_mode": "Markdown"})
    return bool(result and result.get("ok"))


def _first_sentences(text: str, count: int = 2, max_chars: int = 400) -> str:
    parts = re.split(r"(?<=[.!?])\s+", text.strip())
    excerpt = " ".join(parts[:count])
    return excerpt[:max_chars]


def send_draft_notification(draft: dict[str, object]) -> bool:
    """Sends title, a short excerpt, editorial score, and Approve/Reject buttons."""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        logger.warning("telegram_notification_skipped missing_config=true draft_id=%s", draft.get("id"))
        return False

    excerpt = _first_sentences(str(draft.get("content", "")))
    message = (
        "📝 New draft pending review\n\n"
        f"*{draft.get('title', 'Untitled')}*\n\n"
        f"{excerpt}\n\n"
        f"Editorial score: {draft.get('editorial_score', 'n/a')}/100"
    )
    draft_id = draft["id"]
    keyboard = {
        "inline_keyboard": [[
            {"text": "✅ Approve", "callback_data": f"approve:{draft_id}"},
            {"text": "❌ Reject", "callback_data": f"reject:{draft_id}"},
        ]]
    }
    result = _call("sendMessage", {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "Markdown",
        "reply_markup": keyboard,
    })
    return bool(result and result.get("ok"))


def _answer_callback(query_id: str | None, text: str) -> None:
    if not query_id:
        return
    _call("answerCallbackQuery", {"callback_query_id": query_id, "text": text}, timeout=10)


def _handle_callback(callback_query: dict) -> None:
    data = callback_query.get("data", "")
    query_id = callback_query.get("id")
    if ":" not in data:
        return
    action, draft_id = data.split(":", 1)

    draft = db.get_draft(draft_id)
    if not draft:
        _answer_callback(query_id, "Draft not found")
        return

    if action == "approve":
        db.update_draft_status(draft_id, "approved")
        _answer_callback(query_id, "✅ Approved — now live")
        logger.info("draft_approved draft_id=%s", draft_id)
    elif action == "reject":
        db.update_draft_status(draft_id, "rejected")
        _answer_callback(query_id, "❌ Rejected")
        logger.info("draft_rejected draft_id=%s", draft_id)


def _poll_loop() -> None:
    logger.info("telegram_polling_started")
    offset = None
    while True:
        try:
            url = f"{_API_BASE}/bot{TELEGRAM_BOT_TOKEN}/getUpdates?timeout=30"
            if offset is not None:
                url += f"&offset={offset}"
            req = urlrequest.Request(url, method="GET")
            with urlrequest.urlopen(req, timeout=35) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            for update in data.get("result", []):
                offset = update["update_id"] + 1
                callback = update.get("callback_query")
                if callback:
                    _handle_callback(callback)
        except (HTTPError, URLError, TimeoutError, OSError) as exc:
            logger.warning("telegram_poll_error error=%s", exc)
            time.sleep(5)
        except Exception:
            logger.exception("telegram_poll_unexpected_error")
            time.sleep(5)


def start_polling() -> None:
    """Starts the Telegram long-poll loop in a background daemon thread. Safe
    to call even when TELEGRAM_BOT_TOKEN is unset -- it logs and no-ops
    rather than starting a loop that can never do anything."""
    if not TELEGRAM_BOT_TOKEN:
        logger.warning("telegram_polling_not_started missing_bot_token=true")
        return
    thread = threading.Thread(target=_poll_loop, daemon=True)
    thread.start()
