#!/usr/bin/env python3
"""Generate wiki content from the public Spire Codex API."""

from __future__ import annotations

import argparse
import html
import json
import re
import sys
import time
import urllib.request
from collections import Counter
from pathlib import Path
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


def entity_anchor(kind: str, value: Any) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", str(value).lower()).strip("-")
    return f"{kind}-{slug}"


def entity_slug(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "-", str(value).lower()).strip("-")


def detail_link(folder: str, item: dict[str, Any], prefix: str = "") -> str:
    name = clean(item.get("name"))
    directory = f"{folder}/" if folder else ""
    return f"[{name}]({prefix}{directory}{entity_slug(item.get('id'))}.md)"


def page_header(name: Any, description: Any) -> list[str]:
    page_name = clean(name)
    page_description = clean(description) or f"Slay the Spire 2 reference for {page_name}."
    return [
        "---",
        f"title: {json.dumps(page_name)}",
        f"description: {json.dumps(page_description[:155])}",
        "---",
        "",
        f"# {page_name}",
        "",
    ]


def media_path(kind: str, item: dict[str, Any]) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", str(item.get("id", "")).lower()).strip("-")
    return f"/media/{kind}/{slug}.webp"


def image_tag(url: Any, name: Any, kind: str) -> str:
    source = html.escape(str(url), quote=True)
    alt = html.escape(clean(name), quote=True)
    label = html.escape(f"View full image: {clean(name)}", quote=True)
    return (
        f'<a class="wiki-image-link" href="{source}" target="_blank" rel="noopener" '
        f'aria-label="{label}" title="{label}">'
        f'<img class="wiki-image wiki-image--{kind}" src="{source}" alt="{alt}" '
        'loading="lazy" decoding="async"></a>'
    )


def anchored_name(kind: str, item: dict[str, Any]) -> str:
    anchor = entity_anchor(kind, item.get("id"))
    return f'<a id="{anchor}"></a>**{clean(item.get("name"))}**'


def anchored_detail_name(folder: str, kind: str, item: dict[str, Any]) -> str:
    anchor = entity_anchor(kind, item.get("id"))
    return f'<a id="{anchor}"></a>**{detail_link(folder, item)}**'


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


def rarity_heading(rarity: str) -> str:
    return "Other Relics" if rarity == "Relic" else rarity.replace("Relic", "Relics")


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


