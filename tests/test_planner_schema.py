import json
import os
import unittest
from unittest import mock

from api import zone


def _fake_responses_payload(body: dict[str, object]) -> dict[str, object]:
    """Shape a dict the way the OpenAI Responses API returns structured output."""
    return {"output_text": json.dumps(body)}


class PlannerSchemaConfigTests(unittest.TestCase):
    """These tests assert on the API-call configuration itself, not on output content.

    They are the regression guard for the hallucination fix: if the enum-constrained
    json_schema were ever removed or misconfigured, these fail even though a live model
    might still happen to return valid-looking skill names.
    """

    def test_schema_enum_matches_real_implemented_skills(self):
        enum = zone.PLANNER_OUTPUT_SCHEMA["properties"]["skills_to_run"]["items"]["enum"]
        # The enum must be EXACTLY the skills that actually have implementations.
        self.assertEqual(enum, zone.ALLOWED_SKILLS)
        self.assertEqual(set(enum), set(zone.SKILL_FUNCTIONS.keys()))

    def test_schema_shape_is_strict_and_two_field(self):
        schema = zone.PLANNER_OUTPUT_SCHEMA
        self.assertEqual(schema["type"], "object")
        self.assertFalse(schema["additionalProperties"])
        self.assertCountEqual(
            schema["required"], ["skills_to_run", "suggested_missing_skills"]
        )
        # suggested_missing_skills is free-text {name, description}, deliberately no enum.
        item = schema["properties"]["suggested_missing_skills"]["items"]
        self.assertCountEqual(item["required"], ["name", "description"])
        self.assertNotIn("enum", item["properties"]["name"])

    def test_planning_pass_sends_enum_constrained_schema_to_provider(self):
        captured: dict[str, object] = {}

        def fake_post_json(url, payload, headers):
            captured["url"] = url
            captured["payload"] = payload
            return _fake_responses_payload(
                {"skills_to_run": ["scope_check"], "suggested_missing_skills": []}
            )

        env = {"ZONE_PROVIDER": "openai", "OPENAI_API_KEY": "test-key"}
        with mock.patch.dict(os.environ, env, clear=False), mock.patch.object(
            zone, "_post_json", side_effect=fake_post_json
        ):
            zone.planning_pass("Should I switch to a payroll SaaS?", None, "balanced")

        payload = captured["payload"]
        fmt = payload["text"]["format"]
        self.assertEqual(fmt["type"], "json_schema")
        self.assertTrue(fmt["strict"])
        self.assertEqual(fmt["name"], zone.PLANNER_SCHEMA_NAME)

        enum = fmt["schema"]["properties"]["skills_to_run"]["items"]["enum"]
        self.assertEqual(enum, zone.ALLOWED_SKILLS)


class PlannerParsingTests(unittest.TestCase):
    def _run_planner(self, body: dict[str, object]):
        env = {"ZONE_PROVIDER": "openai", "OPENAI_API_KEY": "test-key"}
        with mock.patch.dict(os.environ, env, clear=False), mock.patch.object(
            zone, "_post_json", return_value=_fake_responses_payload(body)
        ):
            return zone.planning_pass("business domain choice", None, "balanced")

    def test_valid_skills_and_suggestions_are_separated(self):
        result = self._run_planner(
            {
                "skills_to_run": ["scope_check", "unit_economics", "thought_experiment"],
                "suggested_missing_skills": [
                    {
                        "name": "context_extraction",
                        "description": "Pull structured facts from the raw input first.",
                    },
                    {
                        "name": "opportunity_analysis",
                        "description": "Rank candidate domains by upside.",
                    },
                ],
            }
        )

        self.assertEqual(
            result["recommended_skills"],
            ["scope_check", "thought_experiment", "unit_economics"],
        )
        # Every executed skill is real.
        for name in result["recommended_skills"]:
            self.assertIn(name, zone.ALLOWED_SKILLS)
        # Previously-hallucinated names now live cleanly in the suggestions field.
        self.assertEqual(
            [s["name"] for s in result["suggested_missing_skills"]],
            ["context_extraction", "opportunity_analysis"],
        )
        self.assertEqual(result["discarded_planner_skills"], [])

    def test_defensive_net_catches_and_logs_a_schema_bypass(self):
        # Simulate the schema constraint failing: an invalid name lands in skills_to_run.
        # The post-hoc filter must still drop it AND emit a warning (schema failure signal).
        with self.assertLogs("api.zone", level="WARNING") as logs:
            result = self._run_planner(
                {
                    "skills_to_run": ["scope_check", "opportunity_analysis"],
                    "suggested_missing_skills": [],
                }
            )

        self.assertNotIn("opportunity_analysis", result["recommended_skills"])
        self.assertIn("opportunity_analysis", result["discarded_planner_skills"])
        self.assertTrue(
            any("survived the enum-constrained schema" in line for line in logs.output)
        )


if __name__ == "__main__":
    unittest.main()
