#!/usr/bin/env python3
"""Spire Codex API client + entity field helpers (no Markdown rendering).

Shared by the JSON export pipeline; intentionally free of any site/SSG code.
"""

from __future__ import annotations

import html
import json
import re
import time
import urllib.request
from typing import Any


API_BASE = "https://spire-codex.com/api"

COLOR_ORDER = [
    "ironclad",
    "silent",
    "defect",
    "necrobinder",
    "regent",
    "colorless",
    "event",
    "token",
    "quest",
    "curse",
    "status",
]

RARITY_ORDER = ["Basic", "Common", "Uncommon", "Rare", "Ancient", "Special", "Curse"]

TYPE_ORDER = ["Attack", "Skill", "Power", "Status", "Curse"]

RELIC_RARITY_ORDER = [
    "Starter Relic",
    "Common Relic",
    "Uncommon Relic",
    "Rare Relic",
    "Shop Relic",
    "Event Relic",
    "Ancient Relic",
    "Relic",
]

POOL_ORDER = ["shared", "ironclad", "silent", "defect", "necrobinder", "regent"]

MONSTER_TYPE_ORDER = ["Boss", "Elite", "Normal", "Minion", "Event", "Unknown"]

def fetch_json(endpoint: str, lang: bool = True) -> Any:
    suffix = "?lang=eng" if lang else ""
    request = urllib.request.Request(
        f"{API_BASE}/{endpoint}{suffix}",
        headers={"User-Agent": "wiki.sts2.app content sync"},
    )
    for attempt in range(3):
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                return json.loads(response.read())
        except Exception:
            if attempt == 2:
                raise
            time.sleep(1 + attempt)
    raise RuntimeError(f"Unable to fetch {endpoint}")


def clean(text: Any) -> str:
    if text is None:
        return ""
    value = html.unescape(str(text))
    value = re.sub(r"\[energy:(\d+)\]", lambda match: f"{match.group(1)} Energy", value)
    value = re.sub(r"\[star:(\d+)\]", lambda match: f"{match.group(1)} Star", value)
    value = re.sub(r"\[/?[^\]]+\]", "", value)
    value = re.sub(r"<[^>]+>", "", value)
    replacements = {
        "’": "'",
        "‘": "'",
        "“": '"',
        "”": '"',
        "—": "-",
        "–": "-",
        "…": "...",
        "→": "->",
        "×": "x",
        "\u00a0": "",
    }
    for old, new in replacements.items():
        value = value.replace(old, new)
    value = value.replace("\r", " ").replace("\n", " ")
    value = re.sub(r"\s+", " ", value).strip()
    return value.replace("|", r"\|")


def title(value: Any) -> str:
    if not value:
        return "-"
    mapping = {
        "ironclad": "Ironclad",
        "silent": "Silent",
        "defect": "Defect",
        "necrobinder": "Necrobinder",
        "regent": "Regent",
        "colorless": "Colorless",
        "event": "Event",
        "token": "Token",
        "quest": "Quest",
        "curse": "Curse",
        "status": "Status",
        "shared": "Shared",
    }
    text = str(value)
    return mapping.get(text, text.replace("_", " ").title())


def sort_key(value: Any, order: list[str]) -> int:
    return order.index(value) if value in order else len(order) + 1


def entity_slug(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "-", str(value).lower()).strip("-")


def media_path(kind: str, item: dict[str, Any]) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", str(item.get("id", "")).lower()).strip("-")
    if kind == "characters":
        return f"https://cdn.spire-codex.com/characters/combat_{slug}.webp"
    return f"/media/{kind}/{slug}.webp"


def card_cost(card: dict[str, Any]) -> str:
    if card.get("is_x_cost"):
        return "X"
    if card.get("is_x_star_cost"):
        return "X Star"
    if card.get("star_cost") is not None:
        return f"{card['star_cost']} Star"
    cost = card.get("cost")
    if cost == -2:
        return "Unplayable"
    return "-" if cost is None else str(cost)


def price(relic: dict[str, Any]) -> str:
    merchant_price = relic.get("merchant_price") or {}
    base = merchant_price.get("base")
    low = merchant_price.get("min")
    high = merchant_price.get("max")
    if base is None:
        return "-"
    if low is not None and high is not None:
        return f"{base} ({low}-{high})"
    return str(base)


def monster_hp(monster: dict[str, Any]) -> str:
    minimum = monster.get("min_hp")
    maximum = monster.get("max_hp")
    asc_min = monster.get("min_hp_ascension")
    asc_max = monster.get("max_hp_ascension")
    if minimum is None and maximum is None:
        return "-"
    base = str(minimum if minimum is not None else maximum) if minimum == maximum or maximum is None else f"{minimum}-{maximum}"
    if asc_min is not None or asc_max is not None:
        asc = str(asc_min if asc_min is not None else asc_max) if asc_min == asc_max or asc_max is None else f"{asc_min}-{asc_max}"
        return f"{base} (Asc {asc})"
    return base


def move_value(value: Any, label: str) -> str | None:
    if value is None:
        return None
    if isinstance(value, dict):
        normal = value.get("normal")
        ascension = value.get("ascension")
        hit_count = value.get("hit_count")
        if normal is None and ascension is None:
            return None
        core = str(normal if normal is not None else ascension)
        if hit_count:
            core = f"{core}x{hit_count}"
        if ascension is not None and ascension != normal:
            asc_core = str(ascension)
            if hit_count:
                asc_core = f"{asc_core}x{hit_count}"
            core = f"{core} (Asc {asc_core})"
        return f"{core} {label}"
    return f"{value} {label}"


def first_moves(monster: dict[str, Any], limit: int = 3) -> str:
    parts = []
    moves = monster.get("moves") or []
    for move in moves[:limit]:
        name = clean(move.get("name") or move.get("id"))
        intent = clean(move.get("intent"))
        details = []
        for key, label in [("damage", "dmg"), ("block", "block"), ("heal", "heal")]:
            rendered = move_value(move.get(key), label)
            if rendered:
                details.append(rendered)
        suffix = f" ({', '.join(details)})" if details else ""
        parts.append(f"{name}: {intent}{suffix}" if intent else f"{name}{suffix}")
    extra = len(moves) - limit
    if extra > 0:
        parts.append(f"+{extra} more")
    return "; ".join(parts) or "-"


