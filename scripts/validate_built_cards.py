#!/usr/bin/env python3
"""Validate first-party card renders and emit a reproducible build report."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).parent))
from build_cards import (  # noqa: E402
    CARDS_NS,
    DEFAULT_PCK,
    INFECTION_FRAME_COUNT,
    INFECTION_FPS,
    OUTPUT_SIZE,
    PCK_ROOT,
    Card,
    compose_text,
    load_accessor_map,
    load_cards,
    upgrade,
    wither_state,
)

WIKI_CARDS = Path("data/wiki/cards.json")
RENDERER = Path(__file__).with_name("build_cards.py")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def webp_frame_durations(path: Path) -> list[int]:
    """Read ANMF durations directly; Pillow omits frame zero's duration."""
    data = path.read_bytes()
    if data[:4] != b"RIFF" or data[8:12] != b"WEBP":
        return []
    durations = []
    offset = 12
    while offset + 8 <= len(data):
        kind = data[offset : offset + 4]
        size = int.from_bytes(data[offset + 4 : offset + 8], "little")
        payload = data[offset + 8 : offset + 8 + size]
        if kind == b"ANMF" and len(payload) >= 15:
            durations.append(int.from_bytes(payload[12:15], "little"))
        offset += 8 + size + (size & 1)
    return durations


def output_path(root: Path, card: Card, stem: str) -> Path:
    return root / f"{stem}.webp"


