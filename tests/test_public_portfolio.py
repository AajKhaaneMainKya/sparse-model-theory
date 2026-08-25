from pathlib import Path
import tempfile
import unittest
from unittest import mock

from api import public_portfolio
from api import server


class PublicPortfolioRetrievalTests(unittest.TestCase):
    def test_agentic_question_retrieves_sparse_and_openclaw(self):
        evidence = public_portfolio.retrieve_public_evidence("Has Rahul built agentic systems?")
        sources = {item.source for item in evidence}

        self.assertTrue(any(source.startswith("projects/sparse-model-theory.md#") for source in sources))
        self.assertTrue(any(source.startswith("projects/openclaw-demo.md#") for source in sources))

    def test_unsupported_google_claim_returns_missing_evidence(self):
        with mock.patch.object(public_portfolio, "_public_model_answer", return_value=None):
            response = public_portfolio.ask_rahul("Has Rahul worked at Google?")

        self.assertEqual(response["evidence"], [])
        self.assertIn("does not contain evidence", response["answer"])

    def test_resume_mba_deep_in_education_section_is_retrieved_and_answered(self):
        with tempfile.TemporaryDirectory() as tmp:
            public_root = Path(tmp) / "public_corpus"
            resumes = public_root / "resumes"
            resumes.mkdir(parents=True)
            long_experience = "\n".join(
                f"Experience item {index}: product systems, applied AI, and operations."
                for index in range(80)
            )
            (resumes / "ps.md").write_text(
                "# Rahul Shiv Shankar — Resume: ps\n\n"
                "## Experience\n\n"
                f"{long_experience}\n"
                "Regenesys Education Aug 2024 -- Mar 2025\n"
                "Growth Product Manager | P&L and Product Strategy\n\n"
                "## Education\n\n"
                "BITSoM (BITS Pilani School of Management), Mumbai 2021 -- 2023\n"
                "MBA, Leadership and Strategy\n"
                "Bachelor degree from another institution.\n",
                encoding="utf-8",
            )

            with mock.patch.object(public_portfolio, "PUBLIC_CORPUS_DIR", public_root), \
                    mock.patch.object(public_portfolio, "_public_model_answer", return_value=None):
                response = public_portfolio.ask_rahul("Where did Rahul complete his MBA?")

        self.assertTrue(
            "BITSoM" in response["answer"]
            or "BITS Pilani School of Management" in response["answer"]
        )
        self.assertNotIn("MBA at Regenesys", response["answer"])
        self.assertEqual(response["evidence"][0]["source"], "resumes/ps.md#Education")
        self.assertIn("BITS Pilani School of Management", response["evidence"][0]["excerpt"])

    def test_resume_education_not_in_first_500_chars_is_found(self):
        with tempfile.TemporaryDirectory() as tmp:
            public_root = Path(tmp) / "public_corpus"
            resumes = public_root / "resumes"
            resumes.mkdir(parents=True)
            prefix = " ".join(["long experience before education"] * 80)
            (resumes / "ps.md").write_text(
                "# Rahul Shiv Shankar — Resume: ps\n\n"
                f"Experience: {prefix} Regenesys Education employer experience.\n\n"
                "Education: BITSoM (BITS Pilani School of Management), Mumbai 2021 -- 2023\n"
                "MBA, Leadership and Strategy\n",
                encoding="utf-8",
            )

            with mock.patch.object(public_portfolio, "PUBLIC_CORPUS_DIR", public_root):
                evidence = public_portfolio.retrieve_public_evidence("Where did Rahul complete his MBA?")

        self.assertTrue(evidence)
        self.assertEqual(evidence[0].source, "resumes/ps.md#Education")
        self.assertIn("BITS Pilani School of Management", evidence[0].excerpt)

    def test_evidence_source_includes_section_anchor(self):
        doc = public_portfolio.PublicDocument(
            title="Rahul Shiv Shankar — Resume: ps",
            source="resumes/ps.md",
            text=public_portfolio.normalize_public_text(
                "# Rahul Shiv Shankar — Resume: ps\n\n"
                "Education: BITSoM (BITS Pilani School of Management), Mumbai 2021 -- 2023\n"
                "MBA, Leadership and Strategy"
            ),
        )

        evidence = public_portfolio.retrieve_public_evidence(
            "Where did Rahul complete his MBA?",
            documents=[doc],
        )

        self.assertEqual(evidence[0].source, "resumes/ps.md#Education")

    def test_mba_conflicting_education_chunks_returns_conflict(self):
        with tempfile.TemporaryDirectory() as tmp:
            public_root = Path(tmp) / "public_corpus"
            resumes = public_root / "resumes"
            resumes.mkdir(parents=True)
            (resumes / "ps.md").write_text(
                "# Rahul Shiv Shankar — Resume: ps\n\n"
                "## Education\n\n"
                "BITSoM (BITS Pilani School of Management), Mumbai 2021 -- 2023\n"
                "MBA, Leadership and Strategy\n",
                encoding="utf-8",
            )
            (resumes / "bad.md").write_text(
                "# Rahul Shiv Shankar — Resume: bad\n\n"
                "## Education\n\n"
                "Rahul completed his MBA at Regenesys Business School.\n",
                encoding="utf-8",
            )

            with mock.patch.object(public_portfolio, "PUBLIC_CORPUS_DIR", public_root), \
                    mock.patch.object(public_portfolio, "_public_model_answer", return_value=None):
                response = public_portfolio.ask_rahul("Where did Rahul complete his MBA?")

        self.assertIn("conflicting MBA institution", response["answer"])
        self.assertIn("BITSoM", response["answer"])
        self.assertIn("Regenesys Business School", response["answer"])

    def test_section_retrieval_test_fixture_outside_public_corpus_is_not_loaded(self):
        with tempfile.TemporaryDirectory() as tmp:
            public_root = Path(tmp) / "public_corpus"
            fixtures = Path(tmp) / "tests" / "fixtures"
            public_root.mkdir(parents=True)
            fixtures.mkdir(parents=True)
            (fixtures / "section-retrieval-test.md").write_text(
                "# Bad Fixture\n\n## Education\n\nRahul completed his MBA at Regenesys Business School.\n",
                encoding="utf-8",
            )
            (public_root / "profile.md").write_text(
                "# Public Profile\n\nRahul has public FastAPI evidence.",
                encoding="utf-8",
            )

            with mock.patch.object(public_portfolio, "PUBLIC_CORPUS_DIR", public_root), \
                    mock.patch.object(public_portfolio, "_public_model_answer", return_value=None):
                response = public_portfolio.ask_rahul("Where did Rahul complete his MBA?")

        self.assertEqual(response["evidence"], [])
        self.assertNotIn("Regenesys", response["answer"])


class AskRahulEndpointBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.public_root = Path(self.tmp.name) / "public_corpus"
        self.private_notes = Path(self.tmp.name) / "notes"
        self.daily = self.private_notes / "daily"
        self.public_root.mkdir(parents=True)
        self.daily.mkdir(parents=True)
        (self.public_root / "profile.md").write_text(
            "# Public Profile\n\nRahul has public proof of FastAPI and OpenAI-compatible model work.",
            encoding="utf-8",
        )
        (self.private_notes / "private.md").write_text(
            "# Private\n\nRahul worked at Google according to private-only notes.",
            encoding="utf-8",
        )
        (self.daily / "2026-08-19.md").write_text(
            "# Daily\n\nPrivate daily capture says Rahul worked at Google.",
            encoding="utf-8",
        )

    def tearDown(self):
        self.tmp.cleanup()

    def test_endpoint_uses_public_corpus_and_does_not_read_notes(self):
        original_read_text = Path.read_text

        def guarded_read_text(path, *args, **kwargs):
            normalized = str(path)
            if "/notes/" in normalized or normalized.endswith("/notes/private.md"):
                raise AssertionError(f"/ask-rahul read private notes path: {normalized}")
            return original_read_text(path, *args, **kwargs)

        with mock.patch.object(public_portfolio, "PUBLIC_CORPUS_DIR", self.public_root), \
                mock.patch.object(public_portfolio, "_public_model_answer", return_value=None), \
                mock.patch.object(Path, "read_text", guarded_read_text):
            response = server.ask_rahul_endpoint(
                public_portfolio.AskRahulRequest(question="Has Rahul worked at Google?")
            )

        self.assertEqual(response["evidence"], [])
        self.assertIn("does not contain evidence", response["answer"])

    def test_private_daily_answer_is_not_retrieved(self):
        original_read_text = Path.read_text

        def guarded_read_text(path, *args, **kwargs):
            normalized = str(path)
            if "/notes/" in normalized or normalized.endswith("/notes/private.md"):
                raise AssertionError(f"/ask-rahul read private notes path: {normalized}")
            return original_read_text(path, *args, **kwargs)

        with mock.patch.object(public_portfolio, "PUBLIC_CORPUS_DIR", self.public_root), \
                mock.patch.object(public_portfolio, "_public_model_answer", return_value=None), \
                mock.patch.object(Path, "read_text", guarded_read_text):
            response = public_portfolio.ask_rahul(
                "Where does the private daily capture say Rahul worked?"
            )

        self.assertEqual(response["evidence"], [])
        self.assertIn("does not contain evidence", response["answer"])


if __name__ == "__main__":
    unittest.main()
