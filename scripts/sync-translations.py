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
        "move_labels": {"damage": "伤害", "block": "格挡", "heal": "治疗", "more": "个额外行动"},
        "pool_labels": {
            "shared": "通用",
            "ironclad": "铁甲战士",
            "silent": "静默猎手",
            "defect": "故障机器人",
            "necrobinder": "亡灵束缚者",
            "regent": "摄政者",
        },
        "keyword_terms": [
            {"id": "ETERNAL", "label": "永恒", "aliases": ["永恒"]},
            {"id": "ETHEREAL", "label": "虚无", "aliases": ["虚无"]},
            {"id": "EXHAUST", "label": "消耗", "aliases": ["消耗"]},
            {"id": "INNATE", "label": "固有", "aliases": ["固有"]},
            {"id": "RETAIN", "label": "保留", "aliases": ["保留"]},
            {"id": "SLY", "label": "奇巧", "aliases": ["奇巧"]},
            {"id": "UNPLAYABLE", "label": "不能被打出", "aliases": ["不能被打出", "不可打出"]},
            {"id": "VULNERABLE", "label": "易伤", "aliases": ["易伤"]},
            {"id": "WEAK", "label": "虚弱", "aliases": ["虚弱"]},
            {"id": "FRAIL", "label": "脆弱", "aliases": ["脆弱"]},
            {"id": "POISON", "label": "中毒", "aliases": ["中毒", "毒"]},
            {"id": "DOOM", "label": "厄运", "aliases": ["厄运"]},
            {"id": "STRENGTH", "label": "力量", "aliases": ["力量"]},
            {"id": "DEXTERITY", "label": "敏捷", "aliases": ["敏捷"]},
            {"id": "THORNS", "label": "荆棘", "aliases": ["荆棘"]},
            {"id": "REGEN", "label": "再生", "aliases": ["再生"]},
            {"id": "FOCUS", "label": "集中", "aliases": ["集中"]},
        ],
    },
    "jpn": {
        "translation_key": "ja",
        "energy": "エナジー",
        "star": "スター",
        "unknown": "不明",
        "move_labels": {"damage": "ダメージ", "block": "ブロック", "heal": "回復", "more": "件の追加行動"},
        "pool_labels": {
            "shared": "共通",
            "ironclad": "アイアンクラッド",
            "silent": "サイレント",
            "defect": "ディフェクト",
            "necrobinder": "ネクロバインダー",
            "regent": "リージェント",
        },
        "keyword_terms": [
            {"id": "ETERNAL", "label": "永劫", "aliases": ["永劫"]},
            {"id": "ETHEREAL", "label": "エセリアル", "aliases": ["エセリアル"]},
            {"id": "EXHAUST", "label": "廃棄", "aliases": ["廃棄"]},
            {"id": "INNATE", "label": "天賦", "aliases": ["天賦"]},
            {"id": "RETAIN", "label": "保留", "aliases": ["保留"]},
            {"id": "SLY", "label": "スライ", "aliases": ["スライ"]},
            {"id": "UNPLAYABLE", "label": "プレイ不可", "aliases": ["プレイ不可"]},
            {"id": "VULNERABLE", "label": "弱体", "aliases": ["弱体"]},
            {"id": "WEAK", "label": "脱力", "aliases": ["脱力"]},
            {"id": "FRAIL", "label": "脆弱", "aliases": ["脆弱"]},
            {"id": "POISON", "label": "毒", "aliases": ["毒"]},
            {"id": "DOOM", "label": "破滅", "aliases": ["破滅"]},
            {"id": "STRENGTH", "label": "筋力", "aliases": ["筋力"]},
            {"id": "DEXTERITY", "label": "敏捷", "aliases": ["敏捷"]},
            {"id": "THORNS", "label": "トゲ", "aliases": ["トゲ"]},
            {"id": "REGEN", "label": "再生", "aliases": ["再生"]},
            {"id": "FOCUS", "label": "集中力", "aliases": ["集中力", "集中"]},
        ],
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


def keyword_names(items: list[dict[str, Any]], config: dict[str, Any]) -> dict[str, str]:
    return {str(item.get("id")): clean_i18n(item.get("name"), config) for item in items if item.get("id")}


def load_payload(kind: str) -> dict[str, Any]:
    return json.loads((ROOT / "data" / "wiki" / f"{kind}.json").read_text())


def write_payload(kind: str, payload: dict[str, Any]) -> None:
    target = ROOT / "data" / "wiki" / f"{kind}.json"
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")


def localized_keywords(card: dict[str, Any], config: dict[str, Any], official_keywords: dict[str, str]) -> list[str]:
    text = " ".join(
        [
            clean_i18n(card.get("description"), config),
            clean_i18n(card.get("upgrade_description"), config),
        ]
    )
    field_values = {clean_i18n(k, config) for k in (card.get("keywords") or [])}
    field_ids = {norm_id(k) for k in (card.get("keywords") or [])}
    out: list[str] = []
    seen: set[str] = set()
    for term in config["keyword_terms"]:
        term_id = str(term["id"])
        label = official_keywords.get(term_id) or term["label"]
        aliases = [label, *term.get("aliases", [])]
        matched_field = norm_id(term_id) in field_ids or label in field_values
        matched_text = any(alias and alias in text for alias in aliases)
        if (matched_field or matched_text) and label not in seen:
            out.append(label)
            seen.add(label)
    return out


def card_translation(card: dict[str, Any], config: dict[str, Any], official_keywords: dict[str, str]) -> dict[str, Any]:
    return {
        "name": clean_i18n(card.get("name"), config),
        "description": clean_i18n(card.get("description"), config),
        "upgradeDescription": clean_i18n(card.get("upgrade_description"), config),
        "type": clean_i18n(card.get("type"), config),
        "rarity": clean_i18n(card.get("rarity"), config),
        "target": clean_i18n(card.get("target"), config),
        "keywords": localized_keywords(card, config, official_keywords),
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
        "movesSummary": localized_moves_summary(monster, config),
    }


def localized_moves_summary(monster: dict[str, Any], config: dict[str, Any], limit: int = 3) -> str:
    parts = []
    moves = monster.get("moves") or []
    labels = config["move_labels"]
    for move in moves[:limit]:
        name = clean_i18n(move.get("name") or move.get("id"), config)
        intent = clean_i18n(move.get("intent"), config)
        details = []
        for key, label in [("damage", labels["damage"]), ("block", labels["block"]), ("heal", labels["heal"])]:
            rendered = sc.move_value(move.get(key), label)
            if rendered:
                details.append(rendered)
        suffix = f" ({', '.join(details)})" if details else ""
        parts.append(f"{name}: {intent}{suffix}" if intent else f"{name}{suffix}")
    extra = len(moves) - limit
    if extra > 0:
        parts.append(f"+{extra} {labels['more']}")
    return "; ".join(parts) or "-"


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
    official_keywords = keyword_names(export.get("keywords") or [], config)

    stats = {
        "cards": merge("cards", cards, translation_key, lambda card: card_translation(card, config, official_keywords)),
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
