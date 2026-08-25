import os
import tempfile
import unittest
from unittest import mock

from fastapi.testclient import TestClient


class OpenClawAgentTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.env = mock.patch.dict(os.environ, {"SMT_DB_PATH": f"{self.tmp.name}/sessions.db"})
        self.env.start()

        from api import db, server

        db.init_db()
        self.server = server
        self.client = TestClient(server.app)

    def tearDown(self):
        self.env.stop()
        self.tmp.cleanup()

    def test_capture_uses_daily_capture_path(self):
        with mock.patch.object(self.server, "DAILY_DIR") as daily_dir:
            daily_dir.mkdir.return_value = None
            path = mock.Mock()
            path.exists.return_value = False
            daily_dir.__truediv__.return_value = path

            response = self.client.post(
                "/openclaw/agent",
                json={"message": "/capture Today I noticed founder-led services sell better."},
            )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["kind"], "capture")
        self.assertIn("Captured for", data["reply"])
        self.assertIsNone(data["full_result"])
        path.write_text.assert_called_once()

    def test_capture_can_be_disabled(self):
        response = self.client.post(
            "/openclaw/agent",
            json={"message": "/capture blocked", "allow_capture": False},
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["kind"], "error")
        self.assertIn("disabled", data["reply"])

    def test_think_runs_agentic_analysis_without_persisting_session(self):
        fake_payload = {
            "agentic": True,
            "results": [{"skill": "scope_check", "output": "Scoped."}],
            "synthesis": {"skill": "synthesis_pass", "output": "Compact synthesis."},
        }
        with mock.patch.object(
            self.server, "agentic_second_brain_analysis", return_value=fake_payload
        ) as analysis, mock.patch.object(self.server.db, "add_session") as add_session:
            response = self.client.post(
                "/openclaw/agent",
                json={"message": "/think Should I build this?", "mode": "economy"},
            )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["kind"], "analysis")
        self.assertEqual(data["reply"], "Compact synthesis.")
        self.assertIsNone(data["full_result"])
        analysis.assert_called_once()
        self.assertEqual(analysis.call_args.kwargs["mode"], "economy")
        add_session.assert_not_called()

    def test_followup_prefix_wraps_question_and_can_return_full(self):
        fake_payload = {
            "agentic": True,
            "results": [{"skill": "scope_check", "output": "Scoped follow-up."}],
        }
        with mock.patch.object(
            self.server, "agentic_second_brain_analysis", return_value=fake_payload
        ) as analysis:
            response = self.client.post(
                "/openclaw/agent",
                json={
                    "message": "/followup What assumptions are missing?",
                    "return_full": True,
                    "skip_skills": ["visualization"],
                },
            )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["kind"], "analysis")
        self.assertIsInstance(data["full_result"], dict)
        self.assertEqual(
            analysis.call_args.args[0],
            "Follow-up question: What assumptions are missing?",
        )
        self.assertEqual(analysis.call_args.kwargs["skip_skills"], ["visualization"])


if __name__ == "__main__":
    unittest.main()
