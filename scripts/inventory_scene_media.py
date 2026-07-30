#!/usr/bin/env python3
"""Inventory enemy/character scene dependencies for the Spine capture phase."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from pck_extract import DEFAULT_PCK, Pack  # noqa: E402

PCK_ROOT = Path("artifacts/pck")
SCENE_ROOT = PCK_ROOT / "scenes/creature_visuals"
WIKI_ROOT = Path("data/wiki")


def inspect_scene(path: Path) -> dict[str, object]:
    text = path.read_text(errors="replace")
    skeletons = sorted(
        set(
            re.findall(
                r'path="res://(animations/[^"]+_skel_data\.tres)"',
                text,
            )
        )
    )
    phobia = sorted(
        set(re.findall(r'path="res://([^"]*phobia[^"]*)"', text, re.I))
    )
    return {
        "scene": path.stem,
        "path": str(path),
        "spineSprites": len(re.findall(r'type="SpineSprite"', text)),
        "skeletonResources": skeletons,
        "shaders": len(re.findall(r'type="Shader"', text)),
        "particles": len(
            re.findall(r'type="(?:CPU|GPU)Particles2D"', text)
        ),
        "phobiaAssets": phobia,
        "previewAnimations": sorted(
            set(re.findall(r'preview_animation = "([^"]+)"', text))
        ),
        "previewSkins": sorted(
            set(re.findall(r'preview_skin = "([^"]+)"', text))
        ),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--out",
        type=Path,
        default=Path("artifacts/generated-media/scene-media-inventory.json"),
    )
    args = parser.parse_args(argv)

    scenes = [
        inspect_scene(path) for path in sorted(SCENE_ROOT.glob("*.tscn"))
    ]
    by_name = {scene["scene"]: scene for scene in scenes}
    enemies = json.loads((WIKI_ROOT / "enemies.json").read_text())["enemies"]
    characters = json.loads(
        (WIKI_ROOT / "characters.json").read_text()
    )["characters"]

    enemy_mapping = []
    for enemy in enemies:
        expected = enemy["id"].lower()
        candidates = [expected] if expected in by_name else []
        note = None
        if enemy["id"] == "DECIMILLIPEDE_SEGMENT":
            candidates = [
                "decimillipede_segment_front",
                "decimillipede_segment_middle",
                "decimillipede_segment_back",
            ]
            note = "one wiki entity represents three runtime segment classes"
        enemy_mapping.append(
            {
                "id": enemy["id"],
                "slug": enemy["slug"],
                "scenes": candidates,
                "note": note,
            }
        )

    character_mapping = [
        {
            "id": character["id"],
            "slug": character["slug"],
            "scenes": (
                [character["id"].lower()]
                if character["id"].lower() in by_name
                else []
            ),
        }
        for character in characters
    ]

    with Pack(DEFAULT_PCK) as pack:
        imports = pack.import_map()
        skeleton_imports = {
            source: baked
            for source, baked in imports.items()
            if source.endswith(".skel")
        }
        atlas_imports = {
            source: baked
            for source, baked in imports.items()
            if source.endswith(".atlas")
        }
        engine_version = list(pack.engine_version)
        pack_entries = len(pack.entries)

    missing_enemy_scenes = [
        mapping["id"] for mapping in enemy_mapping if not mapping["scenes"]
    ]
    missing_character_scenes = [
        mapping["id"] for mapping in character_mapping if not mapping["scenes"]
    ]
    errors = []
    if missing_enemy_scenes:
        errors.append(
            f"enemy models missing scene mappings: {missing_enemy_scenes}"
        )
    if missing_character_scenes:
        errors.append(
            f"character models missing scene mappings: {missing_character_scenes}"
        )

    report = {
        "schemaVersion": 1,
        "kind": "first-party-scene-media-inventory",
        "source": {
            "godotVersion": engine_version,
            "packEntries": pack_entries,
            "skeletonImports": len(skeleton_imports),
            "atlasImports": len(atlas_imports),
            "monsterSkeletonImports": sum(
                source.startswith("animations/monsters/")
                for source in skeleton_imports
            ),
            "characterSkeletonImports": sum(
                source.startswith("animations/characters/")
                for source in skeleton_imports
            ),
        },
        "inventory": {
            "creatureScenes": len(scenes),
            "wikiEnemies": len(enemies),
            "wikiCharacters": len(characters),
            "exactEnemySceneMappings": sum(
                len(mapping["scenes"]) == 1 for mapping in enemy_mapping
            ),
            "representativeChoiceMappings": sum(
                len(mapping["scenes"]) > 1 for mapping in enemy_mapping
            ),
            "characterSceneMappings": sum(
                bool(mapping["scenes"]) for mapping in character_mapping
            ),
            "scenesWithSpine": sum(
                scene["spineSprites"] > 0 for scene in scenes
            ),
            "scenesWithoutSpine": sum(
                scene["spineSprites"] == 0 for scene in scenes
            ),
            "multiSpineScenes": sum(
                scene["spineSprites"] > 1 for scene in scenes
            ),
            "uniqueSkeletonResources": len(
                {
                    resource
                    for scene in scenes
                    for resource in scene["skeletonResources"]
                }
            ),
            "scenesWithShaders": sum(scene["shaders"] > 0 for scene in scenes),
            "scenesWithParticles": sum(
                scene["particles"] > 0 for scene in scenes
            ),
            "scenesWithPhobiaAssets": sum(
                bool(scene["phobiaAssets"]) for scene in scenes
            ),
        },
        "enemyMapping": enemy_mapping,
        "characterMapping": character_mapping,
        "scenes": scenes,
        "proofOfConcept": [
            {
                "case": "single Spine idle",
                "scene": "frog_knight",
                "reason": "one skeleton, idle_loop, no shader, particles, or phobia layer",
            },
            {
                "case": "dynamic skin",
                "scene": "kin_follower",
                "reason": "model assembles a custom randomized hair skin",
            },
            {
                "case": "phobia alternative",
                "scene": "wriggler",
                "reason": "direct phobia texture replaces a Spine creature",
            },
            {
                "case": "complex multi-part composition",
                "scene": "decimillipede",
                "reason": "eight SpineSprite nodes, four skeleton resources, particles, and shader VFX",
            },
        ],
        "captureGate": {
            "preferred": (
                "Godot 4.5.1 capture harness using the packaged Spine GDExtension "
                "and imported .spskel/.spatlas resources"
            ),
            "fallback": "version-matched Spine runtime using scene transforms and preview metadata",
            "blockers": [
                "extract baked .spskel/.spatlas resources into an isolated capture project",
                "load scenes without depending on the game's compiled C# node scripts",
                "define deterministic idle time, viewport, scale, and transparent bounds",
                "choose a representative Decimillipede segment poster",
                "apply explicit phobia-mode policy before publishing sensitive creatures",
            ],
        },
        "missingEnemyScenes": missing_enemy_scenes,
        "missingCharacterScenes": missing_character_scenes,
        "errors": errors,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(
        f"inventoried {len(scenes)} creature scenes for {len(enemies)} enemies "
        f"and {len(characters)} characters; {len(errors)} errors; report: {args.out}",
        file=sys.stderr,
    )
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
