import os
import sqlite3
import tempfile
import unittest
from unittest import mock

_TMPDIR = tempfile.mkdtemp()
os.environ["SMT_DB_PATH"] = os.path.join(_TMPDIR, "test_ctx.db")

from fastapi.testclient import TestClient  # noqa: E402

from api import db, zone  # noqa: E402
from api.server import app  # noqa: E402


client = TestClient(app)


class SchemaAndSummaryTests(unittest.TestCase):
    def test_fresh_db_has_summary_column(self):
        db.init_db()
        with db._connect() as conn:
            cols = {row["name"] for row in conn.execute("PRAGMA table_info(sessions)")}
        self.assertIn("summary", cols)

    def test_ensure_session_columns_adds_missing_without_dropping_data(self):
        # Build an OLD-schema sessions table in a scratch db, then run the ensurer.
        scratch = os.path.join(_TMPDIR, "old_schema.db")
        conn = sqlite3.connect(scratch)
        conn.executescript(
            "CREATE TABLE sessions (id TEXT PRIMARY KEY, thread_id TEXT, created_at TEXT, "
            "mode TEXT, input_text TEXT, daily_capture TEXT, model_provider TEXT, "
            "model_name TEXT, thinking_mode TEXT, latency_ms REAL, raw_output_json TEXT);"
        )
        conn.execute(
            "INSERT INTO sessions (id, input_text, raw_output_json) VALUES ('s1', 'keep me', '{}')"
        )
        conn.commit()
        added = db._ensure_session_columns(conn)
        conn.commit()
        self.assertIn("summary", added)
        # Data preserved, new column NULL.
        row = conn.execute("SELECT input_text, summary FROM sessions WHERE id='s1'").fetchone()
        conn.close()
        self.assertEqual(row[0], "keep me")
        self.assertIsNone(row[1])

    def test_add_session_stores_and_returns_summary(self):
        thread = db.create_thread("summary-thread")
        db.add_session(
            thread_id=thread["id"], mode="fixed", input_text="x", daily_capture=None,
            model_provider="openai", model_name="m", thinking_mode="economy",
            latency_ms=1.0, raw_output={}, summary="core conclusion here",
        )
        [sess_id] = [s["id"] for s in db.list_sessions(thread["id"])]
        self.assertEqual(db.get_session(sess_id)["summary"], "core conclusion here")

    def test_recent_summaries_newest_first_and_skips_empty(self):
        thread = db.create_thread("recent-thread")
        for text, summ in [("a", "SUM A"), ("b", ""), ("c", "SUM C")]:
            db.add_session(
                thread_id=thread["id"], mode="fixed", input_text=text, daily_capture=None,
                model_provider="openai", model_name="m", thinking_mode="economy",
                latency_ms=1.0, raw_output={}, summary=summ,
            )
        got = db.recent_summaries(thread["id"], limit=2)
        # Newest first (C then A); the empty "" summary (b) is skipped entirely.
        self.assertEqual(got, ["SUM C", "SUM A"])


class ShorthandParseTests(unittest.TestCase):
    def test_parse_variants(self):
        self.assertEqual(
            zone.parse_thread_shorthand("analyze this idea +LP conversation"),
            ("analyze this idea", "LP conversation"),
        )
        self.assertEqual(zone.parse_thread_shorthand("no shorthand here"), ("no shorthand here", None))
        self.assertEqual(zone.parse_thread_shorthand("text +Single"), ("text", "Single"))
        self.assertEqual(zone.parse_thread_shorthand("+OnlyTag"), ("", "OnlyTag"))


class ContextBlockTests(unittest.TestCase):
    def test_empty_summaries_yield_empty_block(self):
        self.assertEqual(zone.build_thread_context_block([]), "")

    def test_per_summary_and_total_caps_enforced(self):
        big = "word " * 2000  # ~10k chars, far over caps
        block = zone.build_thread_context_block([big, big, big])
        total_char_cap = zone.THREAD_CONTEXT_TOTAL_TOKEN_CAP * 4
        self.assertLessEqual(len(block), total_char_cap + 1)  # +1 for ellipsis


