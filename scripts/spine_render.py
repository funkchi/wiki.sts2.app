#!/usr/bin/env python3
"""Pose and rasterise a Spine 4.2 skeleton, then export animations as WebP.

Pairs with spine_binary.py. Bones are posed from the parsed timelines, region
attachments are drawn as affine quads and meshes are rasterised per triangle
with barycentric UV interpolation.

    .venv/bin/python scripts/spine_render.py --out "BUILT ANIMATIONS"
"""

from __future__ import annotations

import argparse
import json
import math
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).parent))
from spine_binary import (  # noqa: E402
    BONE_ROTATE, BONE_SCALE, BONE_SCALEX, BONE_SCALEY, BONE_SHEAR, BONE_SHEARX,
    BONE_SHEARY, BONE_TRANSLATE, BONE_TRANSLATEX, BONE_TRANSLATEY,
    parse, read_animations_partial,
)

PCK = Path("artifacts/pck")

# The combat atlas ships a flat white stand-in for the sword trail; the real
# texture lives with the VFX assets and is warped along the swing by slash_mesh.
TEXTURE_OVERRIDES = {
    "slash/slash_placeholder": PCK / "images/vfx/characters/ironclad_slash_base.webp",
}


# --------------------------------------------------------------------------- atlas

@dataclass
class Region:
    page: int
    x: int
    y: int
    w: int          # unrotated size
    h: int
    rotate: bool
    off_x: int      # trim offset within the original image
    off_y: int
    orig_w: int
    orig_h: int


def load_atlas(path: Path) -> tuple[dict[str, Region], list[Image.Image]]:
    """Godot wraps the Spine atlas text in JSON; the body is libgdx format."""
    payload = json.loads(path.read_text(errors="replace"))
    lines = payload["atlas_data"].split("\n")
    regions: dict[str, Region] = {}
    pages: list[Image.Image] = []
    page_index = -1
    name: str | None = None
    fields: dict[str, str] = {}

    def flush() -> None:
        if name is None or "bounds" not in fields:
            return
        bx, by, bw, bh = (int(v) for v in fields["bounds"].split(","))
        rot = fields.get("rotate", "false") in ("90", "true")
        if "offsets" in fields:
            ox, oy, ow, oh = (int(v) for v in fields["offsets"].split(","))
        else:
            ox, oy, ow, oh = 0, 0, bw, bh
        regions[name] = Region(page_index, bx, by, bw, bh, rot, ox, oy, ow, oh)

    for line in lines:
        if not line.strip():
            continue
        if line.endswith(".png"):
            flush()
            name, fields = None, {}
            page_index += 1
            stem = path.parent / line[: -len(".png")]
            page = next((stem.with_suffix(ext) for ext in (".webp", ".png")
                         if stem.with_suffix(ext).exists()), None)
            pages.append(Image.open(page).convert("RGBA") if page
                         else Image.new("RGBA", (4, 4)))
            continue
        if ":" in line and not line.startswith(" "):
            key, _, value = line.partition(":")
            if key in ("size", "filter", "scale", "format", "pma", "repeat"):
                continue
            if key in ("bounds", "offsets", "rotate", "index"):
                fields[key] = value
                continue
        flush()
        name, fields = line.strip(), {}
    flush()
    return regions, pages


def region_image(region: Region, pages: list[Image.Image]) -> Image.Image:
    """Crop a region out of its page and undo the packer's 90 degree rotation."""
    page = pages[region.page]
    if region.rotate:
        box = (region.x, region.y, region.x + region.h, region.y + region.w)
        return page.crop(box).transpose(Image.ROTATE_270)
    return page.crop((region.x, region.y, region.x + region.w, region.y + region.h))


# --------------------------------------------------------------------------- posing

def _curve_value(frames: list[tuple], time: float, index: int) -> float:
    """Sample a timeline. Curves are treated as linear between keys."""
    if time <= frames[0][0]:
        return frames[0][1][index]
    if time >= frames[-1][0]:
        return frames[-1][1][index]
    for i in range(len(frames) - 1):
        t0, v0 = frames[i]
        t1, v1 = frames[i + 1]
        if t0 <= time <= t1:
            span = t1 - t0
            alpha = 0.0 if span <= 0 else (time - t0) / span
            return v0[index] + (v1[index] - v0[index]) * alpha
    return frames[-1][1][index]


