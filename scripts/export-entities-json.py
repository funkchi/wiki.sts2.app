#!/usr/bin/env python3
"""Export Spire Codex entities to JSON for the Astro site.

Field mapping lives in scripts/spire_codex.py (shared data layer). The JSON output
replaces the Markdown the legacy pipeline produced.
"""

from __future__ import annotations

import importlib.util
import json
import re
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "scripts" / "spire_codex.py"

_spec = importlib.util.spec_from_file_location("spire_codex", SOURCE)
sc = importlib.util.module_from_spec(_spec)
assert _spec and _spec.loader
_spec.loader.exec_module(sc)


def _enemy_hp(monster: dict) -> str:
    minimum = monster.get("min_hp")
    maximum = monster.get("max_hp")
    asc_min = monster.get("min_hp_ascension")
    asc_max = monster.get("max_hp_ascension")
    if minimum is None and maximum is None:
        return "-"
    base = (
        str(minimum if minimum is not None else maximum)
        if minimum == maximum or maximum is None
        else f"{minimum}-{maximum}"
    )
    if asc_min is None and asc_max is None:
        return base
    asc = (
        str(asc_min if asc_min is not None else asc_max)
        if asc_min == asc_max or asc_max is None
        else f"{asc_min}-{asc_max}"
    )
    return f"{base} (A9+ {asc})"


