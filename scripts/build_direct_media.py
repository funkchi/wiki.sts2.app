#!/usr/bin/env python3
"""Build first-party relic, enchantment, and event media from the game PCK."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from PIL import Image

PCK_ROOT = Path("artifacts/pck")
WIKI_ROOT = Path("data/wiki")
DEFAULT_OUT = Path("BUILT MEDIA")
DEFAULT_REPORT = Path("artifacts/generated-media/direct-media-report.json")

# Both relics select their IconBaseName dynamically. These deterministic
# posters mirror the game's no-owner/fallback states; every alternate is also
# exported under an explicit variant key below.
RELIC_POSTERS = {
    "YUMMY_COOKIE": "yummy_cookie_ironclad",
    "LOOMING_FRUIT": "looming_fruit_2",
}
RELIC_VARIANTS = {
    "YUMMY_COOKIE": {
        "yummy-cookie-ironclad": "yummy_cookie_ironclad",
        "yummy-cookie-silent": "yummy_cookie_silent",
        "yummy-cookie-defect": "yummy_cookie_defect",
        "yummy-cookie-necrobinder": "yummy_cookie_necro",
        "yummy-cookie-regent": "yummy_cookie_regent",
    },
    "LOOMING_FRUIT": {
        "looming-fruit-cornucopia": "looming_fruit",
        "looming-fruit-no-cornucopia": "looming_fruit_2",
    },
}

# 55 of 66 events resolve to images/events/<id>.png by name. The other 11 are
# scene-composited, so each is mapped to the flat background plate its
# scenes/events/background_scenes/*.tscn draws under the Spine and VFX layers
# rather than being left to a silent fallback. "_placeholder" is the shipped
# asset name for six of the Ancient plates, not an unfinished stand-in.
EVENT_SOURCES = {
    "OROBAS": "images/ancients/orobas_placeholder.webp",
    "PAEL": "images/ancients/pael_placeholder.webp",
    "NONUPEIPE": "images/ancients/nonupeipe_placeholder.webp",
    "TANX": "images/ancients/tanx_placeholder.webp",
    "VAKUU": "images/ancients/vakuu_placeholder.webp",
    "DARV": "images/ancients/darv_placeholder.webp",
    # Neow and Tezcatara are the two Ancients drawn entirely by Spine: neow.tscn
    # has a plate but the Ancient is a hole in it, and tezcatara.tscn has no
    # plate at all. Until the Phase 3 capture harness exists, both use the
    # finished map node icon, the only first-party still that shows the Ancient.
    "NEOW": "images/packed/map/ancients/ancient_node_neow.webp",
    "TEZCATARA": "images/packed/map/ancients/ancient_node_tezcatara.webp",
    "THE_ARCHITECT": "images/rooms/architect_victory/architect_victory_bg.png",
    "FAKE_MERCHANT": "images/events/custom/fake_merchant_rug.png",
    "THE_LANTERN_KEY": "_icons/card_atlas/quest/lantern_key.png",
}

# Relic and enchantment icons are small enough to ship byte-exact. Event plates
# are full-screen art (3440x1613 and up) that the wiki shows in a 220px hero and
# in link previews, so they are resampled to a link-preview width and encoded
# lossy. Sources already at or below the cap stay lossless.
EVENT_MAX_WIDTH = 1200
EVENT_QUALITY = 82
# Resampling plus lossy encoding on photographic plates; anything above this
# mean error means the encode degraded the art rather than just compressing it.
EVENT_MAX_MEAN_ERROR = 3.0


@dataclass(frozen=True)
class BuildItem:
    kind: str
    entity_id: str
    slug: str
    source_stem: str
    variant: str | None = None
    explicit_source: str | None = None

    @property
    def key(self) -> str:
        return f"{self.kind}/{self.slug}.webp"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def find_texture(kind: str, stem: str, explicit: str | None = None) -> tuple[Path | None, str]:
    if explicit is not None:
        candidate = PCK_ROOT / explicit
        return (candidate, "mapped") if candidate.exists() else (None, "missing")
    root = PCK_ROOT / "images" / kind
    for folder, resolution in ((root, "finished"), (root / "beta", "beta")):
        for suffix in (".png", ".webp"):
            candidate = folder / f"{stem}{suffix}"
            if candidate.exists():
                return candidate, resolution
    return None, "missing"


def inventory(kinds: list[str]) -> list[BuildItem]:
    items: list[BuildItem] = []
    for kind in kinds:
        payload = json.loads((WIKI_ROOT / f"{kind}.json").read_text())
        for entity in payload[kind]:
            entity_id = entity["id"]
            source_stem = (
                RELIC_POSTERS.get(entity_id, entity_id.lower())
                if kind == "relics"
                else entity_id.lower()
            )
            items.append(
                BuildItem(
                    kind,
                    entity_id,
                    entity["slug"],
                    source_stem,
                    explicit_source=(
                        EVENT_SOURCES.get(entity_id) if kind == "events" else None
                    ),
                )
            )
            if kind == "relics":
                for variant_slug, variant_stem in RELIC_VARIANTS.get(
                    entity_id, {}
                ).items():
                    items.append(
                        BuildItem(
                            kind,
                            entity_id,
                            variant_slug,
                            variant_stem,
                            variant=variant_slug,
                        )
                    )
    return sorted(items, key=lambda item: item.key)


def encode(item: BuildItem, out_root: Path) -> dict[str, object]:
    source, resolution = find_texture(item.kind, item.source_stem, item.explicit_source)
    if source is None:
        return {
            "key": item.key,
            "entityId": item.entity_id,
            "variant": item.variant,
            "resolution": resolution,
            "errors": [f"missing source texture for {item.explicit_source or item.source_stem}"],
        }

    destination = out_root / item.key
    destination.parent.mkdir(parents=True, exist_ok=True)
    with Image.open(source) as opened:
        decoded = opened.convert("RGBA")
        source_size = decoded.size
        scaled = item.kind == "events" and decoded.width > EVENT_MAX_WIDTH
        if scaled:
            height = round(decoded.height * EVENT_MAX_WIDTH / decoded.width)
            decoded = decoded.resize((EVENT_MAX_WIDTH, height), Image.LANCZOS)
        reference = np.asarray(decoded, dtype=np.int16)
        if scaled:
            decoded.save(
                destination, "WEBP", lossless=False, quality=EVENT_QUALITY, method=6
            )
        else:
            decoded.save(destination, "WEBP", lossless=True, method=6, exact=True)
        width, height = decoded.size
        alpha_bounds = decoded.getchannel("A").getbbox()

    with Image.open(destination) as built:
        output_pixels = np.asarray(built.convert("RGBA"), dtype=np.int16)
        output_size = built.size
    errors = []
    mean_error = None
    if output_size != (width, height):
        errors.append(f"dimensions changed from {(width, height)} to {output_size}")
    elif scaled:
        mean_error = float(np.abs(output_pixels - reference).mean())
        if mean_error > EVENT_MAX_MEAN_ERROR:
            errors.append(f"lossy encode mean error {mean_error:.2f} exceeds {EVENT_MAX_MEAN_ERROR}")
    elif not np.array_equal(reference, output_pixels):
        errors.append("lossless pixel comparison failed")
    if alpha_bounds is None:
        errors.append("source has no visible pixels")
    if destination.stat().st_size > 500 * 1024:
        errors.append(f"output exceeds 500 KiB: {destination.stat().st_size} bytes")

    return {
        "key": item.key,
        "entityId": item.entity_id,
        "variant": item.variant,
        "source": str(source),
        "sourceSha256": sha256(source),
        "resolution": resolution,
        "encoding": f"lossy q{EVENT_QUALITY}" if scaled else "lossless",
        "sourceWidth": source_size[0],
        "sourceHeight": source_size[1],
        "meanError": mean_error,
        "path": str(destination),
        "sha256": sha256(destination),
        "bytes": destination.stat().st_size,
        "width": width,
        "height": height,
        "alphaBounds": alpha_bounds,
        "errors": errors,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--kinds",
        nargs="+",
        choices=["relics", "enchantments", "events"],
        default=["relics", "enchantments", "events"],
    )
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    args = parser.parse_args(argv)

    if not PCK_ROOT.exists():
        parser.error("need artifacts/pck; run the extraction step first")

    items = inventory(args.kinds)
    if len(items) != len({item.key for item in items}):
        raise ValueError("direct-media inventory contains duplicate output keys")
    outputs = [encode(item, args.out) for item in items]
    errors = [
        f"{output['key']}: {error}"
        for output in outputs
        for error in output["errors"]
    ]

    expected = {args.out / item.key for item in items}
    actual = {
        path
        for kind in args.kinds
        for path in (args.out / kind).glob("*.webp")
    }
    stale = sorted(actual - expected)
    if stale:
        errors.append(f"{len(stale)} stale/unexpected outputs")

    source_modes = {}
    for kind in args.kinds:
        primary = [
            output
            for output in outputs
            if output["key"].startswith(f"{kind}/") and output["variant"] is None
        ]
        source_modes[kind] = {
            "primary": len(primary),
            "finished": sum(output["resolution"] == "finished" for output in primary),
            "beta": sum(output["resolution"] == "beta" for output in primary),
            "mapped": sum(output["resolution"] == "mapped" for output in primary),
            "missing": sum(output["resolution"] == "missing" for output in primary),
            "lossless": sum(output.get("encoding") == "lossless" for output in primary),
            "lossy": sum(
                str(output.get("encoding", "")).startswith("lossy") for output in primary
            ),
            "variants": sum(
                output["key"].startswith(f"{kind}/") and output["variant"] is not None
                for output in outputs
            ),
        }

    report = {
        "schemaVersion": 1,
        "kind": "first-party-direct-media-build",
        "rendererSha256": sha256(Path(__file__)),
        "inventory": source_modes,
        "eventPolicy": {
            "maxWidth": EVENT_MAX_WIDTH,
            "quality": EVENT_QUALITY,
            "maxMeanError": EVENT_MAX_MEAN_ERROR,
            "explicitSources": EVENT_SOURCES,
        },
        "variantPolicy": {
            "YUMMY_COOKIE": {
                "stablePoster": "yummy-cookie.webp",
                "stableState": "ironclad fallback",
                "explicitVariants": sorted(RELIC_VARIANTS["YUMMY_COOKIE"]),
            },
            "LOOMING_FRUIT": {
                "stablePoster": "looming-fruit.webp",
                "stableState": "no-cornucopia fallback",
                "explicitVariants": sorted(RELIC_VARIANTS["LOOMING_FRUIT"]),
            },
        },
        "outputs": outputs,
        "staleOutputs": [str(path) for path in stale],
        "errors": errors,
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(
        f"built and validated {len(outputs)} direct-media files; "
        f"{len(errors)} error{'s' if len(errors) != 1 else ''}; "
        f"report: {args.report}",
        file=sys.stderr,
    )
    if errors:
        for error in errors:
            print(f"error: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
