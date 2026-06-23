import importlib.util
import unittest
from pathlib import Path


SCRIPT = Path(__file__).parents[1] / "scripts" / "sync-spire-codex.py"
SPEC = importlib.util.spec_from_file_location("content_sync", SCRIPT)
content_sync = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
SPEC.loader.exec_module(content_sync)

CHECK_SCRIPT = Path(__file__).parents[1] / "scripts" / "check-built-content.py"
CHECK_SPEC = importlib.util.spec_from_file_location("content_check", CHECK_SCRIPT)
content_check = importlib.util.module_from_spec(CHECK_SPEC)
assert CHECK_SPEC.loader
CHECK_SPEC.loader.exec_module(content_check)


class ContentSyncTests(unittest.TestCase):
    def test_characters_use_combat_art_from_spire_codex_cdn(self):
        character = {"id": "DEFECT"}

        self.assertEqual(
            "https://cdn.spire-codex.com/characters/combat_defect.webp",
            content_sync.media_path("characters", character),
        )

    def test_non_character_media_remains_on_the_wiki_proxy(self):
        card = {"id": "BASH"}

        self.assertEqual("/media/cards/bash.webp", content_sync.media_path("cards", card))

    def test_character_validator_accepts_only_combat_cdn_images(self):
        page = content_check.PageAudit()
        page.images = [
            ({"wiki-image--character-detail"}, "https://cdn.spire-codex.com/characters/combat_defect.webp")
        ]

        self.assertEqual(1, content_check.image_count(page, "wiki-image--character-detail"))

    def test_deploy_workflow_does_not_fetch_mutable_source_data(self):
        workflow = (Path(__file__).parents[1] / ".github/workflows/deploy.yml").read_text()

        self.assertNotIn("sync-spire-codex.py --check", workflow)
        self.assertIn("python scripts/check-built-content.py", workflow)

    def test_deploy_workflow_reports_missing_cloudflare_credentials(self):
        workflow = (Path(__file__).parents[1] / ".github/workflows/deploy.yml").read_text()

        self.assertIn("Upload reproducible deployment artifact", workflow)
        self.assertIn("Report missing Cloudflare deploy credentials", workflow)
        self.assertIn("Deploy alert: Cloudflare Pages credentials are unavailable", workflow)
        self.assertIn("issues: write", workflow)


if __name__ == "__main__":
    unittest.main()
