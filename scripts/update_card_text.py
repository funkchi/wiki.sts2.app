#!/usr/bin/env python3
"""Rewrite wiki card descriptions from the PCK's authoritative card templates.

The renderer in build_cards.py already expands each card's localization string
against its canonical variables; this reuses that resolver and flattens the
result to the plain text the wiki stores, for English plus both shipped
translations.

A CalculatedVar has no static value, so the resolver renders it as "X" exactly
as the game does before combat resolves it. Publishing that would replace a
real number with a placeholder, so any field whose resolution touched an
unresolved variable keeps its existing wiki text and is listed in the report.

    .venv/bin/python scripts/update_card_text.py --dry-run
    .venv/bin/python scripts/update_card_text.py
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import build_cards as bc  # noqa: E402

WIKI_CARDS = Path("data/wiki/cards.json")
DEFAULT_REPORT = Path("artifacts/generated-media/card-text-report.json")

# (PCK localization directory, wiki translations key or None for the top level)
LOCALES = [("eng", None), ("zhs", "zhHans"), ("jpn", "ja")]

# gameplay_ui.json names the resources; the icon glyphs the resolver emits are
# spelled out in wiki text, which has no sprite font.
ICON_NOUNS = {"energy": "Energy", "star": "Star"}

COLOR_TAG = re.compile(r"\[/?(?:gold|green|purple|red|blue)\]")
GLYPH = {kind: re.compile(rf"(?:\[icon:{kind}\])+") for kind in ICON_NOUNS}
COUNTED_GLYPH = {
    kind: re.compile(rf"(\d+)\[icon:{kind}\]") for kind in ICON_NOUNS
}
LEFTOVER = re.compile(r"\[[^\]]*\]")


def flatten(text: str, nouns: dict[str, str]) -> str:
    """Turn resolved card markup into the plain sentence the wiki stores."""
    text = COLOR_TAG.sub("", text)
    for kind, noun in nouns.items():
        # "0[icon:energy]" is the resolver's N-plus-one-pip form for counts
        # outside 1-3; the digit is the count, so the pip must not add another.
        text = COUNTED_GLYPH[kind].sub(rf"\1 {noun}", text)
        text = GLYPH[kind].sub(
            lambda match, noun=noun: f"{match.group(0).count('[icon:')} {noun}", text
        )
    return re.sub(r"\s+", " ", text.replace("\n", " ")).strip()


def resolve(card: bc.Card, upgraded: bool, nouns: dict[str, str]) -> tuple[str, list[str]]:
    unresolved: set[str] = set()
    text = flatten(bc.resolve_text(card, upgraded, unresolved), nouns)
    return text, sorted(unresolved)


def localized_nouns(strings: dict[str, str]) -> dict[str, str]:
    """Prefer the pack's own resource names so translations stay in-language."""
    nouns = dict(ICON_NOUNS)
    for kind, key in (("energy", "ENERGY.title"), ("star", "STAR.title")):
        if value := strings.get(key):
            nouns[kind] = value
    return nouns


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--wiki", type=Path, default=WIKI_CARDS)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    payload = json.loads(args.wiki.read_text())
    cards = payload["cards"]
    accessors = bc.load_accessor_map()

    changes: list[dict[str, object]] = []
    fallbacks: list[dict[str, object]] = []
    unknown: list[str] = []

    for lang, translation_key in LOCALES:
        strings = json.loads((bc.PCK_ROOT / f"localization/{lang}/cards.json").read_text())
        strings |= json.loads(
            (bc.PCK_ROOT / f"localization/{lang}/gameplay_ui.json").read_text()
        )
        nouns = localized_nouns(strings)
        models = bc.load_cards(strings)

        for entry in cards:
            model = models.get(entry["id"])
            if model is None:
                if translation_key is None:
                    unknown.append(entry["id"])
                continue
            target = entry if translation_key is None else entry["translations"].get(translation_key)
            if target is None:
                continue

            plus = bc.upgrade(model, accessors)
            fields = [("description", model, False)]
            if plus is not None:
                fields.append(("upgradeDescription", plus, True))

            base_text: str | None = None
            for field, source, upgraded in fields:
                text, unresolved = resolve(source, upgraded, nouns)
                if field == "description":
                    base_text = text
                elif text == base_text:
                    # The wiki stores '' when the upgrade leaves the text
                    # unchanged; the site treats that as "same as base".
                    text = ""
                current = target.get(field)
                if unresolved:
                    fallbacks.append(
                        {
                            "id": entry["id"],
                            "locale": translation_key or "en",
                            "field": field,
                            "unresolved": unresolved,
                            "rejected": text,
                            "kept": current,
                        }
                    )
                    continue
                if leftover := LEFTOVER.findall(text):
                    fallbacks.append(
                        {
                            "id": entry["id"],
                            "locale": translation_key or "en",
                            "field": field,
                            "unresolved": leftover,
                            "rejected": text,
                            "kept": current,
                        }
                    )
                    continue
                # '' is meaningful for upgradeDescription (unchanged by
                # upgrade) but never a valid replacement for a description.
                if text == current or (not text and field == "description"):
                    continue
                changes.append(
                    {
                        "id": entry["id"],
                        "locale": translation_key or "en",
                        "field": field,
                        "from": current,
                        "to": text,
                    }
                )
                target[field] = text

    report = {
        "schemaVersion": 1,
        "kind": "wiki-card-text-update",
        "locales": [key or "en" for _, key in LOCALES],
        "cards": len(cards),
        "changed": len(changes),
        "fallbacks": len(fallbacks),
        "unknownCards": sorted(set(unknown)),
        "changes": changes,
        "fallbackDetails": fallbacks,
        "dryRun": args.dry_run,
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2, ensure_ascii=False, sort_keys=True) + "\n")

    if not args.dry_run:
        args.wiki.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n")

    print(
        f"{'would change' if args.dry_run else 'changed'} {len(changes)} fields; "
        f"{len(fallbacks)} kept existing text (unresolved variables); "
        f"report: {args.report}",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
