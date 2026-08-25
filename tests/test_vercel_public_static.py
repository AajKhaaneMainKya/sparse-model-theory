from __future__ import annotations

import fnmatch
import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
PUBLIC_DIR = ROOT / "vercel_public"


class VercelPublicStaticTests(unittest.TestCase):
    def test_static_folder_contains_only_frontend_deploy_files(self):
        ignore_patterns = [
            line.strip()
            for line in (PUBLIC_DIR / ".vercelignore").read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.strip().startswith("#")
        ]
        files = {
            path.relative_to(PUBLIC_DIR).as_posix()
            for path in PUBLIC_DIR.rglob("*")
            if path.is_file()
            and (
                path.relative_to(PUBLIC_DIR).as_posix() == ".vercelignore"
                or not any(part.startswith(".") for part in path.relative_to(PUBLIC_DIR).parts)
            )
            and not any(fnmatch.fnmatch(path.relative_to(PUBLIC_DIR).as_posix(), pattern) for pattern in ignore_patterns)
        }

        self.assertEqual(
            files,
            {
                ".vercelignore",
                "README.md",
                "assets/ask-rahul-og.svg",
                "assets/favicon.svg",
                "assets/rahul.jpg",
                "assets/rahul.jpg.README.md",
                "app.js",
                "index.html",
                "styles.css",
                "vercel.json",
            },
        )

    def test_public_app_uses_api_rewrite_and_no_localhost(self):
        combined = "\n".join(
            path.read_text(encoding="utf-8")
            for path in [PUBLIC_DIR / "index.html", PUBLIC_DIR / "app.js", PUBLIC_DIR / "styles.css", PUBLIC_DIR / "vercel.json"]
        )

        self.assertIn("/api/ask-rahul", combined)
        self.assertIn("/api/thinking-window", combined)
        self.assertIn("/api/contact-request", combined)
        self.assertIn("/assets/ask-rahul-og.svg", combined)
        self.assertIn("/assets/favicon.svg", combined)
        self.assertIn("https://aksharthewriter.vercel.app/offline", combined)
        self.assertIn("https://sahayakhq.co/", combined)
        self.assertIn("rahul.jpg", combined)
        self.assertIn("/assets/rahul.jpg", combined)
        self.assertIn("localStorage", combined)
        self.assertIn("prefers-color-scheme", combined)
        self.assertIn("data-ask-output", combined)
        self.assertNotIn("localhost", combined)
        self.assertNotIn("127.0.0.1", combined)
        self.assertNotIn("/console", combined)
        self.assertNotIn("/admin", combined)
        self.assertNotIn("ADMIN_PASSWORD", combined)
        self.assertNotIn("ADMIN_TOKEN", combined)
        self.assertNotIn("notes/daily", combined)
        self.assertNotIn("OPENAI_API_KEY", combined)
        self.assertNotIn("Rahul.JPG", combined)
        self.assertNotIn("rahul.jpg.README.md\"", combined)
        self.assertNotIn("interview question", combined.lower())
        self.assertNotIn("caveat", combined.lower())
        self.assertNotIn("How is Rahul doing at his present job?", combined)

    def test_public_metadata_and_preview_identity(self):
        html = (PUBLIC_DIR / "index.html").read_text(encoding="utf-8")
        favicon = PUBLIC_DIR / "assets" / "favicon.svg"
        preview = PUBLIC_DIR / "assets" / "ask-rahul-og.svg"

        self.assertTrue(favicon.exists())
        self.assertTrue(preview.exists())
        self.assertIn("<title>Ask Rahul — Public Work Model</title>", html)
        self.assertIn('name="description"', html)
        self.assertIn("Ask evidence-backed questions", html)
        self.assertIn('property="og:title" content="Ask Rahul"', html)
        self.assertIn('property="og:description"', html)
        self.assertIn('property="og:image" content="/assets/ask-rahul-og.svg"', html)
        self.assertIn('property="og:type" content="website"', html)
        self.assertIn('name="twitter:card" content="summary_large_image"', html)
        self.assertIn('name="twitter:title" content="Ask Rahul"', html)
        self.assertIn('name="twitter:description"', html)
        self.assertIn('name="twitter:image" content="/assets/ask-rahul-og.svg"', html)
        self.assertIn('rel="icon" href="/assets/favicon.svg"', html)
        self.assertIn("Ask Rahul", preview.read_text(encoding="utf-8"))
        self.assertIn("Rahul Shiv Shankar", preview.read_text(encoding="utf-8"))
        self.assertIn("Public proof. Clear judgment.", preview.read_text(encoding="utf-8"))

        head = html.split("</head>", 1)[0]
        self.assertNotIn("/admin", head)
        self.assertNotIn("/console", head)
        self.assertNotIn("private", head.lower())

    def test_footer_has_copyright_and_employer_disclaimer(self):
        html = (PUBLIC_DIR / "index.html").read_text(encoding="utf-8")
        copyright_text = "© 2026 Rahul Shiv Shankar. All rights reserved."
        disclaimer = "Views expressed here are my own and do not represent my employer."

        self.assertIn("<footer", html)
        footer = html.split("<footer", 1)[1].split("</footer>", 1)[0]
        self.assertIn(copyright_text, footer)
        self.assertIn(disclaimer, footer)

        hero_start = html.index('class="hero-shell"')
        hero_end = html.index('id="public-proof"')
        hero = html[hero_start:hero_end]
        self.assertNotIn(copyright_text, hero)
        self.assertNotIn(disclaimer, hero)

    def test_thinking_window_uses_separate_endpoint_from_ask_rahul(self):
        app_js = (PUBLIC_DIR / "app.js").read_text(encoding="utf-8")

        self.assertIn('const ASK_RAHUL_ENDPOINT = "/api/ask-rahul"', app_js)
        self.assertIn('const THINKING_WINDOW_ENDPOINT = "/api/thinking-window"', app_js)
        self.assertIn("endpointForSurface", app_js)
        self.assertIn('surface.dataset.sourcePage === "thinking_window"', app_js)
        self.assertIn("fetch(apiPath(endpointForSurface(surface))", app_js)

    def test_thinking_window_contact_gate_is_preserved(self):
        app_js = (PUBLIC_DIR / "app.js").read_text(encoding="utf-8")
        html = (PUBLIC_DIR / "index.html").read_text(encoding="utf-8")

        self.assertIn("rahul-thinking-window-count", app_js)
        self.assertIn("incrementThinkingCount", app_js)
        self.assertIn("next >= 2", app_js)
        self.assertIn("data-soft-contact", html)

    def test_answer_surfaces_are_local_to_their_modules(self):
        html = (PUBLIC_DIR / "index.html").read_text(encoding="utf-8")

        ask_index = html.index('id="ask-rahul"')
        ask_output_index = html.index("data-ask-output", ask_index)
        proof_index = html.index('id="public-proof"')
        work_index = html.index('id="work-model"')
        self.assertLess(ask_output_index, proof_index)
        self.assertLess(ask_output_index, work_index)

        thinking_index = html.index('id="thinking-window"')
        thinking_output_index = html.index("data-ask-output", thinking_index)
        soft_contact_index = html.index("data-soft-contact", thinking_index)
        self.assertLess(thinking_output_index, soft_contact_index)

    def test_photo_references_existing_asset_and_has_fallback(self):
        html = (PUBLIC_DIR / "index.html").read_text(encoding="utf-8")

        self.assertIn('src="/assets/rahul.jpg"', html)
        self.assertTrue((PUBLIC_DIR / "assets" / "rahul.jpg").exists())
        self.assertNotIn("Rahul.JPG", html)
        self.assertNotIn("rahul.jpg.README.md", html)
        self.assertIn("data-portrait", html)
        self.assertIn("portrait-fallback", html)
        self.assertIn("portrait-missing", (PUBLIC_DIR / "app.js").read_text(encoding="utf-8"))

    def test_admin_static_js_does_not_embed_admin_secret_names(self):
        admin_js = (ROOT / "admin_ui" / "app.js").read_text(encoding="utf-8")

        self.assertNotIn("ADMIN_PASSWORD", admin_js)
        self.assertNotIn("ADMIN_TOKEN", admin_js)
        self.assertNotIn("RESEND_API_KEY", admin_js)

    def test_vercel_config_has_external_api_rewrite_only(self):
        config = json.loads((PUBLIC_DIR / "vercel.json").read_text(encoding="utf-8"))
        rewrites = config["rewrites"]

        self.assertEqual(rewrites[0]["source"], "/api/:path*")
        self.assertTrue(rewrites[0]["destination"].startswith("https://"))
        self.assertTrue(rewrites[0]["destination"].endswith("/:path*"))
        self.assertIn("railway", rewrites[0]["destination"])


if __name__ == "__main__":
    unittest.main()
