import importlib.util
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


SCRIPT = Path(__file__).parents[1] / "scripts" / "sync-r2-media.py"
SPEC = importlib.util.spec_from_file_location("media_sync", SCRIPT)
media_sync = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
SPEC.loader.exec_module(media_sync)


class MediaSyncTests(unittest.TestCase):
    def test_scan_preserves_progress_when_one_source_is_unavailable(self):
        entries = [
            {"key": "enemies/good.webp", "source_url": "https://example.test/good.webp"},
            {"key": "enemies/bad.webp", "source_url": "https://example.test/bad.webp"},
        ]

        def fake_download(entry, refresh):
            if entry["key"].endswith("bad.webp"):
                raise ValueError("Invalid WebP response")
            return {**entry, "sha256": "digest", "size": 12, "path": Path("good.webp")}

        with patch.object(media_sync, "download", side_effect=fake_download):
            scanned, unavailable = media_sync.scan_parallel(entries, workers=2, refresh=True)

        self.assertEqual(["enemies/good.webp"], [entry["key"] for entry in scanned])
        self.assertEqual(["enemies/bad.webp"], [entry["key"] for entry in unavailable])
        self.assertIn("Invalid WebP", unavailable[0]["error"])

    def test_report_calls_out_unavailable_sources(self):
        with tempfile.TemporaryDirectory() as directory:
            report = Path(directory) / "report.md"
            media_sync.write_report(
                report,
                total=2,
                changed=[],
                removed=[],
                unavailable=[
                    {
                        "key": "enemies/bad.webp",
                        "source_url": "https://example.test/bad.webp",
                        "error": "Invalid WebP response",
                    }
                ],
            )
            contents = report.read_text()

        self.assertIn("Temporarily unavailable", contents)
        self.assertIn("enemies/bad.webp", contents)
        self.assertIn("Invalid WebP response", contents)


if __name__ == "__main__":
    unittest.main()
