import importlib.util
import unittest
from pathlib import Path


SCRIPT = Path(__file__).parents[1] / "scripts" / "report-analytics.py"
SPEC = importlib.util.spec_from_file_location("analytics_report", SCRIPT)
analytics_report = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
SPEC.loader.exec_module(analytics_report)


class AnalyticsReportTests(unittest.TestCase):
    def test_extracts_supported_cloudflare_shapes(self):
        rows = [{"path": "/docs/", "views": 4}]
        self.assertEqual(rows, analytics_report.extract_rows({"data": rows}))
        self.assertEqual(rows, analytics_report.extract_rows({"result": {"data": rows}}))

    def test_report_covers_every_requested_usage_view(self):
        results = {
            "popular_pages": [{"path": "/docs/cards/bash/", "views": 12}],
            "searches": [{"search_term": "bash", "searches": 3, "average_results": 2.5}],
            "empty_searches": [{"search_term": "missing", "searches": 2}],
            "navigation_paths": [
                {"source_path": "/docs/", "destination_path": "/docs/cards/", "navigations": 8}
            ],
        }
        report = analytics_report.render_report(results, "2026-06-18T00:00:00+00:00")
        for expected in ("Popular pages", "/docs/cards/bash/", "Popular searches", "Empty searches", "Navigation paths"):
            self.assertIn(expected, report)

    def test_empty_sections_are_explicit(self):
        report = analytics_report.render_report({}, "2026-06-18T00:00:00+00:00")
        self.assertEqual(4, report.count("No events in this period"))

    def test_missing_credentials_report_names_required_secrets(self):
        report = analytics_report.render_missing_credentials_report("2026-06-18T00:00:00+00:00")

        self.assertIn("Usage reporting is not active yet", report)
        self.assertIn("CLOUDFLARE_ACCOUNT_ID", report)
        self.assertIn("CLOUDFLARE_ANALYTICS_TOKEN", report)

    def test_usage_workflow_reports_missing_credentials_without_failing(self):
        workflow = (Path(__file__).parents[1] / ".github/workflows/usage-report.yml").read_text()

        self.assertIn("--allow-missing-credentials", workflow)
        self.assertIn("issues: write", workflow)
        self.assertIn("Analytics alert: Cloudflare usage reporting credentials are unavailable", workflow)


if __name__ == "__main__":
    unittest.main()
