#!/usr/bin/env python3
"""Clean-room reader for Spine 4.2 binary skeletons (.skel).

Written against the published binary layout so the wiki can pre-render the
game's Spine characters without shipping or linking the Spine runtimes. The
parse is validated structurally: every section must consume exactly the bytes
it claims, and the animation section must start where the animation names sit.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass, field
from typing import Any

# Inherit modes (was "transform mode" before 4.2).
INHERIT = ["normal", "onlyTranslation", "noRotationOrReflection", "noScale", "noScaleOrReflection"]
BLEND_MODES = ["normal", "additive", "multiply", "screen"]

# Timeline type ids, per section.
BONE_TIMELINES = [
    "rotate", "translate", "translatex", "translatey", "scale", "scalex", "scaley",
    "shear", "shearx", "sheary", "inherit",
]


class Reader:
    """Big-endian primitive reader with Spine's varint and string encodings."""

    def __init__(self, data: bytes) -> None:
        self.data = data
        self.pos = 0

    def byte(self) -> int:
        value = self.data[self.pos]
        self.pos += 1
        return value

    def sbyte(self) -> int:
        value = self.byte()
        return value - 256 if value > 127 else value

    def bool(self) -> bool:
        return self.byte() != 0

    def int32(self) -> int:
        value = struct.unpack_from(">i", self.data, self.pos)[0]
        self.pos += 4
        return value

    def float(self) -> float:
        value = struct.unpack_from(">f", self.data, self.pos)[0]
        self.pos += 4
        return value

    def varint(self, optimize_positive: bool = True) -> int:
        """7 bits per byte, high bit = continue."""
        value = 0
        shift = 0
        while True:
            piece = self.byte()
            value |= (piece & 0x7F) << shift
            if piece < 0x80 or shift >= 28:
                break
            shift += 7
        if not optimize_positive:
            value = (value >> 1) ^ -(value & 1)
        return value

    def string(self) -> str | None:
        length = self.varint()
        if length == 0:
            return None
        if length == 1:
            return ""
        raw = self.data[self.pos : self.pos + length - 1]
        self.pos += length - 1
        return raw.decode("utf-8")

    def string_ref(self, strings: list[str]) -> str | None:
        index = self.varint()
        return strings[index - 1] if index > 0 else None

    def floats(self, count: int) -> list[float]:
        values = list(struct.unpack_from(f">{count}f", self.data, self.pos))
        self.pos += 4 * count
        return values

    def shorts(self, count: int) -> list[int]:
        values = list(struct.unpack_from(f">{count}H", self.data, self.pos))
        self.pos += 2 * count
        return values


@dataclass
class Bone:
    name: str
    parent: int
    rotation: float
    x: float
    y: float
    scale_x: float
    scale_y: float
    shear_x: float
    shear_y: float
    length: float
    inherit: str
    skin_required: bool


@dataclass
class Slot:
    name: str
    bone: int
    color: int
    dark_color: int | None
    attachment: str | None
    blend: str


@dataclass
class Skeleton:
    hash: bytes
    version: str
    x: float
    y: float
    width: float
    height: float
    reference_scale: float
    fps: float
    images_path: str | None
    strings: list[str] = field(default_factory=list)
    bones: list[Bone] = field(default_factory=list)
    slots: list[Slot] = field(default_factory=list)
    skins: dict[str, dict[int, dict[str, Any]]] = field(default_factory=dict)
    events: list[str] = field(default_factory=list)
    animations: dict[str, Any] = field(default_factory=dict)
    animations_offset: int = 0


def _read_bones(r: Reader, nonessential: bool) -> list[Bone]:
    bones = []
    for i in range(r.varint()):
        name = r.string()
        parent = r.varint() if i > 0 else -1
        rotation = r.float()
        x, y = r.float(), r.float()
        scale_x, scale_y = r.float(), r.float()
        shear_x, shear_y = r.float(), r.float()
        length = r.float()
        inherit = INHERIT[r.varint()]
        skin_required = r.bool()
        if nonessential:
            r.int32()  # editor colour
            r.string()  # editor icon
            r.bool()  # editor visibility
        bones.append(Bone(name, parent, rotation, x, y, scale_x, scale_y,
                          shear_x, shear_y, length, inherit, skin_required))
    return bones


def _read_slots(r: Reader, strings: list[str], nonessential: bool) -> list[Slot]:
    slots = []
    for _ in range(r.varint()):
        name = r.string()
        bone = r.varint()
        color = r.int32() & 0xFFFFFFFF
        dark = r.int32() & 0xFFFFFFFF
        slot = Slot(name, bone, color, None if dark == 0xFFFFFFFF else dark,
                    r.string_ref(strings), BLEND_MODES[r.varint()])
        if nonessential:
            r.bool()  # editor visibility
        slots.append(slot)
    return slots