def _norm(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", str(value).lower())


def _cost_label(card: dict) -> str:
    cost = card.get("cost")
    star = card.get("star_cost")
    if cost in (-1, -2):
        return "Unplayable"
    if card.get("is_x_star_cost"):
        return "X★"
    if card.get("is_x_cost"):
        return "X"
    if star is not None:
        return f"{cost}/{star}★"
    if cost is None:
        return "-"
    return str(cost)


def _cost_raw(card: dict) -> dict:
    return {
        "cost": card.get("cost"),
        "starCost": card.get("star_cost"),
        "isX": bool(card.get("is_x_cost")),
        "isXStar": bool(card.get("is_x_star_cost")),
    }


def _upgrade_image(card: dict) -> str | None:
    return card.get("image_url_card_upg") or None


# Vocabulary of in-game keywords/buffs/debuffs to surface for search + highlight.
KEYWORDS = [
    "Exhaust", "Ethereal", "Retain", "Innate", "Sly", "Eternal",
    "Vulnerable", "Weak", "Frail", "Poison", "Doom",
    "Strength", "Dexterity", "Thorns", "Regen", "Focus",
]


def _matched_keywords(card: dict) -> list[str]:
    text = (
        sc.clean(card.get("description"))
        + " "
        + sc.clean(card.get("upgrade_description"))
    ).lower()
    field = {sc.clean(k).lower() for k in (card.get("keywords") or [])}
    out = []
    for kw in KEYWORDS:
        kl = kw.lower()
        if kl in field or re.search(r"\b" + re.escape(kl) + r"\b", text):
            out.append(kw)
    return out


def _related(card: dict, cards: list[dict]) -> list[str]:
    matches = sorted(
        (
            c
            for c in cards
            if c.get("id") != card.get("id")
            and c.get("color") == card.get("color")
            and c.get("type") == card.get("type")
        ),
        key=lambda c: sc.clean(c.get("name")),
    )[:8]
    return [sc.entity_slug(c.get("id")) for c in matches]


def export_cards() -> list[dict]:
    cards = sc.fetch_json("cards")
    out = []
    for card in cards:
        out.append(
            {
                "id": card.get("id"),
                "slug": sc.entity_slug(card.get("id")),
                "name": sc.clean(card.get("name")),
                "color": card.get("color"),
                "character": sc.title(card.get("color")),
                "type": sc.clean(card.get("type")),
                "rarity": sc.clean(card.get("rarity")),
                "cost": _cost_label(card),
                "costRaw": _cost_raw(card),
                "target": sc.clean(card.get("target")) or "-",
                "description": sc.clean(card.get("description")),
                "upgradeDescription": sc.clean(card.get("upgrade_description")),
                "keywords": [sc.clean(k) for k in (card.get("keywords") or [])],
                "matchedKeywords": _matched_keywords(card),
                "image": sc.media_path("cards", card),
                "imageUpg": _upgrade_image(card),
                "related": _related(card, cards),
            }
        )
    return out


_QUOTE_KEYS = ["gold_monologue", "aroma_principle", "banter_alive", "banter_dead", "unlock_text"]


def export_characters() -> list[dict]:
    characters = sc.fetch_json("characters")
    cards = sc.fetch_json("cards")
    relics = sc.fetch_json("relics")
    card_by_id = {c.get("id"): c for c in cards}
    card_by_norm = {_norm(c.get("id")): c for c in cards}
    relic_by_norm = {_norm(r.get("id")): r for r in relics}

    def find_card(value: str) -> dict | None:
        return card_by_id.get(value) or card_by_norm.get(_norm(value))

    def find_relic(value: str) -> dict | None:
        return relic_by_norm.get(_norm(value))

    out = []
    for ch in characters:
        deck_counter = Counter(ch.get("starting_deck", []))
        deck = []
        for card_id, count in sorted(deck_counter.items()):
            c = find_card(card_id)
            deck.append(
                {
                    "slug": sc.entity_slug(c.get("id")) if c else sc.entity_slug(card_id),
                    "name": sc.clean(c.get("name")) if c else sc.clean(card_id),
                    "count": count,
                }
            )
        relics_out = []
        for rid in ch.get("starting_relics", []):
            r = find_relic(rid)
            relics_out.append(
                {
                    "slug": sc.entity_slug(r.get("id")) if r else sc.entity_slug(rid),
                    "name": sc.clean(r.get("name")) if r else sc.clean(rid),
                }
            )
        quotes = []
        q = ch.get("quotes") or {}
        for key in _QUOTE_KEYS:
            if q.get(key):
                quotes.append({"label": sc.title(key), "text": sc.clean(q[key])})

        out.append(
            {
                "id": ch.get("id"),
                "slug": sc.entity_slug(ch.get("id")),
                "name": sc.clean(ch.get("name")),
                "color": str(ch.get("id", "")).lower(),
                "character": sc.title(ch.get("id")),
                "description": sc.clean(ch.get("description")),
                "image": sc.media_path("characters", ch),
                "icon": f"/media/characters/{sc.entity_slug(ch.get('id'))}_icon.webp",
                "startingHp": ch.get("starting_hp"),
                "startingGold": ch.get("starting_gold"),
                "maxEnergy": ch.get("max_energy"),
                "orbSlots": ch.get("orb_slots"),
                "unlocksAfter": sc.clean(ch.get("unlocks_after")) or "-",
                "startingDeck": deck,
                "startingRelics": relics_out,
                "quotes": quotes,
            }
        )

    order = {color: i for i, color in enumerate(sc.COLOR_ORDER)}
    out.sort(key=lambda x: order.get(str(x.get("color")).lower(), 999))
    return out


def export_relics() -> list[dict]:
    relics = sc.fetch_json("relics")
    items = sorted(
        relics,
        key=lambda r: (
            sc.sort_key(r.get("rarity"), sc.RELIC_RARITY_ORDER),
            r.get("compendium_order") or 9999,
            sc.clean(r.get("name")) or "",
        ),
    )
    out = []
    for r in items:
        related = sorted(
            (
                x
                for x in relics
                if x.get("id") != r.get("id")
                and x.get("rarity") == r.get("rarity")
                and x.get("pool") == r.get("pool")
            ),
            key=lambda x: sc.clean(x.get("name")),
        )[:8]
        out.append(
            {
                "id": r.get("id"),
                "slug": sc.entity_slug(r.get("id")),
                "name": sc.clean(r.get("name")),
                "description": sc.clean(r.get("description")),
                "rarity": sc.clean(r.get("rarity")),
                "pool": sc.title(r.get("pool")),
                "poolRaw": r.get("pool"),
                "price": sc.price(r),
                "flavor": sc.clean(r.get("flavor")),
                "notes": [sc.clean(n) for n in (r.get("notes") or [])],
                "image": sc.media_path("relics", r),
                "related": [sc.entity_slug(x.get("id")) for x in related],
            }
        )
    return out


def export_enemies() -> list[dict]:
    monsters = sc.fetch_json("monsters")
    items = sorted(
        monsters,
        key=lambda m: (sc.sort_key(m.get("type"), sc.MONSTER_TYPE_ORDER), sc.clean(m.get("name")) or ""),
    )
    out = []
    for m in items:
        encounters = m.get("encounters") or []
        enc_names = sorted(
            {sc.clean(e.get("encounter_name")) for e in encounters if e.get("encounter_name")}
        )
        acts = sorted(
            {str(e.get("act")) for e in encounters if e.get("act") is not None},
            key=lambda a: (len(a), a),
        )
        pattern = sc.clean((m.get("attack_pattern") or {}).get("description"))
        moves = [
            {
                "name": sc.clean(mv.get("name") or mv.get("id")),
                "intent": sc.clean(mv.get("intent")),
                "damage": sc.move_value(mv.get("damage"), "damage") or "",
                "block": sc.move_value(mv.get("block"), "block") or "",
                "heal": sc.move_value(mv.get("heal"), "heal") or "",
            }
            for mv in (m.get("moves") or [])
        ]
        out.append(
            {
                "id": m.get("id"),
                "slug": sc.entity_slug(m.get("id")),
                "name": sc.clean(m.get("name")),
                "type": sc.clean(m.get("type")) or "Unknown",
                "hp": _enemy_hp(m),
                "pattern": pattern or "-",
                "moves": moves,
                "encounters": [
                    {
                        "name": sc.clean(e.get("encounter_name")) or "-",
                        "roomType": sc.clean(e.get("room_type")) or "-",
                        "act": e.get("act"),
                    }
                    for e in encounters
                ],
                "encounterNames": enc_names,
                "acts": acts,
                "movesSummary": sc.first_moves(m),
                "image": sc.media_path("enemies", m),
            }
        )
    return out


def _write(kind: str, items: list[dict]) -> None:
    out_dir = ROOT / "data" / "wiki"
    out_dir.mkdir(parents=True, exist_ok=True)
    payload = {"schemaVersion": 1, "kind": kind, "count": len(items), kind: items}
    target = out_dir / f"{kind}.json"
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
    print(f"wrote {len(items)} {kind} -> {target.relative_to(ROOT)}")


def main() -> None:
    _write("cards", export_cards())
    _write("characters", export_characters())
    _write("relics", export_relics())
    _write("enemies", export_enemies())


if __name__ == "__main__":
    main()
