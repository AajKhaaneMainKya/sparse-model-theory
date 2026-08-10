import os
import tempfile
import unittest
from unittest import mock

# Point persistence at a throwaway db BEFORE importing the server (its import runs
# db.init_db()). Every _connect() re-reads SMT_DB_PATH, so this fully isolates the
# test database from data/sparse_model_theory.db.
_TMPDIR = tempfile.mkdtemp()
os.environ["SMT_DB_PATH"] = os.path.join(_TMPDIR, "test_sessions.db")

from fastapi.testclient import TestClient  # noqa: E402

from api import db  # noqa: E402
from api.server import app  # noqa: E402


client = TestClient(app)


class ThreadDbTests(unittest.TestCase):
    def test_create_thread_starts_with_zero_sessions(self):
        thread = db.create_thread("LP conversation")
        self.assertTrue(thread["id"])
        self.assertEqual(thread["name"], "LP conversation")
        self.assertEqual(thread["created_at"], thread["updated_at"])

        fetched = db.get_thread(thread["id"])
        self.assertIsNotNone(fetched)
        self.assertEqual(fetched["session_count"], 0)

    def test_add_session_writes_row_and_bumps_thread(self):
        thread = db.create_thread("Cadence decision")
        original_updated = thread["updated_at"]

        session = db.add_session(
            thread_id=thread["id"],
            mode="agentic",
            input_text="Should we rename Cadence?",
            daily_capture="today's capture",
            model_provider="openai",
            model_name="gpt-5.6-terra",
            thinking_mode="balanced",
            latency_ms=1234.5,
            raw_output={"results": [{"skill": "scope_check", "output": "..."}]},
        )
        self.assertTrue(session["id"])
        self.assertEqual(session["thread_id"], thread["id"])

        # Row is retrievable with raw_output parsed back to an object, not a string.
        stored = db.get_session(session["id"])
        self.assertEqual(stored["thread_id"], thread["id"])
        self.assertEqual(stored["latency_ms"], 1234.5)
        self.assertIsInstance(stored["raw_output"], dict)
        self.assertEqual(stored["raw_output"]["results"][0]["skill"], "scope_check")
        self.assertNotIn("raw_output_json", stored)

        # Session count and updated_at reflect the new session.
        refreshed = db.get_thread(thread["id"])
        self.assertEqual(refreshed["session_count"], 1)
        self.assertGreaterEqual(refreshed["updated_at"], original_updated)

    def test_get_or_create_uncategorized_is_reused(self):
        first = db.get_or_create_uncategorized_thread()
        second = db.get_or_create_uncategorized_thread()
        self.assertEqual(first["id"], second["id"])
        self.assertEqual(first["name"], "Uncategorized")

    def test_move_session_rethreads_and_reports_missing(self):
        thread_a = db.create_thread("A")
        thread_b = db.create_thread("B")
        session = db.add_session(
            thread_id=thread_a["id"],
            mode="fixed",
            input_text="movable",
            daily_capture=None,
            model_provider="openai",
            model_name="gpt-5.6-terra",
            thinking_mode="balanced",
            latency_ms=1.0,
            raw_output={},
        )

        moved = db.move_session(session["id"], thread_b["id"])
        self.assertEqual(moved["thread_id"], thread_b["id"])
        self.assertEqual(db.get_thread(thread_a["id"])["session_count"], 0)
        self.assertEqual(db.get_thread(thread_b["id"])["session_count"], 1)
        self.assertEqual(db.get_session(session["id"])["thread_id"], thread_b["id"])

        self.assertIsNone(db.move_session("no-such-session", thread_b["id"]))

    def test_list_sessions_truncates_input_text(self):
        thread = db.create_thread("Long input thread")
        long_text = "x" * 250
        db.add_session(
            thread_id=thread["id"],
            mode="fixed",
            input_text=long_text,
            daily_capture=None,
            model_provider="openai",
            model_name="gpt-5.6-terra",
            thinking_mode="economy",
            latency_ms=1.0,
            raw_output={},
        )
        listed = db.list_sessions(thread["id"])
        self.assertEqual(len(listed), 1)
        self.assertLessEqual(len(listed[0]["input_text"]), 104)  # ~100 + "..."
        self.assertTrue(listed[0]["input_text"].endswith("..."))


