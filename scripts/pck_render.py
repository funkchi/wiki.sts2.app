#!/usr/bin/env python3
"""Turn an extracted .pck tree into ready-to-use art: PNG sheets and sliced icons.

Runs after pck_extract.py. Godot packs most icons into atlases, so the useful
per-entity art only exists as a Rect2 region inside a shared sheet; this walks
the AtlasTexture resources and cuts them out under their real names.

Needs Pillow (for BC7/DXT and WebP decoding):
    .venv/bin/python scripts/pck_render.py --root artifacts/pck
"""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass
from pathlib import Path

from PIL import Image

RECT_RE = re.compile(r"Rect2\(\s*([-\d.]+),\s*([-\d.]+),\s*([-\d.]+),\s*([-\d.]+)\s*\)")
EXT_RES_RE = re.compile(r'\[ext_resource[^\]]*path="res://([^"]+)"')


@dataclass
class Sprite:
    sheet: str          # res:// path of the atlas sheet, minus extension
    region: tuple[int, int, int, int]
    margin: tuple[int, int, int, int] | None


def _rect(text: str, key: str) -> tuple[int, int, int, int] | None:
    match = re.search(rf"^{key} = " + RECT_RE.pattern, text, re.MULTILINE)
    if not match:
        return None
    return tuple(int(round(float(v))) for v in match.groups())  # type: ignore[return-value]


def parse_atlas_texture(path: Path) -> Sprite | None:
    text = path.read_text(errors="replace")
    if "AtlasTexture" not in text:
        return None
    sheet = EXT_RES_RE.search(text)
    region = _rect(text, "region")
    if not sheet or not region:
        return None
    return Sprite(sheet.group(1), region, _rect(text, "margin"))