def inspect_image(
    path: Path,
    expected_frames: int,
    expected_durations: list[int] | None = None,
    require_zero_transparent: bool = True,
) -> dict[str, object]:
    with Image.open(path) as image:
        size = image.size
        frame_count = getattr(image, "n_frames", 1)
        durations = []
        alpha_bounds = None
        for index in range(frame_count):
            image.seek(index)
            durations.append(int(image.info.get("duration", 0)))
            if index == 0:
                first_frame = image.convert("RGBA")
                alpha_bounds = first_frame.getchannel("A").getbbox()
        loop = image.info.get("loop")
    if frame_count > 1:
        durations = webp_frame_durations(path)

    errors = []
    if size != OUTPUT_SIZE:
        errors.append(f"expected {OUTPUT_SIZE[0]}x{OUTPUT_SIZE[1]}, got {size[0]}x{size[1]}")
    if frame_count != expected_frames:
        errors.append(f"expected {expected_frames} frames, got {frame_count}")
    if alpha_bounds is None:
        errors.append("first frame has no visible pixels")
    elif (
        alpha_bounds[0] <= 0
        or alpha_bounds[1] <= 0
        or alpha_bounds[2] >= size[0]
        or alpha_bounds[3] >= size[1]
    ):
        errors.append(f"visible pixels touch viewport edge: {alpha_bounds}")
    first_pixels = np.asarray(first_frame)
    transparent = first_pixels[..., 3] == 0
    if (
        require_zero_transparent
        and transparent.any()
        and np.any(first_pixels[..., :3][transparent] != 0)
    ):
        errors.append("fully transparent pixels retain non-zero RGB")
    if expected_frames > 1 and loop != 0:
        errors.append(f"expected infinite loop (0), got {loop!r}")
    if expected_durations is not None and durations != expected_durations:
        errors.append(
            f"expected frame durations {expected_durations}, got {durations}"
        )
    budget = 4 * 1024 * 1024 if expected_frames > 1 else 500 * 1024
    if path.stat().st_size > budget:
        errors.append(
            f"file exceeds {'4 MiB' if expected_frames > 1 else '500 KiB'} budget: "
            f"{path.stat().st_size} bytes"
        )
    return {
        "path": str(path),
        "bytes": path.stat().st_size,
        "sha256": sha256(path),
        "width": size[0],
        "height": size[1],
        "frames": frame_count,
        "durationsMs": durations,
        "loop": loop,
        "alphaBounds": alpha_bounds,
        "errors": errors,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cards", type=Path, default=Path("BUILT CARDS"))
    parser.add_argument(
        "--report",
        type=Path,
        default=Path("artifacts/generated-media/cards-report.json"),
    )
    parser.add_argument(
        "--skip-pck-hash",
        action="store_true",
        help="omit the expensive full PCK hash during quick local checks",
    )
    args = parser.parse_args(argv)

    strings = json.loads((PCK_ROOT / "localization/eng/cards.json").read_text())
    strings |= json.loads((PCK_ROOT / "localization/eng/gameplay_ui.json").read_text())
    keyword_strings = json.loads(
        (PCK_ROOT / "localization/eng/card_keywords.json").read_text()
    )
    cards = load_cards(strings)
    accessors = load_accessor_map()
    wiki = json.loads(WIKI_CARDS.read_text())
    wiki_ids = {item["id"] for item in wiki["cards"]}
    wiki_slugs = {item["id"]: item["slug"] for item in wiki["cards"]}

    errors: list[str] = []
    missing_models = sorted(wiki_ids - cards.keys())
    missing_wiki_art = sorted(
        card_id for card_id in wiki_ids & cards.keys() if cards[card_id].portrait is None
    )
    if missing_models:
        errors.append(f"wiki cards missing models: {', '.join(missing_models)}")
    if missing_wiki_art:
        errors.append(f"wiki cards missing portraits: {', '.join(missing_wiki_art)}")

    unresolved: list[str] = []
    for card in cards.values():
        states = [(card, False)]
        if (plus := upgrade(card, accessors)) is not None:
            states.append((plus, True))
        for state, upgraded in states:
            text = compose_text(state, keyword_strings, upgraded)
            if "{" in text or "}" in text or "???" in text:
                unresolved.append(f"{card.id}{'+' if upgraded else ''}: {text}")
    if unresolved:
        errors.append(f"{len(unresolved)} rendered descriptions retain template syntax")

    overlays = sorted(
        path.stem
        for path in CARDS_NS.glob("*.cs")
        if re.search(r"HasBuiltInOverlay\s*=>\s*true", path.read_text(errors="replace"))
    )
    portrait_overrides = sorted(
        path.stem
        for path in CARDS_NS.glob("*.cs")
        if "AllPortraitPaths" in path.read_text(errors="replace")
    )
    if overlays != ["Infection"]:
        errors.append(f"unhandled built-in overlay inventory changed: {overlays}")
    if portrait_overrides != ["MadScience", "Wither"]:
        errors.append(f"portrait-override inventory changed: {portrait_overrides}")

    outputs = []
    expected_paths: set[Path] = set()
    for card_id, card in sorted(cards.items()):
        stem = wiki_slugs.get(card_id, card_id.lower().replace("_", "-"))
        expected_frames = (
            INFECTION_FRAME_COUNT
            if card.id == "INFECTION"
            else 10 if card.rarity == "Ancient" else 1
        )
        expected_durations = (
            [67, 67, 66] * 10
            if card.id == "INFECTION"
            else [100] * 10 if card.rarity == "Ancient" else None
        )
        base = output_path(args.cards, card, stem)
        expected_paths.add(base)
        if not base.exists():
            errors.append(f"missing base render: {base}")
        else:
            result = inspect_image(
                base,
                expected_frames,
                expected_durations,
                require_zero_transparent=card.id != "INFECTION",
            )
            outputs.append({"cardId": card_id, "upgraded": False, **result})
            errors.extend(f"{base}: {error}" for error in result["errors"])

        if (plus := upgrade(card, accessors)) is not None:
            upgraded_path = output_path(args.cards, plus, f"{stem}_upg")
            expected_paths.add(upgraded_path)
            if not upgraded_path.exists():
                errors.append(f"missing upgraded render: {upgraded_path}")
            else:
                result = inspect_image(
                    upgraded_path,
                    expected_frames,
                    expected_durations,
                    require_zero_transparent=card.id != "INFECTION",
                )
                outputs.append({"cardId": card_id, "upgraded": True, **result})
                errors.extend(f"{upgraded_path}: {error}" for error in result["errors"])
        if card.id == "WITHER":
            for level, variant_stem in (
                (1, f"{stem}_upg"),
                (2, f"{stem}-level-3"),
            ):
                state = wither_state(card, level)
                variant_path = output_path(args.cards, state, variant_stem)
                expected_paths.add(variant_path)
                if not variant_path.exists():
                    errors.append(f"missing runtime variant: {variant_path}")
                else:
                    result = inspect_image(variant_path, 1)
                    outputs.append(
                        {
                            "cardId": card_id,
                            "upgraded": False,
                            "runtimeVariant": f"FakeUpgradeLevel={level}",
                            **result,
                        }
                    )
                    errors.extend(
                        f"{variant_path}: {error}" for error in result["errors"]
                    )

    actual_paths = {
        path for path in args.cards.iterdir() if path.suffix.lower() in {".png", ".webp"}
    }
    stale = sorted(actual_paths - expected_paths)
    if stale:
        errors.append(f"{len(stale)} stale/unexpected card renders")

    pck = Path(DEFAULT_PCK)
    pck_source: dict[str, object] = {
        "path": str(pck),
        "bytes": pck.stat().st_size,
    }
    if not args.skip_pck_hash:
        pck_source["sha256"] = sha256(pck)

    report = {
        "schemaVersion": 1,
        "kind": "first-party-card-build",
        "source": {
            "pck": pck_source,
            "rendererSha256": sha256(RENDERER),
            "captureViewport": {
                "width": OUTPUT_SIZE[0],
                "height": OUTPUT_SIZE[1],
            },
        },
        "inventory": {
            "models": len(cards),
            "wikiCards": len(wiki_ids),
            "upgradedRenders": sum(
                upgrade(card, accessors) is not None for card in cards.values()
            ),
            "ancient": sum(card.rarity == "Ancient" for card in cards.values()),
            "curses": sum(card.rarity == "Curse" for card in cards.values()),
            "statuses": sum(card.rarity == "Status" for card in cards.values()),
            "builtInOverlays": overlays,
            "portraitOverrides": portrait_overrides,
            "missingModels": missing_models,
            "missingWikiArt": missing_wiki_art,
            "unresolvedDescriptions": unresolved,
        },
        "runtimeVariants": {
            "WITHER": {
                "publishedPoster": "wither1",
                "upgradeToggleState": "wither2",
                "explicitFinalState": "wither3",
                "reason": "FakeUpgradeLevel is runtime state, not CardModel upgrade art",
            },
            "MAD_SCIENCE": {
                "publishedPoster": "mad_science_attack",
                "deferredExplicitStates": ["mad_science_skill", "mad_science_power"],
                "reason": "type and rider are assigned dynamically by Tinker Time",
            },
        },
        "animationPolicy": {
            "ancient": {"frames": 10, "fps": 10, "loop": 0},
            "infection": {
                "frames": INFECTION_FRAME_COUNT,
                "fps": INFECTION_FPS,
                "loop": 0,
            },
        },
        "outputs": outputs,
        "staleOutputs": [str(path) for path in stale],
        "errors": errors,
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")

    print(
        f"validated {len(outputs)} card renders; "
        f"{len(errors)} error{'s' if len(errors) != 1 else ''}; "
        f"report: {args.report}",
        file=sys.stderr,
    )
    if errors:
        for error in errors[:50]:
            print(f"error: {error}", file=sys.stderr)
        if len(errors) > 50:
            print(f"error: ... and {len(errors) - 50} more", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