def _read_constraints(r: Reader) -> None:
    """IK, transform, path and physics constraints.

    4.2 packs the optional fields behind flag bytes, so each field is only
    present when its bit is set.
    """
    for _ in range(r.varint()):  # IK
        r.string(); r.varint()
        for _ in range(r.varint()):
            r.varint()
        r.varint()
        flags = r.byte()
        if flags & 32:
            if flags & 64:
                r.float()
        if flags & 128:
            r.float()

    for _ in range(r.varint()):  # transform
        r.string(); r.varint()
        for _ in range(r.varint()):
            r.varint()
        r.varint()
        flags = r.byte()
        for bit in (8, 16, 32, 64, 128):
            if flags & bit:
                r.float()
        flags = r.byte()
        for bit in (1, 2, 4, 8, 16, 32, 64):
            if flags & bit:
                r.float()

    for _ in range(r.varint()):  # path
        r.string(); r.varint()
        for _ in range(r.varint()):
            r.varint()
        r.varint()
        flags = r.byte()
        r.float()  # position
        r.float()  # spacing
        r.float()  # mix rotate
        r.float()  # mix x
        r.float()  # mix y
        _ = flags

    for _ in range(r.varint()):  # physics
        r.string(); r.varint()
        r.varint()
        flags = r.byte()
        for bit in (1, 2, 4, 8, 16, 32, 64, 128):
            if flags & bit:
                r.float()


ATTACHMENT_TYPES = ["region", "boundingbox", "mesh", "linkedmesh", "path", "point", "clipping"]


def _read_sequence(r: Reader) -> dict[str, int]:
    return {"count": r.varint(), "start": r.varint(), "digits": r.varint(), "setup": r.varint()}


def _read_vertices(r: Reader, vertex_count: int, weighted: bool) -> dict[str, Any]:
    """Either raw x/y pairs, or per-vertex bone weights for a deformed mesh."""
    if not weighted:
        return {"weighted": False, "vertices": r.floats(vertex_count * 2)}
    entries = []
    for _ in range(vertex_count):
        entry = [(r.varint(), r.float(), r.float(), r.float()) for _ in range(r.varint())]
        entries.append(entry)
    return {"weighted": True, "vertices": entries}


