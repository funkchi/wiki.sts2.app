import importlib.util
import json
import unittest
from pathlib import Path


ROOT = Path(__file__).parents[1]
SCRIPT = ROOT / "scripts" / "export-entities-json.py"
SPEC = importlib.util.spec_from_file_location("entity_export", SCRIPT)
entity_export = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
SPEC.loader.exec_module(entity_export)


class CardCostTests(unittest.TestCase):
    def test_cost_label_prefers_x_flags_before_unplayable_costs(self):
        self.assertEqual("X", entity_export._cost_label({"cost": -1, "is_x_cost": True}))
        self.assertEqual("X★", entity_export._cost_label({"cost": 0, "is_x_star_cost": True}))
        self.assertEqual("Unplayable", entity_export._cost_label({"cost": -1}))
        self.assertEqual("2/7★", entity_export._cost_label({"cost": 2, "star_cost": 7}))

    def test_exported_card_cost_edge_cases_are_normalized(self):
        cards = json.loads((ROOT / "data/wiki/cards.json").read_text())["cards"]
        by_slug = {card["slug"]: card for card in cards}

        self.assertEqual("X", by_slug["cascade"]["cost"])
        self.assertTrue(by_slug["cascade"]["costRaw"]["isX"])
        self.assertEqual(-1, by_slug["cascade"]["costRaw"]["cost"])

        self.assertEqual("X★", by_slug["stardust"]["cost"])
        self.assertTrue(by_slug["stardust"]["costRaw"]["isXStar"])

        self.assertEqual("Unplayable", by_slug["ascenders-bane"]["cost"])
        self.assertEqual("2/7★", by_slug["seven-stars"]["cost"])
        self.assertEqual(1, by_slug["seven-stars"]["upgradeCost"])


if __name__ == "__main__":
    unittest.main()
