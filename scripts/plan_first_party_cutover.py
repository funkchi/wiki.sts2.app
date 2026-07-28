#!/usr/bin/env python3
"""Plan a first-party media cutover without uploading or rewriting site data."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

CARDS_REPORT = Path("artifacts/generated-media/cards-report.json")
DIRECT_REPORT = Path("artifacts/generated-media/direct-media-report.json")
MEDIA_MANIFEST = Path("data/media-manifest.json")
WIKI_ROOT = Path("data/wiki")


def load(path: Path) -> dict:
    return json.loads(path.read_text())


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cards-report", type=Path, default=CARDS_REPORT)
    parser.add_argument("--direct-report", type=Path, default=DIRECT_REPORT)
    parser.add_argument("--manifest", type=Path, default=MEDIA_MANIFEST)
    parser.add_argument(
        "--out",
        type=Path,
        default=Path("artifacts/generated-media/cutover-plan.json"),
    )
    parser.add_argument(
        "--markdown",
        type=Path,
        default=Path("artifacts/generated-media/cutover-plan.md"),
    )
    args = parser.parse_args(argv)

    card_report = load(args.cards_report)
    direct_report = load(args.direct_report)
    current = load(args.manifest).get("items", {})
    errors = [
        *[f"cards: {error}" for error in card_report.get("errors", [])],
        *[f"direct: {error}" for error in direct_report.get("errors", [])],
    ]

    available: dict[str, dict] = {}
    for output in card_report["outputs"]:
        path = Path(output["path"])
        available[f"cards/{path.name}"] = output
    for output in direct_report["outputs"]:
        available[output["key"]] = output

    cards = load(WIKI_ROOT / "cards.json")["cards"]
    relics = load(WIKI_ROOT / "relics.json")["relics"]
    enchantments = load(WIKI_ROOT / "enchantments.json")["enchantments"]
    events = load(WIKI_ROOT / "events.json")["events"]
    characters = load(WIKI_ROOT / "characters.json")["characters"]
    required: set[str] = set()
    rewrites: list[dict[str, str]] = []

    for card in cards:
        base_key = f"cards/{card['slug']}.webp"
        required.add(base_key)
        expected = f"/media/{base_key}"
        if card.get("image") != expected:
            rewrites.append(
                {
                    "kind": "cards",
                    "id": card["id"],
                    "field": "image",
                    "from": card.get("image") or "",
                    "to": expected,
                }
            )
        if card.get("imageUpg"):
            upgraded_key = f"cards/{card['slug']}_upg.webp"
            required.add(upgraded_key)
            expected_upgraded = f"/media/{upgraded_key}"
            if card["imageUpg"] != expected_upgraded:
                rewrites.append(
                    {
                        "kind": "cards",
                        "id": card["id"],
                        "field": "imageUpg",
                        "from": card["imageUpg"],
                        "to": expected_upgraded,
                    }
                )

    for relic in relics:
        key = f"relics/{relic['slug']}.webp"
        required.add(key)
        expected = f"/media/{key}"
        if relic.get("image") != expected:
            rewrites.append(
                {
                    "kind": "relics",
                    "id": relic["id"],
                    "field": "image",
                    "from": relic.get("image") or "",
                    "to": expected,
                }
            )

    for enchantment in enchantments:
        key = f"enchantments/{enchantment['slug']}.webp"
        required.add(key)
        expected = f"/media/{key}"
        if enchantment.get("image") != expected:
            rewrites.append(
                {
                    "kind": "enchantments",
                    "id": enchantment["id"],
                    "field": "image",
                    "from": enchantment.get("image") or "",
                    "to": expected,
                }
            )

    for event in events:
        key = f"events/{event['slug']}.webp"
        required.add(key)
        expected = f"/media/{key}"
        if event.get("imageUrl") != expected:
            rewrites.append(
                {
                    "kind": "events",
                    "id": event["id"],
                    "field": "imageUrl",
                    "from": event.get("imageUrl") or "",
                    "to": expected,
                }
            )

    # Characters are not locally rendered: R2 already holds the five combat
    # objects, so the cutover only repoints the wiki at them.
    for character in characters:
        key = f"characters/{character['slug']}.webp"
        expected = f"/media/{key}"
        if key not in current:
            errors.append(f"characters: {key} is not in the current manifest")
        if character.get("image") != expected:
            rewrites.append(
                {
                    "kind": "characters",
                    "id": character["id"],
                    "field": "image",
                    "from": character.get("image") or "",
                    "to": expected,
                }
            )

    missing = sorted(required - available.keys())
    if missing:
        errors.append(f"{len(missing)} required first-party outputs are missing")

    # Upload all validated direct-media variants too, even though only primary
    # keys are referenced initially. Card models outside the wiki stay local.
    upload_keys = sorted(
        required
        | {
            key
            for key, output in available.items()
            if key.startswith(("relics/", "enchantments/", "events/"))
            and not output.get("errors")
        }
    )
    upload_entries = []
    for key in upload_keys:
        output = available.get(key)
        if output is None:
            continue
        upload_entries.append(
            {
                "key": key,
                "path": output["path"],
                "sha256": output["sha256"],
                "size": output["bytes"],
                "source": output.get("source"),
                "sourceSha256": output.get("sourceSha256"),
            }
        )

    changed = [
        entry
        for entry in upload_entries
        if current.get(entry["key"], {}).get("sha256") != entry["sha256"]
    ]
    unchanged = len(upload_entries) - len(changed)
    new = sum(entry["key"] not in current for entry in changed)

    plan = {
        "schemaVersion": 1,
        "kind": "first-party-media-cutover-plan",
        "requiredKeys": len(required),
        "uploadEntries": upload_entries,
        "changedEntries": changed,
        "unchangedEntries": unchanged,
        "newEntries": new,
        "rewrites": rewrites,
        "missing": missing,
        "errors": errors,
        "productionMutated": False,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(plan, indent=2, sort_keys=True) + "\n")

    by_kind = {
        kind: sum(entry["key"].startswith(f"{kind}/") for entry in upload_entries)
        for kind in ("cards", "relics", "enchantments", "events")
    }
    rewrite_kinds = {
        kind: sum(rewrite["kind"] == kind for rewrite in rewrites)
        for kind in ("cards", "relics", "enchantments", "events", "characters")
    }
    lines = [
        "# First-party media cutover plan",
        "",
        "This is a read-only plan. No R2 object or wiki dataset was changed.",
        "",
        "## Validated upload set",
        "",
        f"- Cards: **{by_kind['cards']}**",
        f"- Relics (including explicit variants): **{by_kind['relics']}**",
        f"- Enchantments: **{by_kind['enchantments']}**",
        f"- Events: **{by_kind['events']}**",
        f"- Changed versus the current manifest: **{len(changed)}** "
        f"(**{new}** new, **{unchanged}** byte-identical)",
        "",
        "## Dataset rewrites after staged-object verification",
        "",
        f"- Card fields: **{rewrite_kinds['cards']}**",
        f"- Relic fields: **{rewrite_kinds['relics']}**",
        f"- Enchantment fields: **{rewrite_kinds['enchantments']}**",
        f"- Event fields: **{rewrite_kinds['events']}**",
        f"- Character fields (existing R2 objects): **{rewrite_kinds['characters']}**",
        "",
        "## Gate",
        "",
        f"- Missing required outputs: **{len(missing)}**",
        f"- Validation errors: **{len(errors)}**",
        "- Production mutated: **no**",
    ]
    if missing:
        lines += ["", "### Missing", ""] + [f"- `{key}`" for key in missing]
    if errors:
        lines += ["", "### Errors", ""] + [f"- {error}" for error in errors]
    args.markdown.write_text("\n".join(lines) + "\n")

    print(
        f"planned {len(upload_entries)} uploads and {len(rewrites)} URL rewrites; "
        f"{len(errors)} error{'s' if len(errors) != 1 else ''}; "
        f"production unchanged",
        file=sys.stderr,
    )
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
