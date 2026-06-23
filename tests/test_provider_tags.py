import importlib.util
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).parents[1] / "scripts" / "inject_provider_tags.py"
SPEC = importlib.util.spec_from_file_location("provider_tags", SCRIPT)
provider_tags = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
SPEC.loader.exec_module(provider_tags)


class ProviderTagTests(unittest.TestCase):
    def test_injects_search_console_once_and_analytics_everywhere(self):
        with tempfile.TemporaryDirectory() as directory:
            public = Path(directory)
            (public / "docs").mkdir()
            (public / "index.html").write_text("<html><head></head><body>Root</body></html>")
            (public / "docs/index.html").write_text("<html><head></head><body>Docs</body></html>")

            counts = provider_tags.configure(public, "google_token_123", "cloudflare_token_123")
            self.assertEqual((1, 2), counts)
            self.assertIn('name="google-site-verification"', (public / "index.html").read_text())
            self.assertNotIn('name="google-site-verification"', (public / "docs/index.html").read_text())
            self.assertIn("static.cloudflareinsights.com/beacon.min.js", (public / "index.html").read_text())
            self.assertIn("static.cloudflareinsights.com/beacon.min.js", (public / "docs/index.html").read_text())

            counts = provider_tags.configure(public, "google_token_123", "cloudflare_token_123")
            self.assertEqual((1, 2), counts)
            self.assertEqual(1, (public / "index.html").read_text().count("google-site-verification"))
            self.assertEqual(1, (public / "index.html").read_text().count("beacon.min.js"))

    def test_rejects_unsafe_tokens(self):
        with tempfile.TemporaryDirectory() as directory:
            public = Path(directory)
            (public / "index.html").write_text("<html><head></head><body></body></html>")
            with self.assertRaises(ValueError):
                provider_tags.configure(public, '\"><script>', None)

    def test_deploy_workflow_reports_missing_provider_setup(self):
        workflow = (Path(__file__).parents[1] / ".github/workflows/deploy.yml").read_text()

        self.assertIn("Report missing provider setup", workflow)
        self.assertIn("Provider setup: Search Console or Web Analytics is not fully configured", workflow)
        self.assertIn("GOOGLE_SITE_VERIFICATION", workflow)
        self.assertIn("CLOUDFLARE_WEB_ANALYTICS_TOKEN", workflow)


if __name__ == "__main__":
    unittest.main()
