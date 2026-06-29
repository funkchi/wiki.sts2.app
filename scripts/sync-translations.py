#!/usr/bin/env python3
"""Fetch Spire Codex language exports and merge translations into wiki JSON."""

from __future__ import annotations

import argparse
import html
import importlib.util
import io
import json
import re
import time
import urllib.request
import zipfile
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "scripts" / "spire_codex.py"

_spec = importlib.util.spec_from_file_location("spire_codex", SOURCE)
sc = importlib.util.module_from_spec(_spec)
assert _spec and _spec.loader
_spec.loader.exec_module(sc)

DEFAULT_LANG = "zhs"
EXPORT_BASE = "https://spire-codex.com/api/exports"

LANG_CONFIG = {
    "zhs": {
        "translation_key": "zhHans",
        "energy": "能量",
        "star": "星",
        "unknown": "未知",
        "pool_labels": {
            "shared": "通用",
            "ironclad": "铁甲战士",
            "silent": "静默猎手",
            "defect": "故障机器人",
            "necrobinder": "亡灵束缚者",
            "regent": "摄政者",
        },
    },
    "jpn": {
        "translation_key": "ja",
        "energy": "エナジー",
        "star": "スター",
        "unknown": "不明",
        "pool_labels": {
            "shared": "共通",
            "ironclad": "アイアンクラッド",
            "silent": "サイレント",
            "defect": "ディフェクト",
            "necrobinder": "ネクロバインダー",
            "regent": "リージェント",
        },
    },
}


def clean_i18n(value: Any, config: dict[str, Any]) -> str:
    if value is None:
        return ""
    text = html.unescape(str(value))
    text = re.sub(r"\[energy:(\d+)\]", rf"\1 {config['energy']}", text)
    text = re.sub(r"\[star:(\d+)\]", rf"\1 {config['star']}", text)
    text = re.sub(r"\[/?[^\]]+\]", "", text)
    text = re.sub(r"<[^>]+>", "", text)
    text = text.replace("\u00a0", "")
    text = text.replace("\r", " ").replace("\n", " ")
    return re.sub(r"\s+", " ", text).strip()


def fetch_export(lang: str) -> dict[str, list[dict[str, Any]]]:
    request = urllib.request.Request(
        f"{EXPORT_BASE}/{lang}",
        headers={"User-Agent": "wiki.sts2.app translation sync"},
    )
    for attempt in range(3):
        try:
            with urllib.request.urlopen(request, timeout=45) as response:
                archive = zipfile.ZipFile(io.BytesIO(response.read()))
                return {
                    name.removesuffix(".json"): json.loads(archive.read(name))
                    for name in archive.namelist()
                    if name.endswith(".json")
                }
        except Exception:
            if attempt == 2:
                raise
            time.sleep(1 + attempt)
    raise RuntimeError(f"Unable to fetch language export {lang}")


