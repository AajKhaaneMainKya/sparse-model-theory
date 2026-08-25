from __future__ import annotations

import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
WEB_DIR = ROOT / "web"


class VercelPublicWebTests(unittest.TestCase):
    def test_public_web_uses_api_rewrite_and_no_localhost(self):
        public_files = [
            WEB_DIR / "index.html",
            WEB_DIR / "app.js",
            WEB_DIR / "styles.css",
            WEB_DIR / "vercel.json",
        ]
        combined = "\n".join(path.read_text(encoding="utf-8") for path in public_files)

        self.assertIn("/api/ask-rahul", combined)
        self.assertNotIn("localhost", combined)
        self.assertNotIn("127.0.0.1", combined)
        self.assertNotIn("/console", (WEB_DIR / "index.html").read_text(encoding="utf-8"))
        self.assertNotIn("/admin", (WEB_DIR / "index.html").read_text(encoding="utf-8"))

    def test_vercel_rewrites_public_api_only(self):
        config = json.loads((WEB_DIR / "vercel.json").read_text(encoding="utf-8"))
        rewrites = config["rewrites"]

        self.assertEqual(rewrites[0]["source"], "/api/:path*")
        self.assertTrue(rewrites[0]["destination"].endswith("/:path*"))
        self.assertIn("railway", rewrites[0]["destination"])
        self.assertIn({"source": "/ask", "destination": "/index.html"}, rewrites)
        self.assertNotIn("/console", json.dumps(config))
        self.assertNotIn("/admin", json.dumps(config))


if __name__ == "__main__":
    unittest.main()
