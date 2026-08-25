from __future__ import annotations

import asyncio
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
        text = saved.read_text(encoding="utf-8")
        self.assertIn("# Rahul Shiv Shankar \u2014 Resume: product-lead", text)
        self.assertIn("Source: uploaded resume", text)
        self.assertIn("Original filename: resume.txt", text)
        self.assertIn("Product lead and AI systems builder", text)

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