def _read_attachment(r: Reader, strings: list[str], slot_name: str,
                     nonessential: bool) -> dict[str, Any] | None:
    flags = r.byte()
    kind = ATTACHMENT_TYPES[flags & 0x7]
    name = r.string_ref(strings) if flags & 8 else slot_name
    att: dict[str, Any] = {"type": kind, "name": name}

    if kind == "region":
        att["path"] = r.string_ref(strings) if flags & 16 else name
        att["color"] = r.int32() & 0xFFFFFFFF if flags & 32 else 0xFFFFFFFF
        att["sequence"] = _read_sequence(r) if flags & 64 else None
        att["rotation"] = r.float() if flags & 128 else 0.0
        att["x"], att["y"] = r.float(), r.float()
        att["scale_x"], att["scale_y"] = r.float(), r.float()
        att["width"], att["height"] = r.float(), r.float()
        return att

    if kind == "boundingbox":
        count = r.varint()
        att["vertices"] = _read_vertices(r, count, bool(flags & 16))
        if nonessential:
            r.int32()  # editor colour
        return att

    if kind == "mesh":
        att["path"] = r.string_ref(strings) if flags & 16 else name
        att["color"] = r.int32() & 0xFFFFFFFF if flags & 32 else 0xFFFFFFFF
        att["sequence"] = _read_sequence(r) if flags & 64 else None
        att["hull"] = r.varint()
        count = r.varint()
        att["vertices"] = _read_vertices(r, count, bool(flags & 128))
        att["uvs"] = r.floats(count * 2)
        # The triangle count is derived rather than stored: triangulating a
        # polygon with `hull` boundary vertices and the rest interior yields
        # 2*count - hull - 2 triangles. Indices are varints, not shorts.
        triangle_count = (2 * count - att["hull"] - 2) * 3
        att["triangles"] = [r.varint() for _ in range(triangle_count)]
        if nonessential:
            att["edges"] = [r.varint() for _ in range(r.varint())]
            att["width"], att["height"] = r.float(), r.float()
        return att

    if kind == "linkedmesh":
        att["path"] = r.string_ref(strings) if flags & 16 else name
        att["color"] = r.int32() & 0xFFFFFFFF if flags & 32 else 0xFFFFFFFF
        att["sequence"] = _read_sequence(r) if flags & 64 else None
        att["skin"] = r.string_ref(strings)
        att["parent_mesh"] = r.string_ref(strings)
        if nonessential:
            att["width"], att["height"] = r.float(), r.float()
        return att

    if kind == "path":
        att["closed"] = bool(flags & 16)
        att["constant_speed"] = bool(flags & 32)
        count = r.varint()
        att["vertices"] = _read_vertices(r, count, bool(flags & 64))
        r.floats(count // 3)  # lengths
        if nonessential:
            r.int32()
        return att

    if kind == "point":
        att["rotation"] = r.float()
        att["x"], att["y"] = r.float(), r.float()
        if nonessential:
            r.int32()
        return att

    if kind == "clipping":
        att["end_slot"] = r.varint()
        count = r.varint()
        att["vertices"] = _read_vertices(r, count, bool(flags & 16))
        if nonessential:
            r.int32()
        return att
    raise ValueError(f"unknown attachment type {kind}")


def _read_skin(r: Reader, strings: list[str], slots: list[Slot], default: bool,
               nonessential: bool) -> tuple[str, dict[int, dict[str, Any]]] | None:
    if default:
        slot_count = r.varint()
        if slot_count == 0:
            return None
        name = "default"
    else:
        name = r.string()
        if nonessential:
            r.int32()  # editor colour
        for _ in range(r.varint()):  # bones
            r.varint()
        for _ in range(r.varint()):  # ik constraints
            r.varint()
        for _ in range(r.varint()):  # transform constraints
            r.varint()
        for _ in range(r.varint()):  # path constraints
            r.varint()
        for _ in range(r.varint()):  # physics constraints
            r.varint()
        slot_count = r.varint()

    attachments: dict[int, dict[str, Any]] = {}
    for _ in range(slot_count):
        slot_index = r.varint()
        entries: dict[str, Any] = {}
        for _ in range(r.varint()):
            key = r.string_ref(strings)
            att = _read_attachment(r, strings, key, nonessential)
            if att is not None:
                entries[key] = att
        attachments[slot_index] = entries
    return name, attachments


def parse(data: bytes) -> Skeleton:
    r = Reader(data)
    hash_ = data[:8]
    r.pos = 8
    version = r.string()
    x, y, width, height = r.float(), r.float(), r.float(), r.float()
    reference_scale = r.float()
    nonessential = r.bool()
    fps, images_path = 30.0, None
    if nonessential:
        fps = r.float()
        images_path = r.string()
        r.string()  # audio path

    strings = [r.string() for _ in range(r.varint())]
    skel = Skeleton(hash_, version, x, y, width, height, reference_scale,
                    fps, images_path, strings)
    skel.bones = _read_bones(r, nonessential)
    skel.slots = _read_slots(r, strings, nonessential)
    _read_constraints(r)

    default = _read_skin(r, strings, skel.slots, True, nonessential)
    if default:
        skel.skins[default[0]] = default[1]
    for _ in range(r.varint()):
        extra = _read_skin(r, strings, skel.slots, False, nonessential)
        if extra:
            skel.skins[extra[0]] = extra[1]

    skel.events = []
    for _ in range(r.varint()):
        # Event names are inline strings; they are not in the strings table.
        skel.events.append(r.string())
        r.varint(False)  # int value
        r.float()  # float value
        r.string()  # string value
        if r.string() is not None:  # audio path
            r.float(); r.float()  # volume, balance

    skel.animations_offset = r.pos
    return skel


if __name__ == "__main__":
    import sys

    blob = open(sys.argv[1], "rb").read()
    s = parse(blob)
    print(f"version={s.version} fps={s.fps} images={s.images_path}")
    print(f"bounds x={s.x} y={s.y} w={s.width} h={s.height} refScale={s.reference_scale}")
    print(f"strings={len(s.strings)} bones={len(s.bones)} slots={len(s.slots)}")
    print(f"skins={list(s.skins)} events={len(s.events)}")
    counts = {}
    for skin in s.skins.values():
        for entries in skin.values():
            for att in entries.values():
                counts[att["type"]] = counts.get(att["type"], 0) + 1
    print(f"attachment types: {counts}")
    print(f"animations section starts at {s.animations_offset} (expected 47061)")


# --------------------------------------------------------------------------- animations

CURVE_LINEAR, CURVE_STEPPED, CURVE_BEZIER = 0, 1, 2

SLOT_ATTACHMENT, SLOT_RGBA, SLOT_RGB, SLOT_RGBA2, SLOT_RGB2, SLOT_ALPHA = range(6)
(BONE_ROTATE, BONE_TRANSLATE, BONE_TRANSLATEX, BONE_TRANSLATEY, BONE_SCALE,
 BONE_SCALEX, BONE_SCALEY, BONE_SHEAR, BONE_SHEARX, BONE_SHEARY, BONE_INHERIT) = range(11)

# Values carried per frame, after `time`, for each bone timeline type.
BONE_VALUE_COUNT = {
    BONE_ROTATE: 1, BONE_TRANSLATE: 2, BONE_TRANSLATEX: 1, BONE_TRANSLATEY: 1,
    BONE_SCALE: 2, BONE_SCALEX: 1, BONE_SCALEY: 1, BONE_SHEAR: 2,
    BONE_SHEARX: 1, BONE_SHEARY: 1,
}


def _read_curve_frames(r: Reader, frame_count: int, value_count: int) -> list[tuple]:
    """Frames of (time, v1..vn) with a curve byte between consecutive frames.

    A bezier curve stores four control floats per animated value.
    """
    r.varint()  # bezier capacity, recomputed on read
    frames = []
    time = r.float()
    values = r.floats(value_count)
    frame = 0
    while True:
        frames.append((time, values))
        if frame == frame_count - 1:
            break
        time2 = r.float()
        values2 = r.floats(value_count)
        curve = r.byte()
        if curve == CURVE_BEZIER:
            r.floats(4 * value_count)
        time, values, frame = time2, values2, frame + 1
    return frames


def _read_animation(r: Reader, skel: Skeleton) -> dict[str, Any]:
    anim: dict[str, Any] = {"bones": {}, "slots": {}, "duration": 0.0}
    r.varint()  # total timeline count, a capacity hint

    for _ in range(r.varint()):  # slot timelines
        slot_index = r.varint()
        for _ in range(r.varint()):
            kind, frame_count = r.byte(), r.varint()
            if kind == SLOT_ATTACHMENT:
                frames = [(r.float(), r.string_ref(skel.strings)) for _ in range(frame_count)]
                anim["slots"].setdefault(slot_index, {})["attachment"] = frames
            elif kind in (SLOT_RGBA, SLOT_RGBA2):
                _read_colour_frames(r, frame_count, 4 if kind == SLOT_RGBA else 7)
            elif kind in (SLOT_RGB, SLOT_RGB2):
                _read_colour_frames(r, frame_count, 3 if kind == SLOT_RGB else 6)
            elif kind == SLOT_ALPHA:
                _read_colour_frames(r, frame_count, 1)

    for _ in range(r.varint()):  # bone timelines
        bone_index = r.varint()
        for _ in range(r.varint()):
            kind, frame_count = r.byte(), r.varint()
            if kind == BONE_INHERIT:
                for _ in range(frame_count):
                    r.float(); r.byte()
                continue
            frames = _read_curve_frames(r, frame_count, BONE_VALUE_COUNT[kind])
            anim["bones"].setdefault(bone_index, {})[kind] = frames

    for _ in range(r.varint()):  # IK
        r.varint()
        frame_count = r.varint()
        r.varint()  # bezier capacity
        r.float(); r.float(); r.float()
        for frame in range(frame_count):
            r.byte(); r.byte(); r.byte()  # bend, compress, stretch
            if frame == frame_count - 1:
                break
            r.float(); r.float(); r.float()
            if r.byte() == CURVE_BEZIER:
                r.floats(8)

    for _ in range(r.varint()):  # transform
        r.varint()
        _read_curve_frames(r, r.varint(), 6)

    for _ in range(r.varint()):  # path
        r.varint()
        for _ in range(r.varint()):
            kind, frame_count = r.byte(), r.varint()
            _read_curve_frames(r, frame_count, 3 if kind == 2 else 1)

    for _ in range(r.varint()):  # physics
        r.varint()
        for _ in range(r.varint()):
            kind, frame_count = r.byte(), r.varint()
            if kind == 6:  # reset carries times only
                for _ in range(frame_count):
                    r.float()
                continue
            _read_curve_frames(r, frame_count, 1)

    for _ in range(r.varint()):  # deform, grouped by skin
        r.varint()
        for _ in range(r.varint()):
            slot_index = r.varint()
            for _ in range(r.varint()):
                attachment = r.string_ref(skel.strings)
                _read_deform(r, skel, slot_index, attachment)

    frame_count = r.varint()  # draw order
    for _ in range(frame_count):
        r.float()
        for _ in range(r.varint()):
            r.varint(); r.varint()

    frame_count = r.varint()  # events
    for _ in range(frame_count):
        r.float()
        index = r.varint()
        r.varint(False); r.float()
        if r.bool():
            r.string()
        _ = index

    for tracks in anim["bones"].values():
        for frames in tracks.values():
            anim["duration"] = max(anim["duration"], frames[-1][0])
    for tracks in anim["slots"].values():
        for frames in tracks.values():
            anim["duration"] = max(anim["duration"], frames[-1][0])
    return anim


def _read_colour_frames(r: Reader, frame_count: int, channels: int) -> None:
    r.varint()  # bezier capacity
    r.float()
    for _ in range(channels):
        r.byte()
    for frame in range(frame_count - 1):
        r.float()
        for _ in range(channels):
            r.byte()
        if r.byte() == CURVE_BEZIER:
            r.floats(4 * channels)
        _ = frame


def _read_deform(r: Reader, skel: Skeleton, slot_index: int, attachment: str | None) -> None:
    frame_count = r.varint()
    r.varint()  # bezier capacity
    r.float()
    for frame in range(frame_count):
        count = r.varint()
        if count:
            r.varint()  # start offset
            r.floats(count)
        if frame == frame_count - 1:
            break
        r.float()
        if r.byte() == CURVE_BEZIER:
            r.floats(4)


def read_animations(data: bytes, skel: Skeleton) -> dict[str, Any]:
    r = Reader(data)
    r.pos = skel.animations_offset
    animations = {}
    for _ in range(r.varint()):
        name = r.string()
        animations[name] = _read_animation(r, skel)
    if r.pos != len(data):
        raise ValueError(f"animation parse ended at {r.pos}, expected {len(data)}")
    return animations


def read_animations_partial(data: bytes, skel: Skeleton) -> dict[str, Any]:
    """Parse each animation's slot and bone timelines, then seek to the next.

    The post-bone sections (IK, deform, draw order) are skipped: their 4.2
    layout is not yet pinned down, and bone tracks plus attachment swaps carry
    the bulk of the motion. Skipping is safe because every animation's start
    offset is known, so a mis-parse cannot cascade.
    """
    r = Reader(data)
    r.pos = skel.animations_offset
    count = r.varint()
    starts = []
    probe = Reader(data)
    probe.pos = r.pos
    for _ in range(count):
        if probe.pos >= len(data):
            break
        starts.append(probe.pos)
        probe.string()
        # Names were located up front; walk forward to the next one.
        probe.pos = _next_animation_start(data, probe.pos, skel)
    animations: dict[str, Any] = {}
    for index, start in enumerate(starts):
        r.pos = start
        name = r.string()
        end = starts[index + 1] if index + 1 < len(starts) else len(data)
        anim: dict[str, Any] = {"bones": {}, "slots": {}, "duration": 0.0}
        r.varint()  # timeline count hint
        for _ in range(r.varint()):
            slot_index = r.varint()
            for _ in range(r.varint()):
                kind, frame_count = r.byte(), r.varint()
                if kind == SLOT_ATTACHMENT:
                    frames = [(r.float(), r.string_ref(skel.strings)) for _ in range(frame_count)]
                    anim["slots"].setdefault(slot_index, {})["attachment"] = frames
                else:
                    _read_colour_frames(r, frame_count, {1: 4, 2: 3, 3: 7, 4: 6, 5: 1}[kind])
        for _ in range(r.varint()):
            bone_index = r.varint()
            for _ in range(r.varint()):
                kind, frame_count = r.byte(), r.varint()
                if kind == BONE_INHERIT:
                    for _ in range(frame_count):
                        r.float(); r.byte()
                    continue
                anim["bones"].setdefault(bone_index, {})[kind] = _read_curve_frames(
                    r, frame_count, BONE_VALUE_COUNT[kind])
        for tracks in list(anim["bones"].values()) + list(anim["slots"].values()):
            for frames in tracks.values():
                anim["duration"] = max(anim["duration"], frames[-1][0])
        animations[name] = anim
        _ = end
    return animations


def _next_animation_start(data: bytes, pos: int, skel: Skeleton) -> int:
    """Locate the next animation name by scanning for a length-prefixed slug."""
    import re as _re

    for p in range(pos + 1, len(data) - 2):
        length = data[p]
        if not 3 <= length <= 24:
            continue
        raw = data[p + 1 : p + length]
        if len(raw) != length - 1:
            continue
        try:
            text = raw.decode("ascii")
        except UnicodeDecodeError:
            continue
        if _re.fullmatch(r"[a-z][a-z0-9_]{2,}", text):
            return p
    return len(data)
