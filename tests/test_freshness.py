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
        report = freshness.render_report(diff)
        self.assertIn("### Added", report)
        self.assertIn("**C** (`C`)", report)
        self.assertIn("### Removed", report)
        self.assertIn("**B** (`B`)", report)

    def test_stats_only_change(self):
        previous = snapshot([], stats_hash="old")
        current = snapshot([], stats_hash="new")
        diff = freshness.compare(previous, current)
        self.assertTrue(diff["changed"])
        self.assertTrue(diff["stats_changed"])
        self.assertFalse(diff["entity_set_changed"])

    def test_workflow_has_deduplicated_entity_alert(self):
        workflow = (Path(__file__).parents[1] / ".github/workflows/freshness.yml").read_text()
        self.assertIn("issues: write", workflow)
        self.assertIn("steps.source.outputs.entity_set_changed == 'true'", workflow)
        self.assertIn("gh issue list --state open", workflow)
        self.assertIn("gh issue comment", workflow)
        self.assertIn("gh issue create", workflow)

    def test_workflow_keeps_data_branch_when_actions_cannot_open_pr(self):
        workflow = (Path(__file__).parents[1] / ".github/workflows/freshness.yml").read_text()
        self.assertIn("Publish data update branch", workflow)
        self.assertIn("Data update branch requires manual PR", workflow)
        self.assertIn("could not create the pull request automatically", workflow)
        self.assertIn("compare/main...", workflow)


if __name__ == "__main__":
    unittest.main()