def pose(skel: Any, anim: dict[str, Any], time: float) -> list[dict[str, float]]:
    """Return each bone's world matrix (a, b, c, d) and world position."""
    local = []
    for index, bone in enumerate(skel.bones):
        track = anim["bones"].get(index, {})
        rotation, x, y = bone.rotation, bone.x, bone.y
        scale_x, scale_y = bone.scale_x, bone.scale_y
        shear_x, shear_y = bone.shear_x, bone.shear_y
        if BONE_ROTATE in track:
            rotation += _curve_value(track[BONE_ROTATE], time, 0)
        if BONE_TRANSLATE in track:
            x += _curve_value(track[BONE_TRANSLATE], time, 0)
            y += _curve_value(track[BONE_TRANSLATE], time, 1)
        if BONE_TRANSLATEX in track:
            x += _curve_value(track[BONE_TRANSLATEX], time, 0)
        if BONE_TRANSLATEY in track:
            y += _curve_value(track[BONE_TRANSLATEY], time, 0)
        if BONE_SCALE in track:
            scale_x *= _curve_value(track[BONE_SCALE], time, 0)
            scale_y *= _curve_value(track[BONE_SCALE], time, 1)
        if BONE_SCALEX in track:
            scale_x *= _curve_value(track[BONE_SCALEX], time, 0)
        if BONE_SCALEY in track:
            scale_y *= _curve_value(track[BONE_SCALEY], time, 0)
        if BONE_SHEAR in track:
            shear_x += _curve_value(track[BONE_SHEAR], time, 0)
            shear_y += _curve_value(track[BONE_SHEAR], time, 1)
        if BONE_SHEARX in track:
            shear_x += _curve_value(track[BONE_SHEARX], time, 0)
        if BONE_SHEARY in track:
            shear_y += _curve_value(track[BONE_SHEARY], time, 0)
        local.append((rotation, x, y, scale_x, scale_y, shear_x, shear_y))

    world: list[dict[str, float]] = []
    for index, bone in enumerate(skel.bones):
        rotation, x, y, scale_x, scale_y, shear_x, shear_y = local[index]
        rot_y = rotation + shear_y + 90.0
        la = math.cos(math.radians(rotation + shear_x)) * scale_x
        lc = math.sin(math.radians(rotation + shear_x)) * scale_x
        lb = math.cos(math.radians(rot_y)) * scale_y
        ld = math.sin(math.radians(rot_y)) * scale_y
        if bone.parent < 0:
            world.append({"a": la, "b": lb, "c": lc, "d": ld, "x": x, "y": y})
            continue
        p = world[bone.parent]
        world.append({
            "a": p["a"] * la + p["b"] * lc,
            "b": p["a"] * lb + p["b"] * ld,
            "c": p["c"] * la + p["d"] * lc,
            "d": p["c"] * lb + p["d"] * ld,
            "x": p["a"] * x + p["b"] * y + p["x"],
            "y": p["c"] * x + p["d"] * y + p["y"],
        })
    return world


def active_attachment(skel: Any, anim: dict[str, Any], slot_index: int, time: float) -> str | None:
    track = anim["slots"].get(slot_index, {}).get("attachment")
    if not track:
        return skel.slots[slot_index].attachment
    current = skel.slots[slot_index].attachment
    for frame_time, name in track:
        if frame_time <= time:
            current = name
        else:
            break
    return current


# --------------------------------------------------------------------------- raster

