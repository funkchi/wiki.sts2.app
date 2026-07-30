# Slay the Spire 2 Wiki — [sts2.app](https://sts2.app)

A community reference for **Slay the Spire 2**: every card, relic, enemy, character,
event and enhancement, with strategy guides and the game's own patch notes.

**→ [sts2.app](https://sts2.app)** · [Cards](https://sts2.app/docs/cards/) ·
[Relics](https://sts2.app/docs/relics/) · [Enemies](https://sts2.app/docs/enemies/) ·
[Characters](https://sts2.app/docs/characters/) · [Events](https://sts2.app/docs/events/) ·
[Guides](https://sts2.app/docs/guides/) · [Patch Notes](https://sts2.app/docs/patches/)

Also available in [简体中文](https://sts2.app/zhs/) and [日本語](https://sts2.app/jpn/).

## What's covered

| Section | Entries | |
|---|---:|---|
| [Cards](https://sts2.app/docs/cards/) | 577 | Cost, type, rarity, target, upgrade values, related cards |
| [Relics](https://sts2.app/docs/relics/) | 296 | Rarity, pool, merchant price, notes |
| [Enemies](https://sts2.app/docs/enemies/) | 115 | HP, move sets with damage and block, encounters by act |
| [Events](https://sts2.app/docs/events/) | 66 | Choice flows, requirements, branching results |
| [Enhancements](https://sts2.app/docs/enhancements/) | 22 | Enchantments and what they apply to |
| [Characters](https://sts2.app/docs/characters/) | 5 | Starting deck and relics, HP, energy, orb slots |
| [Guides](https://sts2.app/docs/guides/) | 4 | Deckbuilding, scaling, archetypes, boss prep |

The game is in Early Access, so numbers move between patches. Pages are rebuilt
against the current build rather than hand-maintained.

## How the media is made

Card, relic and character art is rendered from the installed game rather than
scraped, so it stays in step with each patch. That's the more interesting half of
this repo:

- **`scripts/pck_extract.py`** — reads Godot 4.5 `.pck` archives. Parses the pack
  directory, verifies every file against its stored MD5, and unwraps `.ctex`
  textures (lossless WebP passthrough, or a DDS wrapper for BC7/DXT).
- **`scripts/pck_render.py`** — decodes atlas sheets and slices the shared
  TexturePacker atlases into individually named icons, restoring each sprite's
  trim margin so icon sets line up.
- **`scripts/build_cards.py`** — composites card images the way the game's
  `card.tscn` does: geometry from the scene, frame and banner tints by
  reimplementing the game's HSV shader, stats from the card models, and text from
  the localization files.
- **`scripts/spine_binary.py`** — a **clean-room reader for Spine 4.2 binary
  skeletons**, written against the published binary layout. No Spine runtime is
  linked or shipped. Parses bones, slots, constraints, skins and animation
  timelines.
- **`scripts/spine_render.py`** — poses those skeletons and rasterises region and
  weighted-mesh attachments to produce the animated character idles on the
  character pages.

If you're here for the Spine parser specifically, `spine_binary.py` documents
several details that differ from older format descriptions — mesh triangle counts
are derived rather than stored, triangle indices are varints, and bones and slots
carry extra editor fields.

Text is available in 15 languages in the game data; the site currently ships
English, Simplified Chinese and Japanese.

## Stack

- [Astro](https://astro.build) + [Starlight](https://starlight.astro.build)
- [Cloudflare Pages](https://pages.cloudflare.com), with media served from R2
- Content data as committed JSON under `data/wiki/`
- Python 3 for the asset pipeline (`Pillow`, `numpy`)

## Running locally

```bash
npm install
npm run dev
```

`npm run build` produces a static site in `dist/`. The asset pipeline needs a
local install of the game and is not required to build or develop the site —
generated media is treated as a build artifact, not committed source.

## Credits

Huge thanks to the [Spire Codex](https://github.com/ptrlrd/spire-codex) project,
which this wiki's data pipeline grew out of and still cross-references.

Slay the Spire 2 is made by [Mega Crit](https://www.megacrit.com/). All game art,
names and text are their property, reproduced here for reference. This is an
unofficial fan project and is not affiliated with or endorsed by Mega Crit.

## Contributing

Corrections and additions are welcome — open an issue or a pull request. If
you're reporting a data error, a link to the affected page helps.