class ThreadApiTests(unittest.TestCase):
    def test_post_and_get_threads(self):
        resp = client.post("/threads", json={"name": "API thread"})
        self.assertEqual(resp.status_code, 200)
        thread_id = resp.json()["id"]
        self.assertTrue(thread_id)

        listing = client.get("/threads").json()["threads"]
        ids = [t["id"] for t in listing]
        self.assertIn(thread_id, ids)
        created = next(t for t in listing if t["id"] == thread_id)
        self.assertEqual(created["session_count"], 0)

    def test_second_brain_404_on_missing_thread(self):
        resp = client.post(
            "/second-brain",
            json={"thread_id": "does-not-exist", "input": "hello", "agentic": False},
        )
        self.assertEqual(resp.status_code, 404)
        self.assertIn("not found", resp.json()["detail"])

    def test_second_brain_writes_session_linked_to_thread(self):
        thread_id = client.post("/threads", json={"name": "Run thread"}).json()["id"]

        fake_payload = {"results": [{"skill": "scope_check", "output": "ok"}], "skipped": []}
        with mock.patch("api.server.second_brain_analysis", return_value=fake_payload), \
                mock.patch("api.server.get_latest_daily_capture", return_value=None):
            resp = client.post(
                "/second-brain",
                json={"thread_id": thread_id, "input": "Analyze this", "agentic": False},
            )

        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["thread_id"], thread_id)
        session_id = body["session_id"]
        self.assertTrue(session_id)

        # A row actually landed, linked to the right thread.
        rows = db.list_sessions(thread_id)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["id"], session_id)
        self.assertEqual(rows[0]["mode"], "fixed")

        # Endpoint round-trips: thread listing and full-session detail.
        thread_sessions = client.get(f"/threads/{thread_id}/sessions").json()
        self.assertEqual(thread_sessions["thread"]["session_count"], 1)
        self.assertEqual(len(thread_sessions["sessions"]), 1)

        detail = client.get(f"/sessions/{session_id}").json()
        self.assertEqual(detail["thread_id"], thread_id)
        self.assertIsInstance(detail["raw_output"], dict)
        self.assertEqual(detail["raw_output"]["results"][0]["skill"], "scope_check")

    def test_second_brain_without_thread_uses_uncategorized(self):
        fake_payload = {"results": [], "skipped": []}
        with mock.patch("api.server.second_brain_analysis", return_value=fake_payload), \
                mock.patch("api.server.get_latest_daily_capture", return_value=None):
            first = client.post("/second-brain", json={"input": "no thread here"}).json()
            second = client.post("/second-brain", json={"input": "still no thread"}).json()

        self.assertTrue(first["thread_id"])
        # Both thread-less captures reuse the same Uncategorized thread.
        self.assertEqual(first["thread_id"], second["thread_id"])

        listing = client.get("/threads").json()["threads"]
        uncategorized = next(t for t in listing if t["id"] == first["thread_id"])
        self.assertEqual(uncategorized["name"], "Uncategorized")
        self.assertGreaterEqual(uncategorized["session_count"], 2)

    def test_bad_explicit_thread_id_is_404_not_autocreated(self):
        resp = client.post(
            "/second-brain",
            json={"thread_id": "typo-id", "input": "hi"},
        )
        self.assertEqual(resp.status_code, 404)
        # The bad id must not have been created.
        self.assertEqual(client.get("/threads/typo-id/sessions").status_code, 404)

    def test_patch_moves_session_between_threads(self):
        source = client.post("/threads", json={"name": "Source"}).json()["id"]
        dest = client.post("/threads", json={"name": "Destination"}).json()["id"]

        fake_payload = {"results": [], "skipped": []}
        with mock.patch("api.server.second_brain_analysis", return_value=fake_payload), \
                mock.patch("api.server.get_latest_daily_capture", return_value=None):
            session_id = client.post(
                "/second-brain", json={"thread_id": source, "input": "organize me later"}
            ).json()["session_id"]

        resp = client.patch(f"/sessions/{session_id}", json={"thread_id": dest})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["thread_id"], dest)

        self.assertEqual(len(client.get(f"/threads/{source}/sessions").json()["sessions"]), 0)
        dest_sessions = client.get(f"/threads/{dest}/sessions").json()["sessions"]
        self.assertEqual([s["id"] for s in dest_sessions], [session_id])

    def test_patch_404s_for_missing_session_or_target_thread(self):
        thread_id = client.post("/threads", json={"name": "Patch target"}).json()["id"]
        # Missing session.
        self.assertEqual(
            client.patch("/sessions/nope", json={"thread_id": thread_id}).status_code, 404
        )
        # Missing target thread (real session).
        fake_payload = {"results": [], "skipped": []}
        with mock.patch("api.server.second_brain_analysis", return_value=fake_payload), \
                mock.patch("api.server.get_latest_daily_capture", return_value=None):
            session_id = client.post(
                "/second-brain", json={"thread_id": thread_id, "input": "x"}
            ).json()["session_id"]
        self.assertEqual(
            client.patch(f"/sessions/{session_id}", json={"thread_id": "ghost"}).status_code, 404
        )

    def test_sessions_endpoints_404(self):
        self.assertEqual(client.get("/threads/nope/sessions").status_code, 404)
        self.assertEqual(client.get("/sessions/nope").status_code, 404)


if __name__ == "__main__":
    unittest.main()
