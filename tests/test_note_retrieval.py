from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from engine.note import NoteValidationError, load_notes, parse_frontmatter
from engine.retrieval import MatchTier, precedent_matches


def write_note(root: Path, name: str, title: str, body: str, anchor_type: str = "contested") -> Path:
    path = root / name
    path.write_text(
        f"""---
id: {name.removesuffix(".md")}
title: "{title}"
anchor_type: {anchor_type}
cluster: uncategorized
domain:
  - relationship
  - product
sequence:
  - "Initial signal appears in public"
  - "Attention mechanics increase pressure"
  - "Resolution quality becomes secondary"
created_at: 2026-07-27
source: "synthetic-example"
confidence: medium
---

{body}
""",
        encoding="utf-8",
    )
    return path


class NoteParsingTests(unittest.TestCase):
    def test_empty_frontmatter_raises_note_validation_error(self):
        with self.assertRaises(NoteValidationError) as exc:
            parse_frontmatter("---\n---\nBody only.\n", Path("empty-frontmatter.md"))

        self.assertIn("empty-frontmatter.md", str(exc.exception))
        self.assertIn("YAML frontmatter must be a mapping", str(exc.exception))

    def test_yaml_preserves_hash_colons_nested_lists_and_body(self):
        text = """---
id: 2026-07-27-hash-title
title: "the #1 mistake: treating syntax as intent"
anchor_type: contested
cluster: uncategorized
domain:
  - technical
  - product
sequence:
  - "Observe: quoted colon survives"
  - "Confirm # marker is literal inside quotes"
created_at: 2026-07-27
source: "synthetic-example"
confidence: high
---

First paragraph.

Second paragraph with: punctuation and # signs.
"""

        metadata, body = parse_frontmatter(text, Path("synthetic.md"))

        self.assertEqual(metadata["title"], "the #1 mistake: treating syntax as intent")
        self.assertEqual(metadata["domain"], ["technical", "product"])
        self.assertEqual(
            metadata["sequence"],
            ["Observe: quoted colon survives", "Confirm # marker is literal inside quotes"],
        )
        self.assertIn("First paragraph.", body)
        self.assertIn("Second paragraph with: punctuation and # signs.", body)


class RetrievalTests(unittest.TestCase):
    def test_semantic_vocabulary_mismatch_retrieves_structural_sibling(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_note(
                root,
                "2026-07-27-public-claim-feedback-loop.md",
                "Public claim feedback loop",
                "A named charge enters a crowded feed. Ranking machinery expands reach, "
                "spectators pile on, and the original dispute becomes harder to settle "
                "because emotional spread outruns adjudication.",
            )
            write_note(
                root,
                "2026-07-27-engagement-before-closure.md",
                "Engagement before closure",
                "A service design favors fresh reactions, repeat viewing, and visible "
                "participation. The system keeps the conflict lively while the slower work "
                "of context, repair, and closure receives little priority.",
            )

            result = precedent_matches(
                "online circulation turns a disputed allegation into escalating public pressure",
                load_notes(root),
            )

            print(
                "semantic regression scores:",
                [(match.note.id, round(match.score, 4)) for match in result.matches],
            )
            self.assertEqual(result.tier, MatchTier.STRONG_MATCH)
            self.assertEqual(result.matches[0].note.id, "2026-07-27-public-claim-feedback-loop")

    def test_unrelated_query_is_no_match_or_distinguishable_from_weak_match(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_note(
                root,
                "2026-07-27-engagement-before-closure.md",
                "Engagement before closure",
                "A service design favors fresh reactions and repeat viewing while the "
                "slower work of context and repair receives little priority.",
            )

            result = precedent_matches("solder reflow temperature drift in wafer packaging", load_notes(root))

            self.assertIn(result.tier, {MatchTier.NO_MATCH, MatchTier.WEAK_MATCH})
            self.assertNotEqual(result.tier, MatchTier.STRONG_MATCH)

    def test_weak_match_is_distinguishable_from_no_match(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_note(
                root,
                "2026-07-27-engagement-before-closure.md",
                "Engagement before closure",
                "A service design favors fresh reactions and repeat viewing while the "
                "slower work of context and repair receives little priority.",
            )

            result = precedent_matches("public attention makes judgment harder", load_notes(root))

            self.assertNotEqual(result.tier, MatchTier.NO_MATCH)
            self.assertIn(result.tier, {MatchTier.WEAK_MATCH, MatchTier.STRONG_MATCH})


if __name__ == "__main__":
    unittest.main()