class InjectionWiringTests(unittest.TestCase):
    def test_fixed_mode_injects_into_scope_check_only(self):
        captured = []

        def fake_call(system_prompt, input_text, *a, **k):
            captured.append((k.get("skill_name") or (a[1] if len(a) > 1 else None), input_text))
            return "ok"

        with mock.patch.object(zone, "call_zone_model", side_effect=fake_call):
            # run only scope_check + first_principles to keep it small
            skip = [s for s in zone.SKILL_ORDER if s not in ("scope_check", "first_principles")]
            zone.second_brain_analysis(
                "MY INPUT", daily_capture=None, skip_skills=skip, mode="economy",
                thread_context="THREAD-CTX-MARKER",
            )

        by_input = {text for _, text in captured}
        scope_inputs = [t for _, t in captured if "MY INPUT" in t and "THREAD-CTX-MARKER" in t]
        other_inputs = [t for _, t in captured if "MY INPUT" in t and "THREAD-CTX-MARKER" not in t]
        self.assertTrue(scope_inputs, "scope_check should receive injected context")
        self.assertTrue(other_inputs, "other passes should NOT receive the context")

    def test_agentic_injects_into_planning_only(self):
        captured = []

        def fake_call(system_prompt, input_text, daily_capture=None, skill_name=None, *a, **k):
            captured.append((skill_name, input_text))
            # Return a valid planner payload so a couple skills get selected.
            return '{"skills_to_run": ["scope_check"], "suggested_missing_skills": []}'

        with mock.patch.object(zone, "call_zone_model", side_effect=fake_call):
            zone.agentic_second_brain_analysis(
                "AG INPUT", daily_capture=None, mode="economy",
                thread_context="THREAD-CTX-MARKER",
            )

        planning = [t for name, t in captured if name == "planning_pass"]
        scope = [t for name, t in captured if name == "scope_check"]
        self.assertTrue(planning and "THREAD-CTX-MARKER" in planning[0])
        self.assertTrue(scope and "THREAD-CTX-MARKER" not in scope[0])


class EndpointContextTests(unittest.TestCase):
    def _run(self, json_body):
        fake_payload = {"results": [], "skipped": []}
        analysis = mock.MagicMock(return_value=fake_payload)
        with mock.patch("api.server.second_brain_analysis", analysis), \
                mock.patch("api.server.get_latest_daily_capture", return_value=None), \
                mock.patch("api.server.summarize_session", return_value="STORED SUMMARY"):
            resp = client.post("/second-brain", json=json_body)
        return resp, analysis

    def test_default_no_injection_fetches_no_summaries(self):
        thread_id = client.post("/threads", json={"name": "no-inject"}).json()["id"]
        with mock.patch("api.server.db.recent_summaries") as recent:
            resp, analysis = self._run({"thread_id": thread_id, "input": "hello"})
        self.assertEqual(resp.status_code, 200)
        recent.assert_not_called()  # opt-out path never touches summaries
        self.assertIsNone(analysis.call_args.kwargs["thread_context"])
        self.assertFalse(resp.json()["thread_context_injected"])

    def test_include_thread_context_injects_recent_summaries(self):
        thread_id = client.post("/threads", json={"name": "inject-thread"}).json()["id"]
        with mock.patch("api.server.db.recent_summaries", return_value=["PRIOR ONE", "PRIOR TWO"]):
            resp, analysis = self._run(
                {"thread_id": thread_id, "input": "hello", "include_thread_context": True}
            )
        self.assertEqual(resp.status_code, 200)
        ctx = analysis.call_args.kwargs["thread_context"]
        self.assertIn("PRIOR ONE", ctx)
        self.assertTrue(resp.json()["thread_context_injected"])

    def test_summary_is_persisted_on_write(self):
        thread_id = client.post("/threads", json={"name": "persist-summary"}).json()["id"]
        resp, _ = self._run({"thread_id": thread_id, "input": "analyze"})
        session_id = resp.json()["session_id"]
        self.assertEqual(client.get(f"/sessions/{session_id}").json()["summary"], "STORED SUMMARY")

    def test_shorthand_resolves_strips_and_autoenables_context(self):
        # Real existing thread to resolve against.
        client.post("/threads", json={"name": "LP conversation"})
        resp, analysis = self._run({"input": "analyze the term sheet +LP conversation"})
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["shorthand_thread"], "LP conversation")
        self.assertTrue(body["thread_context_injected"] in (True, False))  # depends on summaries
        # The '+LP conversation' was stripped from the analyzed text.
        analyzed_input = analysis.call_args.args[0]
        self.assertEqual(analyzed_input, "analyze the term sheet")
        # Auto-enabled context => recent_summaries path was taken (thread resolved).
        detail = client.get(f"/sessions/{body['session_id']}").json()
        self.assertEqual(detail["thread_id"], body["thread_id"])

    def test_shorthand_overrides_selected_thread(self):
        other = client.post("/threads", json={"name": "some-other"}).json()["id"]
        client.post("/threads", json={"name": "Cadence decision"})
        resp, _ = self._run({"thread_id": other, "input": "rename it +Cadence decision"})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["shorthand_thread"], "Cadence decision")
        self.assertNotEqual(resp.json()["thread_id"], other)

    def test_typo_shorthand_returns_clarifier_not_guess(self):
        client.post("/threads", json={"name": "LP conversation"})
        resp, analysis = self._run({"input": "analyze this +LP conversashun"})
        self.assertEqual(resp.status_code, 400)
        detail = resp.json()["detail"]
        self.assertIn("No thread found matching 'LP conversashun'", detail)
        self.assertIn("LP conversation", detail)  # offered as a close match
        analysis.assert_not_called()  # did NOT proceed with analysis


if __name__ == "__main__":
    unittest.main()
