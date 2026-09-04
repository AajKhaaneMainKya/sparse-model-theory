"""Tests for the Telegram /draft command.

Two things matter here: command parsing (the UX), and the chat-ID
authorization check (the actual security boundary now that this path
bypasses admin-cookie auth entirely -- a message from any chat other than
TELEGRAM_CHAT_ID must be ignored, not processed). Also covers the
sequential-queue design (enqueue_draft), since batching several /draft
topics in a row relies on jobs genuinely running one at a time.
"""
from __future__ import annotations

import threading
import unittest
from unittest import mock

from api import telegram_bot


class DraftCommandParsingTests(unittest.TestCase):
    def test_slash_command_with_topic(self):
        is_draft, topic = telegram_bot._parse_draft_command("/draft AI agents in production")
        self.assertTrue(is_draft)
        self.assertEqual(topic, "AI agents in production")

    def test_slash_command_no_topic_falls_back_to_rotation(self):
        is_draft, topic = telegram_bot._parse_draft_command("/draft")
        self.assertTrue(is_draft)
        self.assertIsNone(topic)

    def test_slash_command_with_botname_suffix(self):
        is_draft, topic = telegram_bot._parse_draft_command("/draft@my_bot pricing models")
        self.assertTrue(is_draft)
        self.assertEqual(topic, "pricing models")

    def test_plain_prefix_form(self):
        is_draft, topic = telegram_bot._parse_draft_command("draft: sparse models in production")
        self.assertTrue(is_draft)
        self.assertEqual(topic, "sparse models in production")

    def test_case_insensitive(self):
        is_draft, topic = telegram_bot._parse_draft_command("DRAFT: Something")
        self.assertTrue(is_draft)
        self.assertEqual(topic, "Something")

    def test_unrelated_message_is_not_a_draft_command(self):
        is_draft, topic = telegram_bot._parse_draft_command("hey, how's the site looking?")
        self.assertFalse(is_draft)
        self.assertIsNone(topic)


class HandleMessageAuthorizationTests(unittest.TestCase):
    """The actual security boundary: only TELEGRAM_CHAT_ID may trigger a
    job, since this path has no admin-cookie check at all."""

    def test_authorized_chat_triggers_enqueue(self):
        with mock.patch.object(telegram_bot, "TELEGRAM_CHAT_ID", "111"), \
             mock.patch.object(telegram_bot, "send_message") as mock_send, \
             mock.patch("api.draft_scheduler.enqueue_draft", return_value=1) as mock_enqueue:
            telegram_bot._handle_message({
                "chat": {"id": 111},
                "text": "/draft sparse retrieval",
            })
            mock_enqueue.assert_called_once_with("sparse retrieval")
            mock_send.assert_called_once()
            self.assertIn("Starting draft", mock_send.call_args[0][0])

    def test_unauthorized_chat_is_ignored_not_processed(self):
        with mock.patch.object(telegram_bot, "TELEGRAM_CHAT_ID", "111"), \
             mock.patch.object(telegram_bot, "send_message") as mock_send, \
             mock.patch("api.draft_scheduler.enqueue_draft") as mock_enqueue:
            telegram_bot._handle_message({
                "chat": {"id": 999},  # a different chat entirely
                "text": "/draft sparse retrieval",
            })
            mock_enqueue.assert_not_called()
            mock_send.assert_not_called()

    def test_unauthorized_chat_ignored_before_command_parsing(self):
        # Proves the auth check runs before -- not after -- command
        # parsing: plain chatter from a stranger triggers nothing either.
        with mock.patch.object(telegram_bot, "TELEGRAM_CHAT_ID", "111"), \
             mock.patch("api.draft_scheduler.enqueue_draft") as mock_enqueue:
            telegram_bot._handle_message({"chat": {"id": 999}, "text": "hello"})
            mock_enqueue.assert_not_called()

    def test_unconfigured_chat_id_rejects_everything(self):
        # Fail closed, not open: an empty TELEGRAM_CHAT_ID must not mean
        # "anyone is authorized."
        with mock.patch.object(telegram_bot, "TELEGRAM_CHAT_ID", ""), \
             mock.patch("api.draft_scheduler.enqueue_draft") as mock_enqueue:
            telegram_bot._handle_message({"chat": {"id": 111}, "text": "/draft anything"})
            mock_enqueue.assert_not_called()

    def test_queued_position_greater_than_one_reports_wait(self):
        with mock.patch.object(telegram_bot, "TELEGRAM_CHAT_ID", "111"), \
             mock.patch.object(telegram_bot, "send_message") as mock_send, \
             mock.patch("api.draft_scheduler.enqueue_draft", return_value=3):
            telegram_bot._handle_message({"chat": {"id": 111}, "text": "/draft third in line"})
            sent_text = mock_send.call_args[0][0]
            self.assertIn("Queued", sent_text)
            self.assertIn("2 job(s) ahead", sent_text)

    def test_no_topic_falls_back_to_rotation_label(self):
        with mock.patch.object(telegram_bot, "TELEGRAM_CHAT_ID", "111"), \
             mock.patch.object(telegram_bot, "send_message") as mock_send, \
             mock.patch("api.draft_scheduler.enqueue_draft", return_value=1) as mock_enqueue:
            telegram_bot._handle_message({"chat": {"id": 111}, "text": "/draft"})
            mock_enqueue.assert_called_once_with(None)
            self.assertIn("next topic in rotation", mock_send.call_args[0][0])


class EnqueueDraftSequencingTests(unittest.TestCase):
    """Confirms the queue is genuinely sequential (one worker, FIFO), not
    concurrent -- the design decision behind batching multiple Telegram
    topics without tripping Akshar's rate/cap limits."""

    def test_jobs_run_one_at_a_time_in_submission_order(self):
        from api import draft_scheduler

        # Reset module-level singleton state so this test doesn't depend
        # on execution order relative to other tests in the process --
        # the queue/worker are deliberately module-level (one queue per
        # process), so a clean test needs a fresh queue and a fresh
        # "worker not started" flag.
        draft_scheduler._queue_worker_started = False
        draft_scheduler._jobs_in_flight = 0
        draft_scheduler._draft_queue = draft_scheduler.queue.Queue()

        order: list[tuple[str, str]] = []
        order_lock = threading.Lock()
        first_started = threading.Event()
        second_started = threading.Event()
        release_first = threading.Event()

        def fake_run_draft(topic):
            with order_lock:
                order.append(("start", topic))
            if topic == "first":
                first_started.set()
                release_first.wait(timeout=5)
            elif topic == "second":
                second_started.set()
            with order_lock:
                order.append(("end", topic))
            return {"status": "done"}

        with mock.patch.object(draft_scheduler, "run_draft", side_effect=fake_run_draft):
            position_first = draft_scheduler.enqueue_draft("first")
            position_second = draft_scheduler.enqueue_draft("second")
            self.assertEqual(position_first, 1)
            self.assertEqual(position_second, 2)

            self.assertTrue(first_started.wait(timeout=2), "first job never started")
            # "second" must NOT start while "first" is still blocked --
            # this is what makes the queue sequential rather than
            # concurrent.
            self.assertFalse(second_started.wait(timeout=0.3), "second job started concurrently with first")

            release_first.set()
            self.assertTrue(second_started.wait(timeout=2), "second job never started after first finished")

        self.assertEqual(order[0], ("start", "first"))
        self.assertIn(("start", "second"), order)


if __name__ == "__main__":
    unittest.main()
