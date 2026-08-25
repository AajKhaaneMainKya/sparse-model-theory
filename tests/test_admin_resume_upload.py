from __future__ import annotations

import asyncio
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from fastapi import HTTPException

from api import public_portfolio
from api import server


class FakeRequest:
    def __init__(self, body: bytes, content_type: str, headers: dict[str, str] | None = None):
        self._body = body
        self.headers = {"content-type": content_type}
        self.headers.update(headers or {})

    async def body(self) -> bytes:
        return self._body


def multipart_request(
    *,
    filename: str,
    content: bytes,
    content_type: str,
    label: str | None = None,
    headers: dict[str, str] | None = None,
) -> FakeRequest:
    boundary = "----resume-upload-test"
    parts: list[bytes] = []
    if label is not None:
        parts.append(
            (
                f"--{boundary}\r\n"
                'Content-Disposition: form-data; name="label"\r\n\r\n'
                f"{label}\r\n"
            ).encode("utf-8")
        )
    parts.append(
        (
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="resume"; filename="{filename}"\r\n'
            f"Content-Type: {content_type}\r\n\r\n"
        ).encode("utf-8")
        + content
        + b"\r\n"
    )
    parts.append(f"--{boundary}--\r\n".encode("utf-8"))
    return FakeRequest(
        b"".join(parts),
        f"multipart/form-data; boundary={boundary}",
        headers=headers,
    )


class AdminResumeUploadTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.public_root = Path(self.tmp.name) / "public_corpus"
        self.private_notes = Path(self.tmp.name) / "notes"
        self.daily = self.private_notes / "daily"
        self.public_root.mkdir(parents=True)
        self.daily.mkdir(parents=True)
        (self.private_notes / "private.md").write_text(
            "# Private\n\nRahul has private-only resume details.",
            encoding="utf-8",
        )
        (self.daily / "2026-08-24.md").write_text(
            "# Daily\n\nPrivate daily capture with resume notes.",
            encoding="utf-8",
        )

    def tearDown(self):
        self.tmp.cleanup()

    def test_upload_txt_resume(self):
        with mock.patch.object(public_portfolio, "PUBLIC_CORPUS_DIR", self.public_root), \
                mock.patch.dict("os.environ", {}, clear=True):
            response = asyncio.run(
                server.admin_resume_upload(
                    multipart_request(
                        filename="resume.txt",
                        content=b"Product lead and AI systems builder",
                        content_type="text/plain",
                        label="Product Lead",
                    )
                )
            )

        self.assertTrue(response["success"])
        self.assertEqual(response["source"], "resumes/product-lead.md")
        self.assertEqual(response["character_count"], len("Product lead and AI systems builder"))
        saved = self.public_root / "resumes" / "product-lead.md"
        self.assertTrue(saved.exists())
        self.assertEqual(response["facts_source"], "resumes/_facts/product-lead.json")
        self.assertTrue((self.public_root / "resumes" / "_facts" / "product-lead.json").exists())
        self.assertGreaterEqual(response["fact_count"], 1)
        self.assertIn("warnings", response)
        text = saved.read_text(encoding="utf-8")
        self.assertIn("# Rahul Shiv Shankar \u2014 Resume: product-lead", text)
        self.assertIn("Source: uploaded resume", text)
        self.assertIn("Original filename: resume.txt", text)
        self.assertIn("Product lead and AI systems builder", text)

    def test_upload_creates_structured_resume_fact_contract(self):
        resume_text = (
            "Rahul Shiv Shankar\n"
            "rshivs.1295@gmail.com | linkedin.com/in/rshivs | Mumbai, India\n\n"
            "Summary\n"
            "6+ years across deep-tech, edtech, and consulting.\n\n"
            "AI Projects and Community\n"
            "• Akshar -- Agentic content writer with 7-stage pipeline featured in GrowthX newsletter.\n"
            "• Hosted Hermes Buildathon with 100+ participants.\n\n"
            "Work Experience\n"
            "Regenesys Education Aug 2024 -- Mar 2025\n"
            "Growth Product Manager | P&L and Product Strategy\n"
            "• Owned P&L and GTM across 5+ live educational programs.\n\n"
            "Education\n"
            "BITSoM (BITS Pilani School of Management), Mumbai 2021 -- 2023\n"
            "MBA, Leadership and Strategy\n"
            "Jamia Millia Islamia, New Delhi 2013 -- 2017\n"
            "B.Tech, Electronics and Communication\n\n"
            "Skills\n"
            "Growth and GTM: P&L management, funnel analysis, GTM planning\n"
            "AI and Technical: Claude API, Redis Streams, FastAPI, Python, agentic pipelines\n"
        )
        with mock.patch.object(public_portfolio, "PUBLIC_CORPUS_DIR", self.public_root), \
                mock.patch.dict("os.environ", {}, clear=True):
            response = asyncio.run(
                server.admin_resume_upload(
                    multipart_request(
                        filename="rahul-v1.txt",
                        content=resume_text.encode("utf-8"),
                        content_type="text/plain",
                        label="Rahul V1",
                    )
                )
            )

        facts_path = self.public_root / response["facts_source"]
        payload = json.loads(facts_path.read_text(encoding="utf-8"))
        self.assertEqual(payload["schema_version"], 1)
        self.assertEqual(payload["source_resume"], "resumes/rahul-v1.md")
        categories = {fact["category"] for fact in payload["facts"]}
        expected = {
            "identity",
            "contact",
            "location",
            "links",
            "summary",
            "education",
            "work_experience",
            "projects",
            "skills",
            "tools",
            "domains",
            "achievements",
            "metrics",
            "communities",
            "dates",
            "roles",
            "organizations",
        }
        self.assertTrue(expected.issubset(categories))
        for fact in payload["facts"]:
            self.assertEqual(
                set(fact),
                {"id", "category", "value", "source_resume", "source_section", "evidence_text", "confidence"},
            )
            self.assertIn(fact["confidence"], {"high", "medium", "low"})
            self.assertEqual(fact["source_resume"], "resumes/rahul-v1.md")
        values = "\n".join(fact["value"] for fact in payload["facts"])
        self.assertIn("BITSoM", values)
        self.assertIn("Jamia Millia Islamia", values)
        self.assertIn("Regenesys Education", values)
        self.assertIn("Growth Product Manager", values)
        self.assertIn("Akshar", values)
        self.assertIn("FastAPI", values)
        self.assertIn("100+ participants", values)

    def test_upload_md_resume(self):
        with mock.patch.object(public_portfolio, "PUBLIC_CORPUS_DIR", self.public_root), \
                mock.patch.dict("os.environ", {}, clear=True):
            response = asyncio.run(
                server.admin_resume_upload(
                    multipart_request(
                        filename="resume.md",
                        content=b"## Resume\n\nFastAPI, retrieval, agentic systems",
                        content_type="text/markdown",
                    )
                )
            )

        source = response["source"]
        self.assertEqual(source, "resumes/resume.md")

    def test_upload_pdf_resume(self):
        with mock.patch.object(public_portfolio, "PUBLIC_CORPUS_DIR", self.public_root), \
                mock.patch.object(server, "extract_pdf_text", return_value="PDF extracted resume text"), \
                mock.patch.dict("os.environ", {}, clear=True):
            response = asyncio.run(
                server.admin_resume_upload(
                    multipart_request(
                        filename="Rahul Resume.pdf",
                        content=b"%PDF fake fixture",
                        content_type="application/pdf",
                    )
                )
            )

        self.assertEqual(response["source"], "resumes/rahul-resume.md")
        saved = self.public_root / "resumes" / "rahul-resume.md"
        text = saved.read_text(encoding="utf-8")
        self.assertIn("Original filename: Rahul Resume.pdf", text)
        self.assertIn("PDF extracted resume text", text)

    def test_upload_docx_resume(self):
        with mock.patch.object(public_portfolio, "PUBLIC_CORPUS_DIR", self.public_root), \
                mock.patch.object(server, "extract_docx_text", return_value="DOCX extracted resume text"), \
                mock.patch.dict("os.environ", {}, clear=True):
            response = asyncio.run(
                server.admin_resume_upload(
                    multipart_request(
                        filename="Rahul Resume.docx",
                        content=b"docx fake fixture",
                        content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                        label="DOCX Resume",
                    )
                )
            )

        self.assertEqual(response["source"], "resumes/docx-resume.md")
        saved = self.public_root / "resumes" / "docx-resume.md"
        self.assertIn("DOCX extracted resume text", saved.read_text(encoding="utf-8"))

    def test_unsafe_label_is_sanitized(self):
        with mock.patch.object(public_portfolio, "PUBLIC_CORPUS_DIR", self.public_root), \
                mock.patch.dict("os.environ", {}, clear=True):
            response = asyncio.run(
                server.admin_resume_upload(
                    multipart_request(
                        filename="resume.txt",
                        content=b"AI product resume",
                        content_type="text/plain",
                        label=" Rahul Senior/AI Resume!! ",
                    )
                )
            )

        self.assertEqual(response["source"], "resumes/rahul-senior-ai-resume.md")

    def test_duplicate_label_appends_timestamp(self):
        existing_dir = self.public_root / "resumes"
        existing_dir.mkdir(parents=True)
        (existing_dir / "product-lead.md").write_text("original", encoding="utf-8")

        fixed_now = server.datetime(2026, 8, 24, 9, 30, 5)
        upload = server.ResumeUpload(
            filename="resume.txt",
            label="Product Lead",
            text="new resume text",
        )

        with mock.patch.object(public_portfolio, "PUBLIC_CORPUS_DIR", self.public_root):
            result = server.save_resume_to_public_corpus(upload, now=fixed_now)

        self.assertEqual(result["source"], "resumes/product-lead-20260824-093005.md")
        self.assertEqual((existing_dir / "product-lead.md").read_text(encoding="utf-8"), "original")
        self.assertTrue((existing_dir / "product-lead-20260824-093005.md").exists())

    def test_temp_or_test_resume_label_is_rejected(self):
        with mock.patch.object(public_portfolio, "PUBLIC_CORPUS_DIR", self.public_root), \
                mock.patch.dict("os.environ", {}, clear=True):
            with self.assertRaises(HTTPException) as raised:
                asyncio.run(
                    server.admin_resume_upload(
                        multipart_request(
                            filename="section-retrieval-test.txt",
                            content=b"Rahul completed his MBA at Regenesys Business School.",
                            content_type="text/plain",
                            label="section-retrieval-test",
                        )
                    )
                )

        self.assertEqual(raised.exception.status_code, 400)
        self.assertFalse((self.public_root / "resumes").exists())

    def test_wrong_admin_token_fails_when_configured(self):
        with mock.patch.object(public_portfolio, "PUBLIC_CORPUS_DIR", self.public_root), \
                mock.patch.dict("os.environ", {"ADMIN_TOKEN": "correct"}, clear=True):
            with self.assertRaises(HTTPException) as raised:
                asyncio.run(
                    server.admin_resume_upload(
                        multipart_request(
                            filename="resume.txt",
                            content=b"AI product resume",
                            content_type="text/plain",
                            headers={"x-admin-token": "wrong"},
                        )
                    )
                )

        self.assertEqual(raised.exception.status_code, 401)
        self.assertFalse((self.public_root / "resumes").exists())

    def test_production_without_admin_token_blocks_upload(self):
        with mock.patch.object(public_portfolio, "PUBLIC_CORPUS_DIR", self.public_root), \
                mock.patch.dict("os.environ", {"ENV": "production"}, clear=True):
            with self.assertRaises(HTTPException) as raised:
                asyncio.run(
                    server.admin_resume_upload(
                        multipart_request(
                            filename="resume.txt",
                            content=b"AI product resume",
                            content_type="text/plain",
                        )
                    )
                )

        self.assertEqual(raised.exception.status_code, 503)
        self.assertFalse((self.public_root / "resumes").exists())

    def test_railway_without_admin_token_blocks_upload(self):
        with mock.patch.object(public_portfolio, "PUBLIC_CORPUS_DIR", self.public_root), \
                mock.patch.dict("os.environ", {"RAILWAY_ENVIRONMENT": "production"}, clear=True):
            with self.assertRaises(HTTPException) as raised:
                asyncio.run(
                    server.admin_resume_upload(
                        multipart_request(
                            filename="resume.txt",
                            content=b"AI product resume",
                            content_type="text/plain",
                        )
                    )
                )

        self.assertEqual(raised.exception.status_code, 503)
        self.assertFalse((self.public_root / "resumes").exists())

    def test_ask_rahul_can_cite_uploaded_resume_without_private_notes(self):
        upload = server.ResumeUpload(
            filename="resume.txt",
            label="AI Product",
            text="Rahul is strongest for AI product lead and agentic systems roles.",
        )
        original_read_text = Path.read_text

        def guarded_read_text(path, *args, **kwargs):
            normalized = str(path)
            if "/notes/" in normalized or normalized.endswith("/notes/private.md"):
                raise AssertionError(f"/ask-rahul read private notes path: {normalized}")
            return original_read_text(path, *args, **kwargs)

        with mock.patch.object(public_portfolio, "PUBLIC_CORPUS_DIR", self.public_root):
            server.save_resume_to_public_corpus(upload)

        with mock.patch.object(public_portfolio, "PUBLIC_CORPUS_DIR", self.public_root), \
                mock.patch.object(public_portfolio, "_public_model_answer", return_value=None), \
                mock.patch.object(Path, "read_text", guarded_read_text):
            response = public_portfolio.ask_rahul(
                "What roles is Rahul strongest for based on his resume?"
            )

        sources = {item["source"] for item in response["evidence"]}
        self.assertIn("resumes/ai-product.md#Summary", sources)


if __name__ == "__main__":
    unittest.main()
