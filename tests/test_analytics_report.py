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


if __name__ == "__main__":
    unittest.main()
