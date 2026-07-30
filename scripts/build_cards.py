#!/usr/bin/env python3
"""Composite Slay the Spire 2 cards the way the game's card.tscn lays them out.

Pulls geometry from scenes/cards/card.tscn, tint values from the HSV shader
materials, stats from the decompiled C# card models, and strings from the
localization JSON, then draws the whole thing at 2x (the native asset scale).

    .venv/bin/python scripts/build_cards.py --card BASH
    .venv/bin/python scripts/build_cards.py --all
"""

from __future__ import annotations

import argparse
import json
import re
import struct
import sys
from dataclasses import dataclass, field, replace
from pathlib import Path

import numpy as np
from PIL import Image, ImageChops, ImageDraw, ImageFont

sys.path.insert(0, str(Path(__file__).parent))
from pck_extract import DEFAULT_PCK, Pack  # noqa: E402

PCK_ROOT = Path("artifacts/pck")
DECOMP = Path("artifacts/decompiled")
CARDS_NS = DECOMP / "MegaCrit.Sts2.Core.Models.Cards"
POOLS_NS = DECOMP / "MegaCrit.Sts2.Core.Models.CardPools"
FONT_CACHE = Path("artifacts/fonts")

SCALE = 2  # card.tscn works in 1x units; the art ships at 2x
# Full-card captures use a 400x520 viewport with the card origin at (211, 276).
# Render it at native 2x resolution, then downsample once when saving.
BOUNDS = (-211.0, -276.0, 189.0, 244.0)
OUTPUT_SIZE = (400, 520)

# Rects straight out of card.tscn, in CardContainer space (centre origin).
R_SHADOW = (-138.0, -199.0, 162.0, 223.0)
R_FRAME = (-150.0, -211.0, 150.0, 211.0)
R_PORTRAIT = (-125.0, -168.0, 125.0, 22.0)
R_PORTRAIT_BORDER = (-137.5, -164.0, 137.5, 46.0)
R_BANNER = (-163.0, -207.0, 164.0, -124.0)
R_TITLE = (-105.0, -204.0, 105.0, -150.0)
R_DESC = (-122.0, 37.0, 121.0, 173.0)
R_TYPE_PLAQUE = (-30.5, 1.0, 30.5, 38.0)
R_ENERGY = (-166.0, -227.0, -102.0, -163.0)

# Ancient-rarity cards replace the frame/portrait/banner with a full-bleed
# layout. The first two are anchors_preset=15 nodes at scale 0.5, so their
# offsets are pre-multiplied out here.
R_ANCIENT_PORTRAIT = (-153.0, -215.0, 146.0, 206.0)
R_ANCIENT_GLASS = (-148.465, -210.71, 146.8075, 205.295)
R_ANCIENT_BORDER = (-154.0, -223.0, 152.0, 217.0)
R_ANCIENT_TEXT_BG = (-133.0, -22.0, 131.0, 181.0)
# AnimatedSprite2D "Fire", centred at AncientBanner's origin + (164, -10).
ANCIENT_FLAME_CENTRE = (-163.0 + 164.0, -207.0 - 10.0)
ANCIENT_FLAME_SCALE = 0.6
ANCIENT_FLAME_FPS = 10

# Infection is the only canonical card with HasBuiltInOverlay. Its overlay
# scene has a static grime/tint layer and a 30-frame Sprite2D animation.
INFECTION_LAYER_1_POSITION = (-2.5, -7.99999)
INFECTION_LAYER_1_SCALE = (0.473862, 0.47199)
INFECTION_LAYER_2_POSITION = (-0.499993, -7.50001)
INFECTION_LAYER_2_SCALE = (0.510736, 0.520501)
INFECTION_FRAME_COUNT = 30
INFECTION_FPS = 15

CREAM = (255, 246, 226)
GOLD = (0xEF, 0xC8, 0x51)
GREEN = (0x7F, 0xFF, 0x00)
SHADOW = (0, 0, 0)

# StsColors, for the [tag]s that appear in card text.
BBCODE_COLORS = {
    "gold": GOLD, "green": GREEN, "red": (0xFF, 0x55, 0x55),
    "blue": (0x87, 0xCE, 0xEB), "purple": (0xEE, 0x82, 0xEE),
}

# NCard.GetTitleLabelOutlineColor, keyed by rarity.
TITLE_OUTLINE_BY_RARITY = {
    "Uncommon": (0x00, 0x5C, 0x75), "Rare": (0x6B, 0x4B, 0x00),
    "Curse": (0x55, 0x0B, 0x9E), "Quest": (0x7E, 0x3E, 0x15),
    "Status": (0x4F, 0x52, 0x2F), "Event": (0x1B, 0x61, 0x31),
}
TITLE_OUTLINE_COMMON = (0x4D, 0x4B, 0x40)
TITLE_OUTLINE_UPGRADED = (0x1B, 0x61, 0x31)  # cardTitleOutlineSpecial

# Godot's outline_size is a diameter-ish value that renders far heavier through
# Pillow's stroke_width (a radius), so these are tuned down by eye.
TITLE_STROKE = 3
ENERGY_STROKE = 4
SHADOW_OFFSET = 2 * SCALE
LABEL_SHADOW_ALPHA = 48  # theme_override font_shadow_color alpha 0.188
DESC_SHADOW_ALPHA = 64  # 0.251

DEFAULT_ENERGY_OUTLINE = "5C5440"  # CardPoolModel.EnergyOutlineColor

# CardKeywordOrder: these render as their own lines around the description.
# The game Insert(0)s each "before" keyword in this order, so the rendered
# order ends up reversed.
KEYWORDS_BEFORE = ["Ethereal", "Sly", "Retain", "Innate", "Unplayable"]
KEYWORDS_AFTER = ["Exhaust", "Eternal"]
RARITY_TO_BANNER = {
    "Uncommon": "uncommon", "Rare": "rare", "Curse": "curse",
    "Status": "status", "Event": "event", "Quest": "quest",
    "Ancient": "ancient",
}
TYPE_TO_FRAME = {"Attack": "attack", "Skill": "skill", "Power": "power", "Quest": "quest"}
# CardModel.PortraitBorderPath folds None/Status/Curse/Quest onto the Skill
# border, which is then tinted by rarity - that is where the purple band on
# curses and the olive band on statuses comes from.
TYPE_TO_BORDER = {"Attack": "attack", "Power": "power"}
DEFAULT_BORDER = "skill"


