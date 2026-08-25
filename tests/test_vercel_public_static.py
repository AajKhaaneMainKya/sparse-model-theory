from __future__ import annotations

import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
PUBLIC_DIR = ROOT / "vercel_public"


class VercelPublicStaticTests(unittest.TestCase):
    def test_static_folder_contains_only_frontend_deploy_files(self):
        files = {path.relative_to(PUBLIC_DIR).as_posix() for path in PUBLIC_DIR.rglob("*") if path.is_file()}

        self.assertEqual(
            files,
            {
                "README.md",
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
        self.assertNotIn("localhost", combined)
        self.assertNotIn("127.0.0.1", combined)
        self.assertNotIn("/console", combined)
        self.assertNotIn("/admin", combined)

    def test_vercel_config_has_external_api_rewrite_only(self):
        config = json.loads((PUBLIC_DIR / "vercel.json").read_text(encoding="utf-8"))
        rewrites = config["rewrites"]

        self.assertEqual(rewrites[0]["source"], "/api/:path*")
        self.assertTrue(rewrites[0]["destination"].startswith("https://"))
        self.assertTrue(rewrites[0]["destination"].endswith("/:path*"))
        self.assertIn("railway", rewrites[0]["destination"])


if __name__ == "__main__":
    unittest.main()
