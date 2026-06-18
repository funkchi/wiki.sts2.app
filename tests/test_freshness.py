import importlib.util
import unittest
from pathlib import Path


SCRIPT = Path(__file__).parents[1] / "scripts" / "check-spire-codex-freshness.py"
SPEC = importlib.util.spec_from_file_location("freshness", SCRIPT)
freshness = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
SPEC.loader.exec_module(freshness)


def snapshot(items, stats_hash="stats"):
    collections = {endpoint: [] for endpoint in freshness.COLLECTIONS}
    collections["cards"] = items
    return {
        "collections": collections,
        "stats": {"content_sha256": stats_hash},
    }


def entity(entity_id, digest, name=None):
    return {
        "id": entity_id,
        "name": name or entity_id.title(),
        "content_sha256": digest,
        "media": [],
    }


class FreshnessDiffTests(unittest.TestCase):
    def test_unchanged_snapshot(self):
        current = snapshot([entity("A", "same")])
        diff = freshness.compare(current, current)
        self.assertFalse(diff["changed"])
        self.assertFalse(diff["entity_set_changed"])

    def test_added_removed_and_changed_entities(self):
        previous = snapshot([entity("A", "old"), entity("B", "same")])
        current = snapshot([entity("A", "new"), entity("C", "same")])
        diff = freshness.compare(previous, current)
        cards = diff["collections"]["cards"]
        self.assertTrue(diff["changed"])
        self.assertTrue(diff["entity_set_changed"])
        self.assertEqual(["C"], [item["id"] for item in cards["added"]])
        self.assertEqual(["B"], [item["id"] for item in cards["removed"]])
        self.assertEqual(["A"], [item["id"] for item in cards["changed"]])

    def test_stats_only_change(self):
        previous = snapshot([], stats_hash="old")
        current = snapshot([], stats_hash="new")
        diff = freshness.compare(previous, current)
        self.assertTrue(diff["changed"])
        self.assertTrue(diff["stats_changed"])
        self.assertFalse(diff["entity_set_changed"])


if __name__ == "__main__":
    unittest.main()