class SheetCache:
    """Resolve a res:// sheet path to a decoded image, whatever it was baked as."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self._cache: dict[str, Image.Image | None] = {}

    def get(self, res_path: str) -> Image.Image | None:
        if res_path in self._cache:
            return self._cache[res_path]
        stem = self.root / Path(res_path).with_suffix("")
        image = None
        for suffix in (".webp", ".png", ".dds"):
            candidate = stem.with_suffix(suffix)
            if candidate.exists():
                image = Image.open(candidate).convert("RGBA")
                break
        self._cache[res_path] = image
        return image


def cut(sheet: Image.Image, sprite: Sprite) -> Image.Image:
    x, y, w, h = sprite.region
    piece = sheet.crop((x, y, x + w, y + h))
    if not sprite.margin:
        return piece
    # Godot trims transparent borders; margin restores the untrimmed footprint
    # so every icon in a set lines up at a consistent size.
    mx, my, mw, mh = sprite.margin
    canvas = Image.new("RGBA", (w + mw, h + mh), (0, 0, 0, 0))
    canvas.paste(piece, (mx, my))
    return canvas


def slice_atlases(root: Path, out: Path) -> tuple[int, int]:
    cache = SheetCache(root)
    written = skipped = 0
    for tres in sorted(root.rglob("*.sprites/**/*.tres")):
        sprite = parse_atlas_texture(tres)
        if sprite is None:
            skipped += 1
            continue
        sheet = cache.get(sprite.sheet)
        if sheet is None:
            skipped += 1
            continue
        # images/atlases/relic_atlas.sprites/vajra.tres -> relic_atlas/vajra.png
        parts = tres.relative_to(root).parts
        idx = next(i for i, p in enumerate(parts) if p.endswith(".sprites"))
        dest = out.joinpath(parts[idx][: -len(".sprites")], *parts[idx + 1 :]).with_suffix(".png")
        dest.parent.mkdir(parents=True, exist_ok=True)
        cut(sheet, sprite).save(dest)
        written += 1
    return written, skipped


def parse_spine_atlas(path: Path) -> tuple[str, list[tuple[str, tuple[int, int, int, int], bool]]]:
    """Return (sheet_name, [(region_name, bounds, rotated)]) for a .spatlas."""
    payload = json.loads(path.read_text(errors="replace"))
    lines = payload["atlas_data"].split("\n")
    sheet = lines[0].strip()
    regions: list[tuple[str, tuple[int, int, int, int], bool]] = []
    name: str | None = None
    bounds: tuple[int, int, int, int] | None = None
    rotated = False
    for line in lines[1:]:
        if not line.strip():
            continue
        if ":" in line:
            key, _, value = line.partition(":")
            key = key.strip()
            if key == "bounds":
                nums = [int(v) for v in value.split(",")]
                bounds = (nums[0], nums[1], nums[2], nums[3])
            elif key == "rotate":
                rotated = value.strip() in ("90", "true")
            continue
        # A bare line starts a new region; flush the previous one.
        if name and bounds:
            regions.append((name, bounds, rotated))
        name, bounds, rotated = line.strip(), None, False
    if name and bounds:
        regions.append((name, bounds, rotated))
    return sheet, regions


def slice_spine(root: Path, out: Path) -> tuple[int, int]:
    written = skipped = 0
    candidates = sorted(set(root.rglob("*.spatlas")) | set(root.rglob("*.atlas")))
    for spatlas in candidates:
        try:
            payload = json.loads(spatlas.read_text(errors="replace"))
            sheet_name, regions = parse_spine_atlas(spatlas)
        except (ValueError, KeyError, UnicodeDecodeError):
            skipped += 1
            continue
        # Prefer the recorded source directory; Path() would collapse "res://".
        source = str(payload.get("source_path", ""))
        bases = [spatlas.parent]
        if source.startswith("res://"):
            bases.insert(0, root / Path(source[len("res://") :]).parent)
        sheet_path = next(
            (
                candidate
                for base in bases
                for suffix in (".webp", ".png", ".dds")
                if (candidate := (base / sheet_name).with_suffix(suffix)).exists()
            ),
            None,
        )
        if sheet_path is None:
            skipped += 1
            continue
        sheet = Image.open(sheet_path).convert("RGBA")
        # Several atlases share a sheet filename (defect_orbs, decimillipede, ...),
        # so group by the atlas's own location to keep their parts apart.
        group = out / "spine" / spatlas.relative_to(root).with_suffix("")
        group.mkdir(parents=True, exist_ok=True)
        for name, (x, y, w, h), rotated in regions:
            if rotated:
                # bounds are the unrotated size; the page stores it turned 90° CW.
                piece = sheet.crop((x, y, x + h, y + w)).rotate(-90, expand=True)
            else:
                piece = sheet.crop((x, y, x + w, y + h))
            safe = re.sub(r"[^\w.-]+", "_", name).strip("_") or "region"
            piece.save(group / f"{safe}.png")
            written += 1
    return written, skipped


def convert_dds(root: Path, keep: bool) -> int:
    count = 0
    for dds in sorted(root.rglob("*.dds")):
        png = dds.with_suffix(".png")
        Image.open(dds).convert("RGBA").save(png)
        if not keep:
            dds.unlink()
        count += 1
    return count


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--root", type=Path, default=Path("artifacts/pck"), help="extracted pck tree")
    parser.add_argument("--out", type=Path, default=None, help="where sliced icons go (default: <root>/_icons)")
    parser.add_argument("--keep-dds", action="store_true", help="keep the .dds files after PNG conversion")
    parser.add_argument("--spine", action="store_true", help="also slice Spine atlases into body parts")
    args = parser.parse_args(argv)

    if not args.root.exists():
        parser.error(f"no extracted tree at {args.root}; run pck_extract.py first")
    out = args.out or args.root / "_icons"

    converted = convert_dds(args.root, args.keep_dds)
    print(f"converted {converted} block-compressed sheets to PNG")

    written, skipped = slice_atlases(args.root, out)
    print(f"sliced {written} atlas icons to {out}" + (f" ({skipped} skipped)" if skipped else ""))

    if args.spine:
        parts, missed = slice_spine(args.root, out)
        print(f"sliced {parts} Spine parts" + (f" ({missed} atlases skipped)" if missed else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