def draw_triangles(target: np.ndarray, verts: np.ndarray, uvs: np.ndarray,
                   tris: list[int], texture: np.ndarray, additive: bool = False) -> None:
    """Rasterise UV-mapped triangles with barycentric interpolation."""
    height, width = target.shape[:2]
    tex_h, tex_w = texture.shape[:2]
    for i in range(0, len(tris), 3):
        idx = tris[i : i + 3]
        p = verts[idx]
        x0, y0 = np.floor(p[:, 0].min()), np.floor(p[:, 1].min())
        x1, y1 = np.ceil(p[:, 0].max()), np.ceil(p[:, 1].max())
        x0, y0 = max(int(x0), 0), max(int(y0), 0)
        x1, y1 = min(int(x1) + 1, width), min(int(y1) + 1, height)
        if x1 <= x0 or y1 <= y0:
            continue
        ys, xs = np.mgrid[y0:y1, x0:x1]
        px, py = xs + 0.5, ys + 0.5
        (ax, ay), (bx, by), (cx, cy) = p
        denom = (by - cy) * (ax - cx) + (cx - bx) * (ay - cy)
        if abs(denom) < 1e-9:
            continue
        w0 = ((by - cy) * (px - cx) + (cx - bx) * (py - cy)) / denom
        w1 = ((cy - ay) * (px - cx) + (ax - cx) * (py - cy)) / denom
        w2 = 1.0 - w0 - w1
        inside = (w0 >= 0) & (w1 >= 0) & (w2 >= 0)
        if not inside.any():
            continue
        uv = uvs[idx]
        u = w0 * uv[0, 0] + w1 * uv[1, 0] + w2 * uv[2, 0]
        v = w0 * uv[0, 1] + w1 * uv[1, 1] + w2 * uv[2, 1]
        sx = np.clip((u * tex_w).astype(int), 0, tex_w - 1)
        sy = np.clip((v * tex_h).astype(int), 0, tex_h - 1)
        src = texture[sy, sx]
        alpha = (src[..., 3:4].astype(np.float32) / 255.0) * inside[..., None]
        region = target[y0:y1, x0:x1].astype(np.float32)
        if additive:
            # Glow textures are authored white-on-black at full opacity, so the
            # coverage has to come from luminance: black adds nothing, white
            # adds a bright trail. Using the source alpha would paint the dark
            # part of the gradient as solid black.
            lum = src[..., :3].astype(np.float32).max(axis=-1, keepdims=True) / 255.0
            out = np.clip(region + src.astype(np.float32) * alpha * lum, 0, 255)
            out[..., 3] = np.clip(region[..., 3] + 255.0 * lum[..., 0] * alpha[..., 0], 0, 255)
        else:
            out = src.astype(np.float32) * alpha + region * (1 - alpha)
        target[y0:y1, x0:x1] = out.astype(np.uint8)


def render_frame(skel: Any, anim: dict[str, Any], time: float, regions: dict[str, Region],
                 pages: list[Image.Image], view: tuple[float, float, float, float],
                 size: tuple[int, int], cache: dict) -> Image.Image:
    world = pose(skel, anim, time)
    min_x, min_y, span_x, span_y = view
    out_w, out_h = size
    target = np.zeros((out_h, out_w, 4), dtype=np.uint8)
    skin = skel.skins.get("default", {})

    def to_screen(points: np.ndarray) -> np.ndarray:
        sx = (points[:, 0] - min_x) / span_x * out_w
        sy = out_h - (points[:, 1] - min_y) / span_y * out_h
        return np.stack([sx, sy], axis=1)

    for slot_index, slot in enumerate(skel.slots):
        name = active_attachment(skel, anim, slot_index, time)
        if not name:
            continue
        att = skin.get(slot_index, {}).get(name)
        if att is None or att["type"] not in ("region", "mesh"):
            continue
        path = att.get("path") or name
        region = regions.get(path)
        if region is None:
            continue
        if path not in cache:
            override = TEXTURE_OVERRIDES.get(path)
            cache[path] = np.asarray(
                Image.open(override).convert("RGBA") if override and override.exists()
                else region_image(region, pages))
        texture = cache[path]
        additive = slot.blend == "additive" or path in TEXTURE_OVERRIDES
        bone = world[slot.bone]

        if att["type"] == "region":
            full_w = att["width"] * att["scale_x"]
            full_h = att["height"] * att["scale_y"]
            # The packer trims transparent borders, so the cropped image covers
            # only a sub-rect of the attachment quad. offsets are from the
            # bottom-left of the original, untrimmed image.
            u0 = region.off_x / region.orig_w
            u1 = (region.off_x + region.w) / region.orig_w
            v0 = region.off_y / region.orig_h
            v1 = (region.off_y + region.h) / region.orig_h
            x_lo, x_hi = (u0 - 0.5) * full_w, (u1 - 0.5) * full_w
            y_lo, y_hi = (v0 - 0.5) * full_h, (v1 - 0.5) * full_h
            cos_r = math.cos(math.radians(att["rotation"]))
            sin_r = math.sin(math.radians(att["rotation"]))
            corners = []
            for lx, ly in ((x_lo, y_lo), (x_hi, y_lo), (x_hi, y_hi), (x_lo, y_hi)):
                rx = lx * cos_r - ly * sin_r + att["x"]
                ry = lx * sin_r + ly * cos_r + att["y"]
                corners.append((rx * bone["a"] + ry * bone["b"] + bone["x"],
                                rx * bone["c"] + ry * bone["d"] + bone["y"]))
            verts = to_screen(np.array(corners, dtype=np.float64))
            uvs = np.array([[0, 1], [1, 1], [1, 0], [0, 0]], dtype=np.float64)
            draw_triangles(target, verts, uvs, [0, 1, 2, 0, 2, 3], texture, additive)
            continue

        data = att["vertices"]
        points = []
        if data["weighted"]:
            for entry in data["vertices"]:
                wx = wy = 0.0
                for bone_index, vx, vy, weight in entry:
                    wb = world[bone_index]
                    wx += (vx * wb["a"] + vy * wb["b"] + wb["x"]) * weight
                    wy += (vx * wb["c"] + vy * wb["d"] + wb["y"]) * weight
                points.append((wx, wy))
        else:
            flat = data["vertices"]
            for i in range(0, len(flat), 2):
                vx, vy = flat[i], flat[i + 1]
                points.append((vx * bone["a"] + vy * bone["b"] + bone["x"],
                               vx * bone["c"] + vy * bone["d"] + bone["y"]))
        verts = to_screen(np.array(points, dtype=np.float64))
        raw_uv = np.array(att["uvs"], dtype=np.float64).reshape(-1, 2)
        draw_triangles(target, verts, raw_uv, att["triangles"], texture, additive)

    return Image.fromarray(target, "RGBA")