def build_cards(cards: list[dict[str, Any]]) -> str:
    counts = Counter(card.get("color") for card in cards)
    type_counts = Counter(card.get("type") for card in cards)
    rarity_counts = Counter(card.get("rarity") for card in cards)
    ordered_colors = [color for color in COLOR_ORDER if counts.get(color)]
    ordered_colors += sorted(color for color in counts if color not in COLOR_ORDER)

    lines = [
        "# Cards",
        "",
        "All card data on this page is sourced from the [Spire Codex API](https://spire-codex.com/docs), using the English `/api/cards` endpoint.",
        "",
        "## Summary",
        "",
        f"- **Total cards:** {len(cards)}",
        "- **By color:** " + ", ".join(f"{title(color)}: {counts[color]}" for color in ordered_colors),
        "- **By type:** " + ", ".join(f"{kind}: {type_counts[kind]}" for kind in TYPE_ORDER if type_counts.get(kind)),
        "- **By rarity:** " + ", ".join(f"{rarity}: {rarity_counts[rarity]}" for rarity in RARITY_ORDER if rarity_counts.get(rarity)),
        "",
        "## Quick Index",
        "",
    ]
    for color in ordered_colors:
        lines.append(f"- [{title(color)}](#{color}) ({counts[color]})")
    lines.append("")

    for color in ordered_colors:
        group = [card for card in cards if card.get("color") == color]
        group.sort(
            key=lambda card: (
                sort_key(card.get("rarity"), RARITY_ORDER),
                sort_key(card.get("type"), TYPE_ORDER),
                card.get("compendium_order") or 9999,
                card.get("name") or "",
            )
        )
        lines += [
            f"## {title(color)}",
            "",
            "| Image | Card | Cost | Type | Rarity | Effect | Upgrade |",
            "|---|---|---:|---|---|---|---|",
        ]
        for card in group:
            lines.append(
                f"| {image_tag(media_path('cards', card), card.get('name'), 'card')} | "
                f"{anchored_detail_name('cards', 'card', card)} | "
                f"{card_cost(card)} | {clean(card.get('type'))} | "
                f"{clean(card.get('rarity'))} | {clean(card.get('description'))} | "
                f"{clean(card.get('upgrade_description')) or '-'} |"
            )
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def build_relics(relics: list[dict[str, Any]]) -> str:
    items = sorted(
        relics,
        key=lambda relic: (
            sort_key(relic.get("rarity"), RELIC_RARITY_ORDER),
            relic.get("compendium_order") or 9999,
            relic.get("name") or "",
        ),
    )
    rarities = Counter(item.get("rarity") for item in items)
    pools = Counter(item.get("pool") for item in items)

    lines = [
        "# Relics",
        "",
        "All relic data on this page is sourced from the [Spire Codex API](https://spire-codex.com/docs), using the English `/api/relics` endpoint. This first pass includes every relic currently returned by that source.",
        "",
        "## Summary",
        "",
        f"- **Total relics:** {len(items)}",
        "- **By rarity:** "
        + ", ".join(f"{rarity.replace(' Relic', '')}: {rarities[rarity]}" for rarity in RELIC_RARITY_ORDER if rarities.get(rarity)),
        "- **By pool:** " + ", ".join(f"{title(pool)}: {pools[pool]}" for pool in POOL_ORDER if pools.get(pool)),
        "",
        "Merchant price is shown as `base (min-max)` when Spire Codex provides the shop range.",
        "",
        "## Quick Index",
        "",
    ]
    for rarity in RELIC_RARITY_ORDER:
        if rarities.get(rarity):
            heading = rarity_heading(rarity)
            lines.append(f"- [{heading}](#{heading.lower().replace(' ', '-')}) ({rarities[rarity]})")
    lines.append("")

    for rarity in RELIC_RARITY_ORDER:
        group = [item for item in items if item.get("rarity") == rarity]
        if not group:
            continue
        lines += [
            f"## {rarity_heading(rarity)}",
            "",
            "| Image | Relic | Pool | Effect | Price |",
            "|---|---|---|---|---|",
        ]
        for item in group:
            lines.append(
                f"| {image_tag(media_path('relics', item), item.get('name'), 'relic')} | "
                f"{anchored_detail_name('relics', 'relic', item)} | {title(item.get('pool'))} | "
                f"{clean(item.get('description'))} | {price(item)} |"
            )
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def build_characters(characters: list[dict[str, Any]], cards: list[dict[str, Any]], relics: list[dict[str, Any]]) -> str:
    card_items = {card["id"]: card for card in cards}
    relic_items = {relic["id"]: relic for relic in relics}
    for card in cards:
        card_items.setdefault(re.sub(r"[^a-z0-9]", "", card["id"].lower()), card)
    for relic in relics:
        relic_items.setdefault(re.sub(r"[^a-z0-9]", "", relic["id"].lower()), relic)

    def resolve(items: dict[str, dict[str, Any]], value: str) -> dict[str, Any] | None:
        return items.get(value) or items.get(re.sub(r"[^a-z0-9]", "", value.lower()))

    def entity_link(folder: str, item: dict[str, Any] | None, fallback: str) -> str:
        if not item:
            return clean(fallback)
        return detail_link(folder, item)

    def card_link(value: str) -> str:
        return entity_link("cards", resolve(card_items, value), value)

    def relic_link(value: str) -> str:
        return entity_link("relics", resolve(relic_items, value), value)

    def character_order(character: dict[str, Any]) -> Any:
        key = str(character.get("id", "")).lower()
        return COLOR_ORDER.index(key) if key in COLOR_ORDER else character.get("name", "")

    sorted_characters = sorted(characters, key=character_order)
    lines = [
        "# Characters",
        "",
        "Character data is sourced from the [Spire Codex API](https://spire-codex.com/docs), using the English `/api/characters` endpoint. Full transparent character artwork is provided by [Untapped.gg](https://sts2.untapped.gg/en/characters).",
        "",
        "## Summary",
        "",
        "| Image | Character | HP | Gold | Energy | Orb Slots | Unlocks After | Starting Relics |",
        "|---|---|---:|---:|---:|---:|---|---|",
    ]
    for character in sorted_characters:
        relic_list = ", ".join(relic_link(item) for item in character.get("starting_relics", [])) or "-"
        lines.append(
            f"| {image_tag(media_path('characters', character), character.get('name'), 'character-thumb')} | "
            f"**{detail_link('characters', character)}** | {character.get('starting_hp') or '-'} | "
            f"{character.get('starting_gold') or '-'} | {character.get('max_energy') or '-'} | "
            f"{character.get('orb_slots') if character.get('orb_slots') is not None else '-'} | "
            f"{clean(character.get('unlocks_after')) or '-'} | {relic_list} |"
        )
    lines.append("")

    for character in sorted_characters:
        lines += [
            f"## {clean(character.get('name'))}",
            "",
            '<div class="wiki-character">',
            image_tag(media_path("characters", character), character.get("name"), "character"),
            '<div class="wiki-character__copy">',
            clean(character.get("description")),
            "</div>",
            "</div>",
            "",
        ]
        lines += ["| Stat | Value |", "|---|---|"]
        lines.append(f"| Starting HP | {character.get('starting_hp') or '-'} |")
        lines.append(f"| Starting Gold | {character.get('starting_gold') or '-'} |")
        lines.append(f"| Energy | {character.get('max_energy') or '-'} |")
        lines.append(f"| Orb Slots | {character.get('orb_slots') if character.get('orb_slots') is not None else '-'} |")
        lines.append(f"| Unlocks After | {clean(character.get('unlocks_after')) or '-'} |")
        lines.append(f"| Starting Relics | {', '.join(relic_link(item) for item in character.get('starting_relics', [])) or '-'} |")
        lines += ["", "### Starting Deck", ""]
        deck = Counter(character.get("starting_deck", []))
        for card_id, count in sorted(deck.items(), key=lambda entry: card_link(entry[0])):
            linked_name = card_link(card_id)
            lines.append(f"- {count}x {linked_name}" if count > 1 else f"- {linked_name}")
        quotes = character.get("quotes") or {}
        if quotes:
            lines += ["", "### Notable Quotes", ""]
            for key in ["gold_monologue", "aroma_principle", "banter_alive", "banter_dead", "unlock_text"]:
                if quotes.get(key):
                    lines.append(f"- **{title(key)}:** {clean(quotes[key])}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def build_enemies(monsters: list[dict[str, Any]]) -> str:
    counts = Counter(monster.get("type") for monster in monsters)
    lines = [
        "# Enemies",
        "",
        "Enemy data is sourced from the [Spire Codex API](https://spire-codex.com/docs), using the English `/api/monsters` endpoint.",
        "",
        "## Summary",
        "",
        f"- **Total enemies:** {len(monsters)}",
        "- **By type:** " + ", ".join(f"{kind}: {counts[kind]}" for kind in MONSTER_TYPE_ORDER if counts.get(kind)),
        "",
        "## Enemy Table",
        "",
        "| Image | Enemy | Type | HP | Encounters | Moves | Pattern |",
        "|---|---|---|---:|---|---|---|",
    ]
    monsters.sort(key=lambda monster: (sort_key(monster.get("type"), MONSTER_TYPE_ORDER), clean(monster.get("name"))))
    for monster in monsters:
        encounters = monster.get("encounters") or []
        encounter_names = sorted({clean(encounter.get("encounter_name")) for encounter in encounters if encounter.get("encounter_name")})
        pattern = clean((monster.get("attack_pattern") or {}).get("description")) or "-"
        lines.append(
            f"| {image_tag(media_path('enemies', monster), monster.get('name'), 'enemy')} | "
            f"{anchored_detail_name('enemies', 'enemy', monster)} | {clean(monster.get('type'))} | "
            f"{monster_hp(monster)} | "
            f"{', '.join(encounter_names) or '-'} | {first_moves(monster)} | {pattern} |"
        )
    return "\n".join(lines).rstrip() + "\n"


def build_card_page(card: dict[str, Any], cards: list[dict[str, Any]]) -> str:
    description = clean(card.get("description"))
    lines = page_header(card.get("name"), f"{description} {title(card.get('color'))} {card.get('type')} card.")
    lines += [
        '<div class="wiki-entity-hero">',
        image_tag(media_path("cards", card), card.get("name"), "card-detail"),
        '<div class="wiki-entity-hero__details">',
        description or "No description is currently available.",
        "",
        "| Property | Value |",
        "|---|---|",
        f"| Character / Pool | {title(card.get('color'))} |",
        f"| Type | {clean(card.get('type'))} |",
        f"| Rarity | {clean(card.get('rarity'))} |",
        f"| Cost | {card_cost(card)} |",
        f"| Target | {clean(card.get('target')) or '-'} |",
        "</div>",
        "</div>",
        "",
        "## Upgrade",
        "",
        clean(card.get("upgrade_description")) or "No standard upgrade text is available.",
    ]
    keywords = card.get("keywords") or []
    if keywords:
        lines += ["", "## Keywords", "", ", ".join(f"`{clean(keyword)}`" for keyword in keywords)]
    variants = card.get("type_variants") or {}
    if variants:
        lines += ["", "## Variants", ""]
        for variant_name, variant in variants.items():
            lines += [
                f"### {title(variant_name)}",
                "",
                clean(variant.get("description")) or "No description available.",
            ]
            riders = variant.get("riders") or []
            for rider in riders:
                lines.append(f"- **{clean(rider.get('name'))}:** {clean(rider.get('description'))}")
            lines.append("")
    related = sorted(
        (
            item
            for item in cards
            if item.get("id") != card.get("id")
            and item.get("color") == card.get("color")
            and item.get("type") == card.get("type")
        ),
        key=lambda item: clean(item.get("name")),
    )[:8]
    if related:
        lines += ["", "## Related Cards", "", "- " + "\n- ".join(detail_link("", item) for item in related)]
    lines += ["", "[Back to all cards](../cards.md)", ""]
    return "\n".join(lines).rstrip() + "\n"


def build_relic_page(relic: dict[str, Any], relics: list[dict[str, Any]]) -> str:
    description = clean(relic.get("description"))
    lines = page_header(relic.get("name"), f"{description} {relic.get('rarity')} relic.")
    lines += [
        '<div class="wiki-entity-hero">',
        image_tag(media_path("relics", relic), relic.get("name"), "relic-detail"),
        '<div class="wiki-entity-hero__details">',
        description or "No description is currently available.",
        "",
        "| Property | Value |",
        "|---|---|",
        f"| Rarity | {clean(relic.get('rarity'))} |",
        f"| Pool | {title(relic.get('pool'))} |",
        f"| Merchant Price | {price(relic)} |",
        "</div>",
        "</div>",
    ]
    flavor = clean(relic.get("flavor"))
    notes = relic.get("notes") or []
    if flavor:
        lines += ["", "## Flavor", "", flavor]
    if notes:
        lines += ["", "## Notes", ""] + [f"- {clean(note)}" for note in notes]
    related = sorted(
        (
            item
            for item in relics
            if item.get("id") != relic.get("id")
            and item.get("rarity") == relic.get("rarity")
            and item.get("pool") == relic.get("pool")
        ),
        key=lambda item: clean(item.get("name")),
    )[:8]
    if related:
        lines += ["", "## Related Relics", "", "- " + "\n- ".join(detail_link("", item) for item in related)]
    lines += ["", "[Back to all relics](../relics.md)", ""]
    return "\n".join(lines).rstrip() + "\n"


def build_character_page(
    character: dict[str, Any], cards: list[dict[str, Any]], relics: list[dict[str, Any]]
) -> str:
    card_items = {re.sub(r"[^a-z0-9]", "", item["id"].lower()): item for item in cards}
    relic_items = {re.sub(r"[^a-z0-9]", "", item["id"].lower()): item for item in relics}

    def find(items: dict[str, dict[str, Any]], value: str) -> dict[str, Any] | None:
        return items.get(re.sub(r"[^a-z0-9]", "", value.lower()))

    description = clean(character.get("description"))
    lines = page_header(character.get("name"), description)
    lines += [
        '<div class="wiki-entity-hero wiki-entity-hero--character">',
        image_tag(media_path("characters", character), character.get("name"), "character-detail"),
        '<div class="wiki-entity-hero__details">',
        description,
        "",
        "| Stat | Value |",
        "|---|---|",
        f"| Starting HP | {character.get('starting_hp') or '-'} |",
        f"| Starting Gold | {character.get('starting_gold') or '-'} |",
        f"| Energy | {character.get('max_energy') or '-'} |",
        f"| Orb Slots | {character.get('orb_slots') if character.get('orb_slots') is not None else '-'} |",
        f"| Unlocks After | {clean(character.get('unlocks_after')) or '-'} |",
        "</div>",
        "</div>",
        "",
        "## Starting Deck",
        "",
    ]
    deck = Counter(character.get("starting_deck", []))
    for card_id, count in sorted(deck.items()):
        item = find(card_items, card_id)
        name = detail_link("cards", item, "../") if item else clean(card_id)
        lines.append(f"- {count}x {name}" if count > 1 else f"- {name}")
    lines += ["", "## Starting Relics", ""]
    for relic_id in character.get("starting_relics", []):
        item = find(relic_items, relic_id)
        lines.append(f"- {detail_link('relics', item, '../') if item else clean(relic_id)}")
    quotes = character.get("quotes") or {}
    if quotes:
        lines += ["", "## Notable Quotes", ""]
        for key in ["gold_monologue", "aroma_principle", "banter_alive", "banter_dead", "unlock_text"]:
            if quotes.get(key):
                lines.append(f"- **{title(key)}:** {clean(quotes[key])}")
    lines += ["", "[Back to all characters](../characters.md)", ""]
    return "\n".join(lines).rstrip() + "\n"


def build_enemy_page(monster: dict[str, Any]) -> str:
    pattern = clean((monster.get("attack_pattern") or {}).get("description"))
    lines = page_header(monster.get("name"), f"{monster.get('type')} enemy with {monster_hp(monster)} HP. {pattern}")
    lines += [
        '<div class="wiki-entity-hero">',
        image_tag(media_path("enemies", monster), monster.get("name"), "enemy-detail"),
        '<div class="wiki-entity-hero__details">',
        "| Property | Value |",
        "|---|---|",
        f"| Type | {clean(monster.get('type'))} |",
        f"| HP | {monster_hp(monster)} |",
        f"| Pattern | {pattern or '-'} |",
        "</div>",
        "</div>",
        "",
        "## Moves",
        "",
        "| Move | Intent | Damage | Block | Heal |",
        "|---|---|---|---|---|",
    ]
    for move in monster.get("moves") or []:
        lines.append(
            f"| {clean(move.get('name') or move.get('id'))} | {clean(move.get('intent')) or '-'} | "
            f"{move_value(move.get('damage'), 'damage') or '-'} | "
            f"{move_value(move.get('block'), 'block') or '-'} | "
            f"{move_value(move.get('heal'), 'heal') or '-'} |"
        )
    encounters = monster.get("encounters") or []
    if encounters:
        lines += ["", "## Encounters", "", "| Encounter | Room | Act |", "|---|---|---|"]
        for encounter in encounters:
            lines.append(
                f"| {clean(encounter.get('encounter_name')) or '-'} | "
                f"{clean(encounter.get('room_type')) or '-'} | {encounter.get('act') or '-'} |"
            )
    lines += ["", "[Back to all enemies](../enemies.md)", ""]
    return "\n".join(lines).rstrip() + "\n"


def build_guides(guides: list[dict[str, Any]]) -> str:
    lines = [
        "# Guides",
        "",
        "Guide listings are sourced from the [Spire Codex API](https://spire-codex.com/docs), using the English `/api/guides` endpoint. External guide links open on their original sites.",
        "",
        "## Guide Index",
        "",
        "| Guide | Author | Difficulty | Character | Updated | Summary |",
        "|---|---|---|---|---|---|",
    ]
    guides.sort(key=lambda guide: (guide.get("date") or "", guide.get("title") or ""), reverse=True)
    for guide in guides:
        title_text = clean(guide.get("title"))
        title_cell = f"[{title_text}]({guide['website']})" if guide.get("website") else f"**{title_text}**"
        updated = clean(guide.get("updated") or guide.get("date"))
        lines.append(
            f"| {title_cell} | {clean(guide.get('author'))} | {title(guide.get('difficulty'))} | "
            f"{title(guide.get('character'))} | {updated} | {clean(guide.get('summary'))} |"
        )
    tag_counts = Counter(tag for guide in guides for tag in guide.get("tags", []))
    lines += ["", "## Tags", "", ", ".join(f"`{clean(tag)}` ({count})" for tag, count in sorted(tag_counts.items()))]
    return "\n".join(lines).rstrip() + "\n"


def patch_counts(text: str, stats: dict[str, Any], guide_count: int) -> str:
    replacements = {
        "Base and upgraded card data, organized for quick lookup.": f"{stats['cards']} cards with base and upgraded text, organized for quick lookup.",
        "Relic effects, synergies, and pick considerations.": f"{stats['relics']} relic effects, pools, and merchant price ranges.",
        "Playable characters, starter kits, and defining mechanics.": f"{stats['characters']} playable characters, starter kits, and defining mechanics.",
        "Boss and encounter notes for cleaner pathing decisions.": f"{stats['monsters']} enemies with HP, encounters, moves, and attack patterns.",
        "Beginner fundamentals and advanced deckbuilding ideas.": f"{guide_count} curated external guides from Spire Codex.",
    }
    for old, new in replacements.items():
        text = text.replace(old, new)
    return text


def generate() -> dict[Path, str]:
    cards = fetch_json("cards")
    characters = fetch_json("characters")
    relics = fetch_json("relics")
    monsters = fetch_json("monsters")
    guides = fetch_json("guides")
    stats = fetch_json("stats", lang=False)

    files = {
        Path("docs/cards.md"): build_cards(cards),
        Path("docs/characters.md"): build_characters(characters, cards, relics),
        Path("docs/enemies.md"): build_enemies(monsters),
        Path("docs/guides.md"): build_guides(guides),
        Path("docs/relics.md"): build_relics(relics),
    }
    for card in cards:
        files[Path("docs/cards") / f"{entity_slug(card['id'])}.md"] = build_card_page(card, cards)
    for character in characters:
        files[Path("docs/characters") / f"{entity_slug(character['id'])}.md"] = build_character_page(
            character, cards, relics
        )
    for monster in monsters:
        files[Path("docs/enemies") / f"{entity_slug(monster['id'])}.md"] = build_enemy_page(monster)
    for relic in relics:
        files[Path("docs/relics") / f"{entity_slug(relic['id'])}.md"] = build_relic_page(relic, relics)
    index = Path("docs/index.md").read_text()
    files[Path("docs/index.md")] = patch_counts(index, stats, len(guides))
    landing = Path("landing/index.html").read_text()
    landing = landing.replace(
        "Cards, relics, enemies, characters, and strategy notes for faster run planning as Early Access changes.",
        f"{stats['cards']} cards, {stats['relics']} relics, {stats['monsters']} enemies, characters, and strategy notes for faster run planning.",
    )
    landing = landing.replace("Base and upgraded card data in a searchable wiki.", f"{stats['cards']} searchable cards with base and upgrade text.")
    landing = landing.replace("Effects, synergies, and pick considerations.", f"{stats['relics']} relic effects, pools, and price ranges.")
    landing = landing.replace("Encounter and boss notes for cleaner pathing.", f"{stats['monsters']} enemies with encounters, moves, and patterns.")
    landing = landing.replace("Fundamentals, deckbuilding, and advanced ideas.", f"{len(guides)} curated external guides from Spire Codex.")
    files[Path("landing/index.html")] = landing
    return files


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="fail if generated files differ")
    args = parser.parse_args()

    generated = generate()
    changed = []
    generated_directories = [Path("docs/cards"), Path("docs/characters"), Path("docs/enemies"), Path("docs/relics")]
    expected_paths = set(generated)
    stale = sorted(
        path
        for directory in generated_directories
        if directory.exists()
        for path in directory.glob("*.md")
        if path not in expected_paths
    )
    for path, text in generated.items():
        current = path.read_text() if path.exists() else None
        if current != text:
            changed.append(path)
            if not args.check:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(text)

    for path in stale:
        changed.append(path)
        if not args.check:
            path.unlink()

    if args.check and changed:
        print("Generated content is out of date:", file=sys.stderr)
        for path in changed:
            print(f"  {path}", file=sys.stderr)
        return 1

    if changed:
        print("Updated generated content:")
        for path in changed:
            print(f"  {path}")
    else:
        print("Generated content is up to date.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