# --------------------------------------------------------------------------- fonts

def _unrscc(data: bytes) -> bytes:
    """Godot wraps imported resources in a zstd-blocked 'RSCC' container."""
    from compression import zstd

    _mode, block, total = struct.unpack("<III", data[4:16])
    count = -(-total // block)
    sizes = struct.unpack(f"<{count}I", data[16 : 16 + 4 * count])
    pos = 16 + 4 * count
    out = bytearray()
    for size in sizes:
        chunk = data[pos : pos + size]
        pos += size
        out += zstd.decompress(chunk) if size < min(block, total - len(out)) else chunk
    return bytes(out)


def _carve_sfnt(blob: bytes) -> bytes | None:
    """Find the original TTF inside a .fontdata (the rest is glyph cache)."""
    at = -1
    while (at := blob.find(b"\x00\x01\x00\x00", at + 1)) >= 0:
        tables = struct.unpack(">H", blob[at + 4 : at + 6])[0]
        if not 4 <= tables <= 40:
            continue
        entries = [blob[at + 12 + 16 * i : at + 28 + 16 * i] for i in range(tables)]
        if len(entries[-1]) < 16:
            continue
        tags = {e[:4] for e in entries}
        # 0x00010000 is a common byte run; only a real directory has these tables.
        if not {b"head", b"cmap", b"name"} <= tags:
            continue
        spans = [struct.unpack(">II", e[8:16]) for e in entries]
        end = max(offset + length for offset, length in spans)
        if not 1000 < end <= len(blob) - at:
            continue
        return blob[at : at + end]
    return None


def ensure_fonts(pack: Pack) -> dict[str, Path]:
    FONT_CACHE.mkdir(parents=True, exist_ok=True)
    wanted = {"kreon_bold": None, "kreon_regular": None}
    for name in list(wanted):
        dest = FONT_CACHE / f"{name}.ttf"
        if dest.exists():
            wanted[name] = dest
            continue
        src = next((p for p in pack.entries if f"/{name}.ttf-" in p and p.endswith(".fontdata")), None)
        if src is None:
            raise SystemExit(f"no .fontdata for {name} in the pack")
        ttf = _carve_sfnt(_unrscc(pack.read(src)))
        if ttf is None:
            raise SystemExit(f"could not carve a TTF out of {src}")
        dest.write_bytes(ttf)
        wanted[name] = dest
    return wanted  # type: ignore[return-value]


# --------------------------------------------------------------------------- tint

def hsv_shader(img: Image.Image, h: float, s: float, v: float) -> Image.Image:
    """Port of shaders/hsv.gdshader: a YIQ hue rotation plus sat/value scale."""
    arr = np.asarray(img.convert("RGBA"), dtype=np.float32) / 255.0
    rgb, alpha = arr[..., :3], arr[..., 3:]
    to_yiq = np.array(
        [[0.2989, 0.5870, 0.1140], [0.5959, -0.2774, -0.3216], [0.2115, -0.5229, 0.3114]],
        dtype=np.float32,
    )
    yiq = rgb @ to_yiq.T
    angle = (1.0 - h) * 6.283185
    cos_a, sin_a = float(np.cos(angle)), float(np.sin(angle))
    i, q = yiq[..., 1].copy(), yiq[..., 2].copy()
    yiq[..., 1] = i * cos_a - q * sin_a
    yiq[..., 2] = i * sin_a + q * cos_a
    yiq[..., 1] *= s
    yiq[..., 2] *= s
    yiq *= v
    out = np.clip(yiq @ np.linalg.inv(to_yiq).T, 0.0, 1.0)
    return Image.fromarray((np.concatenate([out, alpha], axis=-1) * 255).astype(np.uint8), "RGBA")


def load_materials() -> dict[str, tuple[float, float, float]]:
    mats: dict[str, tuple[float, float, float]] = {}
    for folder in ("frames", "banners"):
        for path in (PCK_ROOT / "materials/cards" / folder).glob("*.tres"):
            text = path.read_text()
            get = lambda k: float(re.search(rf"shader_parameter/{k} = ([-\d.]+)", text).group(1))  # noqa: E731
            mats[path.stem.replace("_mat", "")] = (get("h"), get("s"), get("v"))
    return mats


# --------------------------------------------------------------------------- data

@dataclass
class Pool:
    name: str
    frame: str  # e.g. "card_frame_red"
    energy_color: str
    energy_outline: tuple[int, int, int]


@dataclass
class Card:
    id: str
    cls: str
    title: str
    description: str
    cost: int
    costs_x: bool
    type: str
    rarity: str
    pool: Pool
    portrait: Path | None
    variables: dict[str, float] = field(default_factory=dict)
    keywords: list[str] = field(default_factory=list)
    upgrade_levels: int = 1
    changed: frozenset[str] = frozenset()


def _hex(value: str) -> tuple[int, int, int]:
    return tuple(int(value[i : i + 2], 16) for i in (0, 2, 4))  # type: ignore[return-value]


def load_pools() -> tuple[dict[str, Pool], Pool]:
    """Map each card class to its pool - the authoritative source for framing."""
    by_class: dict[str, Pool] = {}
    fallback: Pool | None = None
    for source in sorted(POOLS_NS.glob("*CardPool.cs")):
        text = source.read_text(errors="replace")
        grab = lambda k: (re.search(rf'{k} => "([^"]+)"', text) or [None, None])[1]  # noqa: E731
        frame, energy = grab("CardFrameMaterialPath"), grab("EnergyColorName")
        if not frame or not energy:
            continue
        outline = re.search(r'EnergyOutlineColor => new Color\("(\w+)"\)', text)
        pool = Pool(
            source.stem.replace("CardPool", ""), frame, energy,
            _hex(outline.group(1) if outline else DEFAULT_ENERGY_OUTLINE),
        )
        for cls in re.findall(r"ModelDb\.Card<(\w+)>\(\)", text):
            by_class[cls] = pool
        if pool.name == "Colorless":
            fallback = pool
    assert fallback is not None, "no ColorlessCardPool found"
    return by_class, fallback


# Three shapes appear in CanonicalVars:
#   new DamageVar(8m, ...)              -> named after the class
#   new PowerVar<VulnerablePower>(2m)   -> named after the type argument
#   new DynamicVar("Accelerant", 1m)    -> named by string
# CalculatedVar("X") has no static value at all; it stays unresolved.
VAR_RE = re.compile(
    r'new (\w+)Var(?:<(\w+)>)?\(\s*'
    r'(?:"([^"]+)"(?:\s*,\s*([-\d.]+)m?)?|([-\d.]+)m?|([A-Za-z_]\w*))'
)
BASE_RE = re.compile(r":\s*base\(\s*(-?\d+)\s*,\s*CardType\.(\w+)\s*,\s*CardRarity\.(\w+)")


def snake(name: str) -> str:
    return re.sub(r"(?<!^)(?=[A-Z])", "_", name).upper()


def parse_card_source(
    path: Path,
) -> tuple[int, bool, str, str, dict[str, float], list[str], int] | None:
    text = path.read_text(errors="replace")
    base = BASE_RE.search(text)
    if not base:
        return None
    costs_x = "HasEnergyCostX => true" in text
    levels = re.search(r"MaxUpgradeLevel => (\d+)", text)
    upgrade_levels = int(levels.group(1)) if levels else 1
    keyword_block = re.search(r"CanonicalKeywords\s*=>(.*?);", text, re.S)
    keywords = re.findall(r"CardKeyword\.(\w+)", keyword_block.group(1)) if keyword_block else []
    def from_field(identifier: str) -> str | None:
        """Cards that grow over a run pass a property, e.g. BlockVar(CurrentBlock)."""
        backing = f"_{identifier[:1].lower()}{identifier[1:]}"
        hit = re.search(rf"\b{re.escape(backing)}\s*=\s*(-?\d+)", text)
        return hit.group(1) if hit else None

    variables: dict[str, float] = {}
    block = re.search(r"CanonicalVars\s*=>(.*?);", text, re.S)
    if block:
        for kind, generic, name, named_value, plain_value, ident in VAR_RE.findall(block.group(1)):
            value = named_value or plain_value or (from_field(ident) if ident else None)
            if value:
                variables[name or generic or kind] = float(value)
    return int(base.group(1)), costs_x, base.group(2), base.group(3), variables, keywords, upgrade_levels


def find_portrait(card_id: str) -> Path | None:
    """Locate a card's art.

    Portraits are not simply <pool>/<id>.webp: unreleased cards sit under a
    beta/ subfolder, and a few (Wither) ship numbered variants instead of a
    plain name, so this searches the whole tree and prefers finished art.
    """
    stem = card_id.lower()
    root = PCK_ROOT / "images/packed/card_portraits"
    exact, numbered, variants = [], [], []
    for path in root.rglob("*.webp"):
        if path.stem == stem:
            exact.append(path)
        elif re.fullmatch(rf"{re.escape(stem)}\d+", path.stem):
            numbered.append(path)
        elif path.stem.startswith(f"{stem}_"):
            variants.append(path)
    # CardModel checks HasPortrait before HasBetaPortrait, so finished art always
    # wins; Wither-style variants (wither1..3) are level 0 first.
    for group in (exact, numbered):
        if chosen := sorted(p for p in group if "beta" not in p.parts):
            return chosen[0]
    if chosen := sorted(exact + numbered):
        return chosen[0]
    # Stateful cards can expose several portraits through AllPortraitPaths.
    # Their constructor state is the canonical poster; currently Mad Science
    # starts as Attack, with Skill and Power as later runtime states.
    finished_variants = sorted(
        (p for p in variants if "beta" not in p.parts),
        key=lambda p: (not p.stem.endswith("_attack"), str(p)),
    )
    if finished_variants:
        return finished_variants[0]
    if variants:
        return sorted(variants)[0]
    # Some cards only exist in the shared card atlas, at lower resolution.
    return next((PCK_ROOT / "_icons/card_atlas").rglob(f"{stem}.png"), None)


def load_cards(strings: dict[str, str]) -> dict[str, Card]:
    pools, fallback = load_pools()
    cards: dict[str, Card] = {}
    for source in sorted(CARDS_NS.glob("*.cs")):
        parsed = parse_card_source(source)
        if parsed is None:
            continue
        cost, costs_x, ctype, rarity, variables, keywords, upgrade_levels = parsed
        card_id = snake(source.stem)
        title = strings.get(f"{card_id}.title")
        if title is None:
            continue
        cards[card_id] = Card(
            card_id, source.stem, title, strings.get(f"{card_id}.description", ""),
            cost, costs_x, ctype, rarity, pools.get(source.stem, fallback),
            find_portrait(card_id), variables, keywords, upgrade_levels,
        )
    return cards


def fmt(value: float) -> str:
    return str(int(value)) if float(value).is_integer() else str(value)


def _split_top(text: str, sep: str = "|") -> list[str]:
    """Split on `sep`, ignoring separators nested inside braces or parens."""
    parts, depth, current = [], 0, []
    for char in text:
        if char in "{(":
            depth += 1
        elif char in "})":
            depth -= 1
        if char == sep and depth == 0:
            parts.append("".join(current))
            current = []
        else:
            current.append(char)
    parts.append("".join(current))
    return parts


def resolve_text(
    card: Card, upgraded: bool = False, unresolved: set[str] | None = None
) -> str:
    """Expand the card-text template against this card's canonical values.

    The templates nest ({CardType:choose(...):{Damage:diff()}...}), so this
    walks braces rather than pattern-matching flat placeholders - otherwise a
    construct like Shiv's `choose` leaks raw syntax onto the card.

    A CalculatedVar has no static value, so it renders as a literal "X" the way
    the game does before combat resolves it. Pass `unresolved` to collect the
    names of any such variables; callers that need real numbers (the wiki text
    export) use that to reject the result rather than publish an "X".
    """

    def evaluate(body: str, context: str | None = None) -> str:
        head, _, rest = body.partition(":")
        name = head
        fn, _, args = rest.partition(":")
        if not name and context:
            # A bare {:diff()} inside a plural refers to the plural's own
            # variable (Lightning Rod's "next {:diff()} turns").
            name = context
        value = card.variables.get(name)

        if name == "singleStarIcon" and not fn:
            return "[icon:star]"
        if not fn and value is not None:
            text = fmt(value)
            return f"[green]{text}[/green]" if name in card.changed else text
        if fn.startswith("choose("):
            # SmartFormat ChooseFormatter: match the value's text against the
            # choice list; the trailing extra option is the default.
            choices = fn[len("choose(") :].rstrip(")").split("|")
            options = _split_top(args)
            key = card.type if name == "CardType" else fmt(value) if value is not None else None
            if key is not None and key in choices:
                index = choices.index(key)
                if index < len(options):
                    return expand(options[index], name)
            # Runtime-dependent value (TargetType and friends): the default.
            return expand(options[-1], name)
        if fn.startswith("cond"):
            # SmartFormat ConditionalFormatter. "COND?text" options test the
            # value ({Attacks:cond:>1?...}); without conditions the first
            # option is the truthy branch and the last the falsy one, which is
            # how runtime bools (GainsBlock) resolve at canonical state: absent
            # from the vars, hence falsy.
            options = _split_top(args)
            complex_options = [option.partition("?") for option in options if "?" in option]
            if complex_options:
                for condition, _, text in complex_options:
                    test = re.fullmatch(r"(>=|<=|!=|=|>|<)(-?\d+(?:\.\d+)?)", condition)
                    if test and value is not None:
                        op, operand = test.group(1), float(test.group(2))
                        matched = {
                            ">": value > operand, "<": value < operand,
                            ">=": value >= operand, "<=": value <= operand,
                            "=": value == operand, "!=": value != operand,
                        }[op]
                        if matched:
                            return expand(text, name)
                defaults = [option for option in options if "?" not in option]
                return expand(defaults[-1], name) if defaults else ""
            truthy = value is not None and value != 0
            return expand(options[0] if truthy else options[-1], name)
        if fn == "show" and name == "IfUpgraded":
            options = _split_top(args)
            if upgraded:
                return expand(options[0], context)
            return expand(options[1], context) if len(options) > 1 else ""
        if fn == "plural":
            # A bare {} or {:diff()} inside any of these formatter options
            # scopes to the formatter's own variable, so `name` becomes the
            # nested expansion context.
            options = _split_top(args)
            if value is not None and abs(value) == 1 and len(options) > 1:
                return expand(options[0], name)
            return expand(options[-1], name)
        if fn.startswith(("energyIcons", "starIcons")):
            kind = "star" if fn.startswith("starIcons") else "energy"
            # The formatter option (energyIcons(1)) wins when there is no var.
            option = re.search(r"\((\d+)\)", fn)
            count = int(value) if value is not None else int(option.group(1)) if option else 1
            glyph = f"[icon:{kind}]"
            # 1-3 draw as repeated pips; anything else as "N" plus one pip.
            if 1 <= count <= 3:
                return glyph * count
            text = fmt(count)
            if name in card.changed:
                text = f"[green]{text}[/green]"
            return text + glyph
        if fn.startswith(("diff", "inverseDiff", "show", "percentMore", "percentLess")):
            if value is None:
                if unresolved is not None:
                    unresolved.add(name)
                return "X"
            text = fmt(value)
            return f"[green]{text}[/green]" if name in card.changed else text
        # Unknown construct (nested rider tables and the like): drop it rather
        # than printing template syntax onto the card.
        return ""

    def expand(text: str, context: str | None = None) -> str:
        out, i = [], 0
        while i < len(text):
            char = text[i]
            if char != "{":
                out.append(char)
                i += 1
                continue
            depth, j = 0, i
            while j < len(text):
                if text[j] == "{":
                    depth += 1
                elif text[j] == "}":
                    depth -= 1
                    if depth == 0:
                        break
                j += 1
            if depth != 0:  # unbalanced; emit the rest verbatim
                out.append(text[i:])
                break
            out.append(evaluate(text[i + 1 : j], context))
            i = j + 1
        return "".join(out)

    return expand(card.description.replace("\\n", "\n"))


def compose_text(card: Card, keyword_strings: dict[str, str], upgraded: bool = False) -> str:
    """Full card body: keyword lines wrapped around the description, as CardModel does."""
    period = keyword_strings.get("PERIOD", ".")

    def line(keyword: str) -> str:
        title = keyword_strings.get(f"{keyword.upper()}.title", keyword)
        return f"[gold]{title}[/gold]{period}"

    have = set(card.keywords)
    before = [line(k) for k in KEYWORDS_BEFORE if k in have][::-1]
    after = [line(k) for k in KEYWORDS_AFTER if k in have]
    body = resolve_text(card, upgraded).strip()
    return "\n".join(before + ([body] if body else []) + after)


def load_accessor_map() -> dict[str, str]:
    """DynamicVarSet exposes typed properties whose names differ from the var
    keys used in the localization strings (Vulnerable -> VulnerablePower)."""
    path = DECOMP / "MegaCrit.Sts2.Core.Localization.DynamicVars/DynamicVarSet.cs"
    if not path.exists():
        return {}
    return dict(re.findall(r'public \S+ (\w+) => \(\S+\)_vars\["(\w+)"\];', path.read_text()))


def upgrade(card: Card, accessors: dict[str, str]) -> Card | None:
    """Apply the card's OnUpgrade body, mirroring CardModel's upgrade path."""
    if card.upgrade_levels == 0:
        return None
    source = (CARDS_NS / f"{card.cls}.cs").read_text(errors="replace")
    body = re.search(r"protected override void OnUpgrade\(\)\s*\{(.*?)\n\t\}", source, re.S)
    variables = dict(card.variables)
    keywords = list(card.keywords)
    changed: set[str] = set()
    cost = card.cost
    if body:
        text = body.group(1)
        for accessor, delta in re.findall(
            r"DynamicVars\.(\w+)\.UpgradeValueBy\(\s*(-?[\d.]+)m?", text
        ):
            key = accessors.get(accessor, accessor)
            if key in variables:
                variables[key] += float(delta)
                changed.add(key)
        for key, delta in re.findall(
            r'DynamicVars\["(\w+)"\]\.UpgradeValueBy\(\s*(-?[\d.]+)m?', text
        ):
            if key in variables:
                variables[key] += float(delta)
                changed.add(key)
        for delta in re.findall(r"EnergyCost\.UpgradeBy\(\s*(-?\d+)", text):
            cost = max(0, cost + int(delta))
        for keyword in re.findall(r"AddKeyword\(CardKeyword\.(\w+)", text):
            if keyword not in keywords:
                keywords.append(keyword)
        for keyword in re.findall(r"RemoveKeyword\(CardKeyword\.(\w+)", text):
            if keyword in keywords:
                keywords.remove(keyword)
    suffix = "+" if card.upgrade_levels <= 1 else "+1"
    return replace(card, title=card.title + suffix, cost=cost, variables=variables,
                   keywords=keywords, changed=frozenset(changed))


def wither_state(card: Card, level: int) -> Card:
    """Build Wither's FakeUpgrade runtime states without calling them upgrades."""
    if card.id != "WITHER" or level not in (1, 2):
        raise ValueError("Wither runtime level must be 1 or 2")
    portrait = (
        PCK_ROOT
        / "images/packed/card_portraits/status"
        / f"wither{level + 1}.webp"
    )
    if not portrait.exists():
        raise FileNotFoundError(portrait)
    variables = dict(card.variables)
    variables["Damage"] = 3.0 * (level + 1)
    return replace(
        card,
        title=f"{card.title}+{level}",
        portrait=portrait,
        variables=variables,
        changed=frozenset({"Damage"}),
    )


# --------------------------------------------------------------------------- text

@dataclass
class Run:
    text: str
    color: tuple[int, int, int]
    icon: str | None = None  # "energy" / "star", drawn as an inline sprite


def parse_bbcode(text: str) -> list[list[Run]]:
    """Split into lines of coloured runs; only [gold] and [b] appear on cards."""
    lines: list[list[Run]] = []
    for raw in text.split("\n"):
        runs: list[Run] = []
        color = CREAM
        pos = 0
        for tag in re.finditer(r"\[(/?)(\w+)(?::(\w+))?\]", raw):
            if tag.start() > pos:
                runs.append(Run(raw[pos : tag.start()], color))
            closing, name = tag.group(1), tag.group(2)
            if name == "icon":
                runs.append(Run("", color, icon=tag.group(3)))
            elif name in BBCODE_COLORS:
                color = CREAM if closing else BBCODE_COLORS[name]
            pos = tag.end()
        if pos < len(raw):
            runs.append(Run(raw[pos:], color))
        lines.append(runs or [Run("", CREAM)])
    return lines


def run_width(run: Run, font: ImageFont.FreeTypeFont) -> float:
    """Inline icons are square and sized to the font's ascent."""
    if run.icon:
        return font.getmetrics()[0]
    return font.getlength(run.text)


def wrap_runs(lines: list[list[Run]], font: ImageFont.FreeTypeFont, width: int) -> list[list[Run]]:
    out: list[list[Run]] = []
    for runs in lines:
        current: list[Run] = []
        used = 0.0
        for run in runs:
            if run.icon:
                current.append(run)
                used += run_width(run, font)
                continue
            for word in re.split(r"(\s+)", run.text):
                if not word:
                    continue
                w = font.getlength(word)
                if word.isspace():
                    if current:
                        current.append(Run(word, run.color))
                        used += w
                    continue
                if current and used + w > width:
                    while current and current[-1].text.isspace():
                        current.pop()
                    out.append(current)
                    current, used = [], 0.0
                current.append(Run(word, run.color))
                used += w
        while current and current[-1].text.isspace():
            current.pop()
        out.append(current)
    return out


def _layer(canvas: Image.Image, paint, alpha: int = 255) -> None:
    """Paint onto a scratch layer and composite it.

    ImageDraw writes ink straight into RGBA pixels, so drawing a translucent
    shadow directly on the card would punch a hole in the art underneath
    instead of darkening it. Painting opaque then scaling alpha avoids that,
    and keeps overlapping glyphs from double-darkening each other.
    """
    scratch = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    paint(ImageDraw.Draw(scratch))
    if alpha < 255:
        scratch.putalpha(scratch.getchannel("A").point(lambda v: v * alpha // 255))
    canvas.alpha_composite(scratch)


def draw_runs(
    canvas: Image.Image, lines: list[list[Run]], font: ImageFont.FreeTypeFont,
    box: tuple[int, int, int, int], leading: int,
    icons: dict[str, Image.Image] | None = None,
) -> None:
    x0, y0, x1, y1 = box
    ascent, descent = font.getmetrics()
    line_h = ascent + descent + leading
    start_y = y0 + ((y1 - y0) - line_h * len(lines)) // 2

    def positions(shift: int):
        y = start_y + shift
        for runs in lines:
            width = sum(run_width(r, font) for r in runs)
            x = x0 + ((x1 - x0) - width) / 2 + shift
            for item in runs:
                yield item, x, y
                x += run_width(item, font)
            y += line_h

    def paint(shift: int, color: tuple[int, int, int] | None):
        def run(draw: ImageDraw.ImageDraw) -> None:
            for item, x, y in positions(shift):
                if not item.icon:
                    draw.text((x, y), item.text, font=font, fill=(*(color or item.color), 255))
        return run

    _layer(canvas, paint(SHADOW_OFFSET, SHADOW), DESC_SHADOW_ALPHA)
    _layer(canvas, paint(0, None))

    for item, x, y in positions(0):
        if item.icon and icons and item.icon in icons:
            sprite = icons[item.icon]
            size = ascent
            canvas.alpha_composite(
                sprite.resize((size, size), Image.LANCZOS),
                (round(x), round(y + (ascent - size) / 2)),
            )


def draw_outlined(
    canvas: Image.Image, xy: tuple[float, float], text: str,
    font: ImageFont.FreeTypeFont, fill: tuple[int, int, int],
    outline: tuple[int, int, int], stroke: int, anchor: str = "mm",
) -> None:
    x, y = xy
    _layer(
        canvas,
        lambda d: d.text((x + SHADOW_OFFSET, y + SHADOW_OFFSET), text, font=font, anchor=anchor,
                         fill=(*SHADOW, 255), stroke_width=stroke, stroke_fill=(*SHADOW, 255)),
        LABEL_SHADOW_ALPHA,
    )
    _layer(
        canvas,
        lambda d: d.text((x, y), text, font=font, anchor=anchor, fill=(*fill, 255),
                         stroke_width=stroke, stroke_fill=(*outline, 255)),
    )


def clear_transparent_rgb(image: Image.Image) -> Image.Image:
    """Zero RGB where alpha is zero so WebP decoders cannot expose color junk."""
    arr = np.array(image.convert("RGBA"), dtype=np.uint8, copy=True)
    arr[..., :3][arr[..., 3] == 0] = 0
    return Image.fromarray(arr, "RGBA")


# --------------------------------------------------------------------------- render

class Renderer:
    def __init__(self, fonts: dict[str, Path]) -> None:
        self.materials = load_materials()
        self.icons = PCK_ROOT / "_icons/ui_atlas/card"
        self.bold = fonts["kreon_bold"]
        self.regular = fonts["kreon_regular"]
        self._font_cache: dict[tuple[str, int], ImageFont.FreeTypeFont] = {}

    def font(self, which: str, size: int) -> ImageFont.FreeTypeFont:
        key = (which, size)
        if key not in self._font_cache:
            path = self.bold if which == "bold" else self.regular
            self._font_cache[key] = ImageFont.truetype(str(path), size)
        return self._font_cache[key]

    def icon(self, name: str) -> Image.Image:
        return Image.open(self.icons / f"{name}.png").convert("RGBA")

    def sprites(self, energy_color: str) -> dict[str, Image.Image]:
        root = PCK_ROOT / "images/packed/sprite_fonts"
        orb = root / f"{energy_color}_energy_icon.webp"
        if not orb.exists():
            orb = root / "colorless_energy_icon.webp"
        return {
            "energy": Image.open(orb).convert("RGBA"),
            "star": Image.open(root / "star_icon.webp").convert("RGBA"),
        }

    def template(self, name: str) -> Image.Image:
        """Ancient-card pieces live in the compressed atlas, not the UI atlas."""
        root = PCK_ROOT / "_icons/compressed/card_template"
        return Image.open(root / f"{name}.png").convert("RGBA")

    def flame_frames(self) -> list[Image.Image]:
        root = PCK_ROOT / "_icons/compressed/card_template/ancient_flame"
        return [
            Image.open(root / f"ancient_card_flame_{i}.png").convert("RGBA")
            for i in range(ANCIENT_FLAME_FPS)
        ]

    def paste_flame(self, canvas: Image.Image, frame: Image.Image) -> None:
        """AnimatedSprite2D draws centred on its position, at the node's scale."""
        width = round(frame.width * ANCIENT_FLAME_SCALE * SCALE)
        height = round(frame.height * ANCIENT_FLAME_SCALE * SCALE)
        cx = round((ANCIENT_FLAME_CENTRE[0] - BOUNDS[0]) * SCALE)
        cy = round((ANCIENT_FLAME_CENTRE[1] - BOUNDS[1]) * SCALE)
        canvas.alpha_composite(
            frame.resize((width, height), Image.LANCZOS), (cx - width // 2, cy - height // 2)
        )

    def paste_sprite(
        self, canvas: Image.Image, sprite: Image.Image,
        position: tuple[float, float], scale: tuple[float, float],
    ) -> None:
        """Draw a centred Sprite2D into the renderer's native 2x canvas."""
        width = round(sprite.width * scale[0] * SCALE)
        height = round(sprite.height * scale[1] * SCALE)
        cx = round((position[0] - BOUNDS[0]) * SCALE)
        cy = round((position[1] - BOUNDS[1]) * SCALE)
        canvas.alpha_composite(
            sprite.resize((width, height), Image.LANCZOS),
            (cx - width // 2, cy - height // 2),
        )

    def infection_overlay(self, frame_index: int) -> Image.Image:
        """Reproduce scenes/cards/overlays/infection.tscn at one animation frame."""
        overlay = Image.new("RGBA", self.canvas_size(), (0, 0, 0, 0))
        root = PCK_ROOT / "images/card_overlays/infection"
        static = Image.open(root / "infectiona.webp").convert("RGBA")
        animated = Image.open(root / f"infection_{frame_index:02d}.webp").convert("RGBA")
        self.paste_sprite(
            overlay, static, INFECTION_LAYER_1_POSITION, INFECTION_LAYER_1_SCALE
        )
        self.paste_sprite(
            overlay, animated, INFECTION_LAYER_2_POSITION, INFECTION_LAYER_2_SCALE
        )
        return overlay

    @staticmethod
    def box(rect: tuple[float, float, float, float]) -> tuple[int, int, int, int]:
        ox, oy = BOUNDS[0], BOUNDS[1]
        left, top, right, bottom = rect
        return (
            round((left - ox) * SCALE), round((top - oy) * SCALE),
            round((right - ox) * SCALE), round((bottom - oy) * SCALE),
        )

    @staticmethod
    def canvas_size() -> tuple[int, int]:
        return (
            round((BOUNDS[2] - BOUNDS[0]) * SCALE),
            round((BOUNDS[3] - BOUNDS[1]) * SCALE),
        )

    def paste(self, canvas: Image.Image, img: Image.Image, rect, tint: str | None = None) -> None:
        x0, y0, x1, y1 = self.box(rect)
        if tint:
            img = hsv_shader(img, *self.materials[tint])
        img = img.resize((x1 - x0, y1 - y0), Image.LANCZOS)
        canvas.alpha_composite(img, (x0, y0))

    def fitted(
        self, img: Image.Image, rect: tuple[float, float, float, float]
    ) -> tuple[Image.Image, tuple[int, int]]:
        """TextureRect STRETCH_KEEP_ASPECT_CENTERED (stretch_mode = 5)."""
        x0, y0, x1, y1 = self.box(rect)
        scale = min((x1 - x0) / img.width, (y1 - y0) / img.height)
        width, height = round(img.width * scale), round(img.height * scale)
        fitted = img.resize((width, height), Image.LANCZOS)
        position = (x0 + (x1 - x0 - width) // 2, y0 + (y1 - y0 - height) // 2)
        return fitted, position

    def paste_modulated(
        self, canvas: Image.Image, img: Image.Image,
        rect: tuple[float, float, float, float],
        color: tuple[float, float, float, float],
        keep_aspect: bool = False,
    ) -> None:
        """Apply CanvasItem.modulate before normal alpha compositing."""
        if keep_aspect:
            img, position = self.fitted(img, rect)
        else:
            x0, y0, x1, y1 = self.box(rect)
            img = img.resize((x1 - x0, y1 - y0), Image.LANCZOS)
            position = (x0, y0)
        arr = np.asarray(img.convert("RGBA"), dtype=np.float32) / 255.0
        arr[..., :3] *= np.asarray(color[:3], dtype=np.float32)
        arr[..., 3] *= color[3]
        layer = Image.fromarray(
            np.round(np.clip(arr, 0.0, 1.0) * 255).astype(np.uint8), "RGBA"
        )
        canvas.alpha_composite(layer, position)

    def paste_ancient_glass(self, canvas: Image.Image) -> None:
        """Port debug_ancient_card_border_overlay.gdshader."""
        x0, y0, x1, y1 = self.box(R_ANCIENT_GLASS)
        size = (x1 - x0, y1 - y0)
        screen = np.asarray(
            canvas.crop((x0, y0, x1, y1)), dtype=np.float32
        ) / 255.0
        main = np.asarray(
            Image.open(PCK_ROOT / "images/vfx/ui/ui_card_mask.webp")
            .convert("RGBA").resize(size, Image.LANCZOS),
            dtype=np.float32,
        ) / 255.0
        mask = np.asarray(
            Image.open(
                PCK_ROOT / "images/vfx/ui/card/ancient/ui_card_ancient_border_main.png"
            ).convert("RGBA").resize(size, Image.LANCZOS),
            dtype=np.float32,
        ) / 255.0

        sampled = screen.copy()
        sampled[..., :3] = np.clip(sampled[..., :3] + 0.15, 0.0, 1.0)
        sampled[..., 3] = mask[..., 3]
        corner = np.clip(mask[..., 1:2] * 0.2, 0.0, 1.0)
        final = sampled * (1.0 - corner) + corner
        final *= main[..., 3:4] * mask[..., 3:4]
        layer = Image.fromarray(
            np.round(np.clip(final, 0.0, 1.0) * 255).astype(np.uint8), "RGBA"
        )
        canvas.alpha_composite(layer, (x0, y0))

    def paste_additive(
        self, canvas: Image.Image, img: Image.Image,
        rect: tuple[float, float, float, float],
        color: tuple[float, float, float, float],
    ) -> None:
        """Port CanvasItemMaterial blend_mode=ADD for the Ancient highlight."""
        img, (x0, y0) = self.fitted(img, rect)
        x1, y1 = x0 + img.width, y0 + img.height
        src = np.asarray(img.convert("RGBA"), dtype=np.float32) / 255.0
        src[..., :3] *= np.asarray(color[:3], dtype=np.float32)
        src[..., 3] *= color[3]
        dst = np.asarray(
            canvas.crop((x0, y0, x1, y1)), dtype=np.float32
        ) / 255.0

        src_a, dst_a = src[..., 3:4], dst[..., 3:4]
        out_a = np.clip(dst_a + src_a, 0.0, 1.0)
        out_premul = np.clip(
            dst[..., :3] * dst_a + src[..., :3] * src_a, 0.0, 1.0
        )
        out_rgb = np.divide(
            out_premul, out_a, out=np.zeros_like(out_premul), where=out_a > 0
        )
        out = np.concatenate([out_rgb, out_a], axis=-1)
        canvas.paste(
            Image.fromarray(np.round(out * 255).astype(np.uint8), "RGBA"),
            (x0, y0),
        )

    def render(
        self, card: Card, strings: dict[str, str], keyword_strings: dict[str, str],
        upgraded: bool = False, overlay: Image.Image | None = None,
    ) -> Image.Image:
        canvas = Image.new("RGBA", self.canvas_size(), (0, 0, 0, 0))
        frame_tint = card.pool.frame
        banner_tint = f"card_banner_{RARITY_TO_BANNER.get(card.rarity, 'common')}"
        frame_kind = TYPE_TO_FRAME.get(card.type, "skill")

        ancient = card.rarity == "Ancient"
        art = Image.open(card.portrait).convert("RGBA") if card.portrait else None

        # This offset, translucent silhouette is always visible in card.tscn.
        self.paste_modulated(
            canvas, self.icon("card_frame_attack_s"), R_SHADOW,
            (0.0, 0.0, 0.0, 0.25098), keep_aspect=True,
        )

        if ancient:
            # NCard swaps the whole stack: full-bleed art clipped to the card
            # silhouette, a screen-sampling glass rim, an additive highlight,
            # and a black-modulated slab behind the description.
            if art:
                mask = self.template("ancient_portrait_mask_large")
                if mask.size != art.size:
                    mask = mask.resize(art.size, Image.LANCZOS)
                clipped = art.copy()
                clipped.putalpha(ImageChops.multiply(art.getchannel("A"), mask.getchannel("A")))
                self.paste(canvas, clipped, R_ANCIENT_PORTRAIT)
            self.paste_ancient_glass(canvas)
            self.paste_additive(
                canvas, self.template("ancient_card_border"), R_ANCIENT_BORDER,
                (1.0, 0.9776916, 0.9058309, 0.50200003),
            )
            self.paste_modulated(
                canvas, self.template(f"ancient_card_text_bg_{frame_kind}"),
                R_ANCIENT_TEXT_BG, (0.0, 0.0, 0.0, 0.66),
            )
        else:
            if art:
                self.paste(canvas, art, R_PORTRAIT)
            self.paste(canvas, self.icon(f"card_frame_{frame_kind}_s"), R_FRAME, frame_tint)

        desc_font = self.font("regular", 21 * SCALE)
        box = self.box(R_DESC)
        lines = wrap_runs(parse_bbcode(compose_text(card, keyword_strings, upgraded)),
                          desc_font, box[2] - box[0])
        draw_runs(canvas, lines, desc_font, box, leading=-3 * SCALE,
                  icons=self.sprites(card.pool.energy_color))

        if ancient:
            self.paste(canvas, self.icon("ancient_banner"), R_BANNER)
        else:
            border_kind = TYPE_TO_BORDER.get(card.type, DEFAULT_BORDER)
            self.paste(canvas, self.icon(f"card_portrait_border_{border_kind}_s"),
                       R_PORTRAIT_BORDER, banner_tint)
            if overlay is None and card.id == "INFECTION":
                overlay = self.infection_overlay(0)
            if overlay is not None:
                canvas.alpha_composite(overlay)
            self.paste(canvas, self.icon("card_banner"), R_BANNER, banner_tint)

        tx0, ty0, tx1, ty1 = self.box(R_TITLE)
        title_fill = GREEN if upgraded else CREAM
        title_outline = (
            TITLE_OUTLINE_UPGRADED if upgraded
            else TITLE_OUTLINE_BY_RARITY.get(card.rarity, TITLE_OUTLINE_COMMON)
        )
        draw_outlined(canvas, ((tx0 + tx1) / 2, (ty0 + ty1) / 2), card.title,
                      self.font("bold", 26 * SCALE), title_fill, title_outline, TITLE_STROKE)

        self.paste(canvas, self.icon("card_portrait_border_plaque_s"), R_TYPE_PLAQUE, banner_tint)
        px0, py0, px1, py1 = self.box(R_TYPE_PLAQUE)
        type_text = strings.get(f"CARD_TYPE.{card.type.upper()}", card.type)
        _layer(canvas, lambda d: d.text(((px0 + px1) / 2, (py0 + py1) / 2), type_text,
                                        font=self.font("bold", 16 * SCALE),
                                        fill=(0, 0, 0, 255), anchor="mm"), 192)

        # NCard hides the orb entirely for unplayable cards (negative cost that
        # isn't an X cost); X-cost cards show a literal "X".
        if card.costs_x or card.cost >= 0:
            self.paste(canvas, self.icon(f"energy_{card.pool.energy_color}"), R_ENERGY)
            ex0, ey0, ex1, ey1 = self.box(R_ENERGY)
            label = "X" if card.costs_x else str(card.cost)
            draw_outlined(canvas, ((ex0 + ex1) / 2, (ey0 + ey1) / 2), label,
                          self.font("bold", 32 * SCALE), CREAM, card.pool.energy_outline,
                          ENERGY_STROKE)
        return canvas

    def render_frames(self, card: Card, strings: dict[str, str],
                      keyword_strings: dict[str, str], upgraded: bool = False) -> list[Image.Image]:
        """Render the built-in animation for Ancient cards and Infection."""
        if card.id == "INFECTION":
            return [
                self.render(
                    card, strings, keyword_strings, upgraded,
                    overlay=self.infection_overlay(i),
                )
                for i in range(INFECTION_FRAME_COUNT)
            ]
        base = self.render(card, strings, keyword_strings, upgraded)
        if card.rarity != "Ancient":
            return [base]
        frames = []
        for flame in self.flame_frames():
            frame = base.copy()
            self.paste_flame(frame, flame)
            frames.append(frame)
        return frames


def save(renderer: Renderer, card: Card, strings: dict[str, str],
         keyword_strings: dict[str, str], args, stem: str, upgraded: bool) -> None:
    if args.animate and (card.rarity == "Ancient" or card.id == "INFECTION"):
        frames = [
            clear_transparent_rgb(frame.resize(OUTPUT_SIZE, Image.LANCZOS))
            for frame in renderer.render_frames(card, strings, keyword_strings, upgraded)
        ]
        duration: int | list[int]
        if card.id == "INFECTION":
            # Thirty frames over exactly two seconds: 20 × 67 ms + 10 × 66 ms.
            duration = [67, 67, 66] * 10
            # The animated parasite texture changes across most of the card.
            # Lossless WebP is ~13 MiB; quality 85 preserves the painted detail
            # while keeping the deployable result near 3 MiB.
            frames[0].save(
                args.out / f"{stem}.webp", save_all=True, append_images=frames[1:],
                duration=duration, loop=0, lossless=False, quality=85, method=4,
            )
            return
        else:
            duration = 1000 // ANCIENT_FLAME_FPS
        frames[0].save(args.out / f"{stem}.webp", save_all=True, append_images=frames[1:],
                       duration=duration, loop=0, lossless=True)
        return
    clear_transparent_rgb(
        renderer.render(card, strings, keyword_strings, upgraded).resize(
            OUTPUT_SIZE, Image.LANCZOS
        )
    ).save(
        args.out / f"{stem}.webp", "WEBP", lossless=True, method=6, exact=True
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--card", action="append", default=[], help="card id, e.g. BASH (repeatable)")
    parser.add_argument("--all", action="store_true", help="render every card")
    parser.add_argument("--out", type=Path, default=Path("BUILT CARDS"), help="output directory")
    parser.add_argument("--upgraded", action="store_true",
                        help="also render the upgraded (+) version of each card")
    parser.add_argument("--animate", action="store_true",
                        help="write Ancient cards and Infection as looping animated WebP")
    parser.add_argument("--lang", default="eng")
    args = parser.parse_args(argv)

    if not PCK_ROOT.exists() or not CARDS_NS.exists():
        parser.error("need artifacts/pck and artifacts/decompiled; run the extract steps first")

    strings = json.loads((PCK_ROOT / f"localization/{args.lang}/cards.json").read_text())
    strings |= json.loads((PCK_ROOT / f"localization/{args.lang}/gameplay_ui.json").read_text())
    keyword_strings = json.loads((PCK_ROOT / f"localization/{args.lang}/card_keywords.json").read_text())
    cards = load_cards(strings)
    print(f"parsed {len(cards)} card models", file=sys.stderr)

    with Pack(DEFAULT_PCK) as pack:
        fonts = ensure_fonts(pack)
    renderer = Renderer(fonts)

    targets = list(cards) if args.all else [c.upper() for c in args.card]
    if not targets:
        parser.error("pass --card ID or --all")

    args.out.mkdir(parents=True, exist_ok=True)
    accessors = load_accessor_map()
    wiki_path = Path("data/wiki/cards.json")
    wiki_slugs = {}
    if wiki_path.exists():
        wiki_slugs = {
            item["id"]: item["slug"]
            for item in json.loads(wiki_path.read_text()).get("cards", [])
        }
    made = upgraded = runtime_variants = 0
    for card_id in targets:
        card = cards.get(card_id)
        if card is None:
            print(f"unknown card: {card_id}", file=sys.stderr)
            continue
        stem = wiki_slugs.get(card_id, card_id.lower().replace("_", "-"))
        save(renderer, card, strings, keyword_strings, args, stem, False)
        made += 1
        if args.upgraded and (plus := upgrade(card, accessors)) is not None:
            save(renderer, plus, strings, keyword_strings, args, f"{stem}_upg", True)
            upgraded += 1
        if args.upgraded and card.id == "WITHER":
            # The wiki's existing upgrade toggle represents FakeUpgradeLevel 1.
            # Publish that contract, plus the final runtime state explicitly.
            save(
                renderer, wither_state(card, 1), strings, keyword_strings,
                args, f"{stem}_upg", True,
            )
            save(
                renderer, wither_state(card, 2), strings, keyword_strings,
                args, f"{stem}-level-3", True,
            )
            runtime_variants += 2
    summary = f"built {made} cards" + (f" + {upgraded} upgraded" if upgraded else "")
    if runtime_variants:
        summary += f" + {runtime_variants} runtime variants"
    print(f"{summary} into {args.out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