# Sweeping VFX overlays reach far beyond the body; framing to them would leave
# the character tiny, so they are ignored when measuring (and may crop).
VFX_ATTACHMENTS = ("slash", "zaps", "shine", "trail")


def measure_bounds(skel: Any, animations: dict[str, Any], regions: dict[str, Region],
                   fps: int, pad: float = 0.08) -> tuple[float, float, float, float]:
    """Union of every posed body attachment corner across all animations."""
    skin = skel.skins.get("default", {})
    lo_x = lo_y = float("inf")
    hi_x = hi_y = float("-inf")
    for anim in animations.values():
        steps = max(2, int(anim["duration"] * fps))
        for step in range(steps):
            time = step / fps
            world = pose(skel, anim, time)
            for slot_index, slot in enumerate(skel.slots):
                name = active_attachment(skel, anim, slot_index, time)
                att = skin.get(slot_index, {}).get(name) if name else None
                if att is None or att["type"] not in ("region", "mesh"):
                    continue
                if (att.get("path") or name) not in regions:
                    continue
                bone = world[slot.bone]
                if att["type"] == "region":
                    hw = att["width"] * att["scale_x"] / 2
                    hh = att["height"] * att["scale_y"] / 2
                    pts = [(-hw, -hh), (hw, -hh), (hw, hh), (-hw, hh)]
                    cos_r = math.cos(math.radians(att["rotation"]))
                    sin_r = math.sin(math.radians(att["rotation"]))
                    pts = [(px * cos_r - py * sin_r + att["x"],
                            px * sin_r + py * cos_r + att["y"]) for px, py in pts]
                    coords = [(px * bone["a"] + py * bone["b"] + bone["x"],
                               px * bone["c"] + py * bone["d"] + bone["y"]) for px, py in pts]
                else:
                    data = att["vertices"]
                    coords = []
                    if data["weighted"]:
                        for entry in data["vertices"]:
                            wx = wy = 0.0
                            for bi, vx, vy, weight in entry:
                                wb = world[bi]
                                wx += (vx * wb["a"] + vy * wb["b"] + wb["x"]) * weight
                                wy += (vx * wb["c"] + vy * wb["d"] + wb["y"]) * weight
                            coords.append((wx, wy))
                    else:
                        flat = data["vertices"]
                        for i in range(0, len(flat), 2):
                            vx, vy = flat[i], flat[i + 1]
                            coords.append((vx * bone["a"] + vy * bone["b"] + bone["x"],
                                           vx * bone["c"] + vy * bone["d"] + bone["y"]))
                for cx, cy in coords:
                    lo_x, hi_x = min(lo_x, cx), max(hi_x, cx)
                    lo_y, hi_y = min(lo_y, cy), max(hi_y, cy)
    span_x, span_y = hi_x - lo_x, hi_y - lo_y
    return (lo_x - span_x * pad, lo_y - span_y * pad,
            span_x * (1 + 2 * pad), span_y * (1 + 2 * pad))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--character", action="append", default=[],
                        help="character folder name; defaults to all five")
    parser.add_argument("--out", type=Path, default=Path("BUILT ANIMATIONS"))
    parser.add_argument("--height", type=int, default=420)
    parser.add_argument("--fps", type=int, default=30)
    parser.add_argument("--only", action="append", default=[])
    parser.add_argument("--max-seconds", type=float, default=0.0,
                        help="trim long loops at their closest repeat point")
    parser.add_argument("--supersample", type=int, default=2,
                        help="render at NxN then downsample to antialias")
    parser.add_argument("--exclude", action="append", default=[],
                        help="animation names to skip")
    parser.add_argument("--frame-on", default="idle_loop",
                        help="animation whose extent sets the shared viewport")
    args = parser.parse_args(argv)

    characters = args.character or sorted(
        p.name for p in (PCK / "animations/characters").iterdir() if p.is_dir())
    args.out.mkdir(parents=True, exist_ok=True)
    for character in characters:
        render_character(character, args)
    return 0