def by_id(items: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {str(item.get("id")): item for item in items if item.get("id")}


def norm_id(value: Any) -> str:
    return re.sub(r"[^a-z0-9]", "", str(value).lower())


def by_norm_id(items: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {norm_id(item.get("id")): item for item in items if item.get("id")}


def load_payload(kind: str) -> dict[str, Any]:
    return json.loads((ROOT / "data" / "wiki" / f"{kind}.json").read_text())


def write_payload(kind: str, payload: dict[str, Any]) -> None:
    target = ROOT / "data" / "wiki" / f"{kind}.json"
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")


def card_translation(card: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
    return {
        "name": clean_i18n(card.get("name"), config),
        "description": clean_i18n(card.get("description"), config),
        "upgradeDescription": clean_i18n(card.get("upgrade_description"), config),
        "type": clean_i18n(card.get("type"), config),
        "rarity": clean_i18n(card.get("rarity"), config),
        "target": clean_i18n(card.get("target"), config),
        "keywords": [clean_i18n(k, config) for k in (card.get("keywords") or [])],
    }


def character_translation(
    character: dict[str, Any],
    translated_cards: dict[str, dict[str, Any]],
    translated_relics: dict[str, dict[str, Any]],
    config: dict[str, Any],
) -> dict[str, Any]:
    quotes = []
    for key, value in (character.get("quotes") or {}).items():
        if value:
            quotes.append({"key": key, "text": clean_i18n(value, config)})

    return {
        "name": clean_i18n(character.get("name"), config),
        "character": clean_i18n(character.get("name"), config),
        "description": clean_i18n(character.get("description"), config),
        "unlocksAfter": clean_i18n(character.get("unlocks_after"), config),
        "startingDeck": [
            {
                "id": card_id,
                "name": clean_i18n((translated_cards.get(norm_id(card_id)) or {}).get("name"), config)
                or clean_i18n(card_id, config),
            }
            for card_id in (character.get("starting_deck") or [])
        ],
        "startingRelics": [
            {
                "id": relic_id,
                "name": clean_i18n((translated_relics.get(norm_id(relic_id)) or {}).get("name"), config)
                or clean_i18n(relic_id, config),
            }
            for relic_id in (character.get("starting_relics") or [])
        ],
        "quotes": quotes,
    }


def relic_translation(relic: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
    pool_raw = relic.get("pool")
    return {
        "name": clean_i18n(relic.get("name"), config),
        "description": clean_i18n(relic.get("description"), config),
        "rarity": clean_i18n(relic.get("rarity"), config),
        "pool": config["pool_labels"].get(str(pool_raw), clean_i18n(pool_raw, config)),
        "flavor": clean_i18n(relic.get("flavor"), config),
        "notes": [clean_i18n(n, config) for n in (relic.get("notes") or [])],
    }


def enemy_translation(monster: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
    moves = [
        {
            "name": clean_i18n(move.get("name") or move.get("id"), config),
            "intent": clean_i18n(move.get("intent"), config),
            "damage": sc.move_value(move.get("damage"), "damage") or "",
            "block": sc.move_value(move.get("block"), "block") or "",
            "heal": sc.move_value(move.get("heal"), "heal") or "",
        }
        for move in (monster.get("moves") or [])
    ]
    encounters = [
        {
            "name": clean_i18n(encounter.get("encounter_name"), config) or "-",
            "roomType": clean_i18n(encounter.get("room_type"), config) or "-",
            "act": encounter.get("act"),
        }
        for encounter in (monster.get("encounters") or [])
    ]
    return {
        "name": clean_i18n(monster.get("name"), config),
        "type": clean_i18n(monster.get("type"), config) or config["unknown"],
        "pattern": clean_i18n((monster.get("attack_pattern") or {}).get("description"), config),
        "moves": moves,
        "encounters": encounters,
        "encounterNames": sorted({e["name"] for e in encounters if e["name"] != "-"}),
        "movesSummary": sc.first_moves(monster),
    }


def merge(kind: str, source: dict[str, dict[str, Any]], translation_key: str, transform) -> tuple[int, int]:
    payload = load_payload(kind)
    items = payload[kind]
    matched = 0
    for item in items:
        translated = source.get(item["id"])
        if not translated:
            continue
        item.setdefault("translations", {})[translation_key] = transform(translated)
        matched += 1
    write_payload(kind, payload)
    return matched, len(items) - matched


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--lang", default=DEFAULT_LANG, choices=sorted(LANG_CONFIG), help="Spire Codex export language code")
    args = parser.parse_args()
    config = LANG_CONFIG[args.lang]
    translation_key = config["translation_key"]

    export = fetch_export(args.lang)
    cards = by_id(export["cards"])
    characters = by_id(export["characters"])
    relics = by_id(export["relics"])
    monsters = by_id(export["monsters"])
    cards_by_norm = by_norm_id(export["cards"])
    relics_by_norm = by_norm_id(export["relics"])

    stats = {
        "cards": merge("cards", cards, translation_key, lambda card: card_translation(card, config)),
        "characters": merge(
            "characters",
            characters,
            translation_key,
            lambda character: character_translation(character, cards_by_norm, relics_by_norm, config),
        ),
        "relics": merge("relics", relics, translation_key, lambda relic: relic_translation(relic, config)),
        "enemies": merge("enemies", monsters, translation_key, lambda monster: enemy_translation(monster, config)),
    }

    for kind, (matched, missing) in stats.items():
        print(f"merged {matched} {kind} translations ({missing} missing)")


if __name__ == "__main__":
    main()
