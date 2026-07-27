from pathlib import Path
import unittest

from engine.gate import route_note
from engine.note import load_notes
from engine.retrieval import MatchTier, precedent_matches


ROOT = Path(__file__).resolve().parents[1]


class GateTests(unittest.TestCase):
    def test_examples_route_by_human_anchor_type(self):
        routes = {note.id: route_note(note).path for note in load_notes(ROOT / "examples")}

        self.assertEqual(routes["2026-07-27-sahayak-shelved"], "structural-match")
        self.assertEqual(routes["2026-07-27-career-switch-pressure"], "precedent-match")
        self.assertEqual(routes["2026-07-27-pain-led-product"], "precedent-match")

    def test_contested_query_only_returns_contested_notes(self):
        notes = load_notes(ROOT / "examples")

        result = precedent_matches("job offer versus continuing to build", notes)

        self.assertIn(result.tier, {MatchTier.WEAK_MATCH, MatchTier.STRONG_MATCH})
        self.assertTrue(result.matches)
        self.assertTrue(all(match.note.anchor_type == "contested" for match in result.matches))
        self.assertEqual(result.matches[0].note.id, "2026-07-27-career-switch-pressure")


if __name__ == "__main__":
    unittest.main()