def trim_to_loop(frames: list[Image.Image], fps: int, max_seconds: float) -> list[Image.Image]:
    """Cut a long ambient loop where it most closely returns to its first frame.

    Truncating at an arbitrary time makes the loop visibly jump; scoring each
    candidate against frame 0 finds a cut the eye reads as seamless.
    """
    limit = min(len(frames), int(max_seconds * fps))
    earliest = max(2, int(fps * 0.75))
    if limit <= earliest:
        return frames[:limit] or frames[:1]
    small = [np.asarray(f.resize((48, 64), Image.BILINEAR), dtype=np.float32) for f in frames]
    first = small[0]
    best, best_score = limit, float("inf")
    for k in range(earliest, limit):
        score = float(np.abs(small[k] - first).mean())
        if score < best_score:
            best, best_score = k, score
    return frames[:best]


def render_character(character: str, args) -> None:
    base = PCK / f"animations/characters/{character}/{character}"
    skel_file = next((p for p in Path("/tmp/skels").rglob("*.spskel")
                      if p.name.startswith(f"{character}.skel-")), None)
    if skel_file is None:
        print(f"  {character}: no skeleton extracted, skipping", file=sys.stderr)
        return
    data = skel_file.read_bytes()
    skel = parse(data)
    animations = read_animations_partial(data, skel)
    regions, pages = load_atlas(base.with_suffix(".atlas"))

    # The setup-pose bounds do not cover lunges, so measure the real extent
    # across every animation and share one viewport so the character keeps a
    # consistent size between clips.
    # Frame on the idle pose: other clips (die, lunges) throw the union box far
    # wider than the body, which would leave the character tiny.
    # One shared pixels-per-unit derived from the idle pose, then a per-clip
    # canvas. A single union viewport would have to contain the death fall,
    # which shrinks the character; this keeps him the same size everywhere and
    # still guarantees nothing is clipped.
    reference = {k: v for k, v in animations.items() if k == args.frame_on} or animations
    _, _, _, ref_span_y = measure_bounds(skel, reference, regions, args.fps, pad=0.06)
    ppu = args.height / ref_span_y

    cache: dict[str, Any] = {}
    for name, anim in animations.items():
        if args.only and name not in args.only:
            continue
        if name in args.exclude:
            continue
        view = measure_bounds(skel, {name: anim}, regions, args.fps, pad=0.06)
        out_w = max(2, int(round(view[2] * ppu)))
        out_h = max(2, int(round(view[3] * ppu)))
        duration = max(anim["duration"], 1.0 / args.fps)
        frame_count = max(1, int(round(duration * args.fps)))
        ss = args.supersample
        frames: list[Image.Image] = []
        for i in range(frame_count):
            big = render_frame(skel, anim, i / args.fps, regions, pages, view,
                               (out_w * ss, out_h * ss), cache)
            frames.append(big.resize((out_w, out_h), Image.LANCZOS) if ss > 1 else big)
        if args.max_seconds and duration > args.max_seconds:
            frames = trim_to_loop(frames, args.fps, args.max_seconds)
            frame_count = len(frames)
        dest = args.out / f"{character}_{name}.webp"
        frames[0].save(dest, save_all=True, append_images=frames[1:],
                       duration=int(1000 / args.fps), loop=0, quality=88, method=4)
        print(f"  {character}/{name:12} {frame_count:3} frames {out_w}x{out_h} "
              f"-> {dest.name}", file=sys.stderr)


if __name__ == "__main__":
    raise SystemExit(main())
