# First-party media replacement plan

## Goal

Replace artwork fetched from Spire Codex with deterministic media built from the
installed Slay the Spire 2 PCK, while keeping the site's stable `/media/...`
URLs and preserving animated or scene-composited visuals where the game uses
them.

The PCK, decompiled model metadata, localization, scenes, materials, shaders,
and animation resources are the authoritative inputs. Generated media remains
an ignored build artifact; only manifests, renderer code, and compact visual
fixtures belong in Git.

## Implementation status — 2026-07-28

The local, non-production portion of Phases 0–2 is now implemented:

- `build_cards.py` produces 1,155 stable-key WebP files: 596 base models, 557
  normal upgrades, and Wither's two explicit runtime states.
- All 19 Ancient cards use the decompiled glass-mask shader inputs, additive
  rim, modulated text background, full capture viewport, and 10-frame/10 fps
  flame. Infection uses its 30-frame/15 fps built-in overlay.
- `validate_built_cards.py` reports zero missing wiki portraits, unresolved
  descriptions, clipped viewports, stale files, size-budget violations, or
  animation metadata errors.
- `build_direct_media.py` produces 296 primary relics, seven explicit
  stateful relic variants, and all 22 enchantments. Every primary texture is a
  finished PCK asset; none currently needs a beta fallback.
- The `/media` function accepts the new `enchantments` namespace.
- `plan_first_party_cutover.py` verifies all 1,435 page-required keys and
  produces a read-only upload/rewrite plan. It currently calls for 1,442
  uploads including variants, 540 upgraded-card URL rewrites, and 22
  enchantment URL rewrites.

Production R2 and wiki datasets remain unchanged. Promotion is intentionally
deferred until the versioned staging upload and object-by-object verification
step is explicitly authorized.

### Cutover session — 2026-07-28 (second pass)

- The text resolver now implements the game's SmartFormat semantics for
  `cond` (comparison and truthy forms), numeric `choose` matching, and `{}`
  scoping to the enclosing formatter's variable. This corrected One-Two
  Punch's upgraded render, Lightning Rod, Burst, and Sovereign Blade; the five
  affected cards were re-rendered and revalidated (1,155 renders, zero
  errors).
- `update_card_text.py` rewrites wiki descriptions from the PCK templates for
  English, zhHans, and ja. It rewrote 411 fields, preserved the wiki's
  `upgradeDescription: ''` unchanged-by-upgrade convention, and kept existing
  text for 96 fields whose templates reach an unresolved CalculatedVar `X`
  (17 cards, listed in `artifacts/generated-media/card-text-report.json`).
- `build_direct_media.py` gained the `events` namespace: all 66 events now
  build (55 direct `images/events/<id>.png` plates, 11 explicit mappings for
  the scene-composited Ancients, The Architect's background plate, Fake
  Merchant's rug, and The Lantern Key). Full-screen plates are resampled to
  1200 px wide and encoded lossy q82 under a mean-error gate; the set totals
  1.24 MiB. Neow and Tezcatara have no flat plate showing the Ancient and use
  their finished map-node icons until the Phase 3 capture harness exists.
- The `/media` function accepts `events`; the two external star-icon
  references now use the extracted PCK icon at `/images/star-icon.webp`.
- All 633 dataset URL rewrites are applied: 540 upgraded cards, 22
  enchantments, 66 events, and 5 characters. No wiki image field references an
  external host any more; the site builds (3,280 pages) with only ads and
  analytics as external requests.
- `stage_first_party_media.py` drives the R2 gate (stage → verify-staging →
  promote → verify-stable → finalize) with resumable state and per-object
  sha256 verification of 1,508 uploads.
- **The R2 cutover is complete.** All 1,508 objects were staged to
  `staging/2026-07-28/`, sha256-verified, promoted to stable keys, and
  re-verified with zero failures; live `/media` responses were spot-checked
  byte-exact. `data/media-manifest.json` now records 1,628 items (1,508
  first-party plus 115 enemies and 5 characters); `cards/follow-through.webp`
  was dropped (card no longer exists) and the staging prefix is retained for
  rollback. The only remaining step is deploying the site build so pages
  reference the new upgraded-card, enchantment, event, and character URLs.

## Current dependency inventory

| Kind | Wiki entities | Current delivery | Known gap |
| --- | ---: | --- | --- |
| Cards | 577 | Base images use `/media/cards`; upgrades use external CDN URLs | 540 upgrade URLs remain external; local renderer sees 596 models |
| Relics | 296 | `/media/relics` | R2 objects were populated from the external API/CDN |
| Enemies | 115 | `/media/enemies` | R2 objects were populated from the external API/CDN |
| Characters | 5 | External CDN URLs | R2 has five objects, but the wiki does not use them |
| Enchantments | 22 | External static URLs | Not accepted by the `/media` function or tracked in the R2 manifest |
| Events | 66 | Nine external images | No first-party event media namespace |

The current media manifest has 989 objects: 576 cards, 293 relics, 115 enemies,
and five characters. Those counts must be reconciled with the wiki datasets
before any production replacement.

## Build architecture

Use one pipeline with category-specific renderers:

1. Record the game PCK hash, Godot version, extraction date, and renderer
   version.
2. Extract and resolve source imports with `pck_extract.py`.
3. Build a normalized inventory from decompiled model paths and scene
   references. Record intended, beta-fallback, variant, missing, and animated
   assets explicitly.
4. Render into a staging directory with stable keys such as
   `cards/wraith-form.webp` and `relics/vajra.webp`.
5. Validate counts, dimensions, alpha, animation metadata, file-size budgets,
   and visual fixtures.
6. Generate a manifest containing source paths and hashes, output hashes,
   renderer version, dimensions, frame count, duration, and fallback status.
7. Upload to a versioned R2 staging prefix. Promote to stable keys only after
   the complete category passes.
8. Rewrite wiki image fields to `/media/...`, build the whole site, and verify
   every referenced object with `HEAD` requests.

Renderer families:

- **Direct textures:** relics, enchantment icons, powers, potions, event art,
  and phobia-mode images. Resolve finished art before beta fallback and convert
  losslessly or at a visually reviewed WebP quality.
- **Card compositor:** frames, portrait borders, banners, localized text,
  upgrades, Ancient glass/shaders, inline resource glyphs, and built-in
  overlays such as Infection.
- **Spine/scene renderer:** enemies and character combat art. Extract the
  `.spskel`, atlas, scene transform, skin, and canonical idle animation from
  each `creature_visuals/*.tscn`. Render a deterministic idle timestamp and,
  where worthwhile, an optional bounded animation.
- **Scene overlays:** card afflictions and other shader-driven assets. Port
  simple shaders to the compositor; use a controlled Godot capture harness for
  effects that depend on screen textures, particles, or complex scene state.

## Phased rollout

### Phase 0 — Pipeline and manifest foundation

- Add a first-party source mode instead of teaching `sync-r2-media.py` to
  redownload generated files from an external API.
- Add namespaces for `enchantments`, `events`, `potions`, and `powers` to the
  media function as they become populated.
- Generate an inventory/diff report that blocks unexplained missing,
  duplicated, or stale entities.
- Add a small golden-image suite covering transparent edges, beta fallback,
  tint materials, text wrapping, and animation metadata.

Exit gate: identical inputs produce identical manifests and byte-stable static
outputs; no production objects are changed.

### Phase 1 — Finish cards

- Correct the Ancient glass overlay, additive border treatment, text
  background modulation, flame scale, and canvas bounds.
- Render direct `{singleStarIcon}` placeholders and audit every unresolved
  localization construct.
- Include Infection's static and animated built-in overlay.
- Decide how to publish Wither's runtime levels (`wither1`–`wither3`) without
  pretending they are normal upgrades.
- Audit any future `HasBuiltInOverlay`, affliction, or portrait overrides from
  decompiled metadata instead of maintaining a handwritten exception list.
- Produce base and upgraded WebP files under the same first-party namespace.

Exit gate: every publishable card has art; all intended upgrades exist; every
animation has the expected frame count, duration, loop, and static poster;
representative cards match game captures.

Status: **local exit gate passed**. Wither level 2 retains the existing wiki
upgrade-toggle contract at `wither_upg.webp`; level 3 is exported separately
as `wither-level-3.webp`. Mad Science uses its canonical Attack portrait and
description, while its dynamically assigned Skill/Power/rider states remain
documented runtime variants rather than invented upgrades.

### Phase 2 — Relics and enchantments

- Resolve `RelicModel.BigIconPath`, then beta fallback, for all wiki relics.
- Resolve `EnchantmentModel.IntendedIconPath`, then beta fallback, for all 22
  enchantments.
- Preserve native transparent bounds and generate consistent display boxes
  without baking CSS padding into the images.
- Add `relics` and `enchantments` to the first-party manifest and rewrite every
  enchantment URL to `/media/enchantments/...`.

Exit gate: 296 relic and 22 enchantment pages use only first-party URLs and
match a sampled set of source assets pixel-for-pixel before WebP encoding.

Status: **build/validation gate passed; URL cutover pending staging upload**.
All 318 primary files match their decoded PCK sources pixel-for-pixel after
lossless WebP encoding. Yummy Cookie's five character variants and Looming
Fruit's two save-dependent variants are also exported with explicit keys.

### Phase 3 — Enemies and characters

- Extract all Spine skeleton binaries and atlases referenced by the 126
  `creature_visuals` scenes.
- Read each scene's skin, idle animation, position, scale, bounds, and
  phobia-mode alternative.
- Build a renderer proof of concept on one simple enemy, one multi-part boss,
  one skin-swapping enemy, and Wriggler's phobia alternative.
- Prefer a deterministic game/Godot capture harness if it can load the packed
  Spine runtime reliably; otherwise use a version-matched Spine 4.2 runtime.
- Render static idle posters first. Add animation only when it improves the
  wiki and stays within the media budget.

Exit gate: all 115 enemy pages and five character pages use first-party media;
poses and bounds are stable; phobia-sensitive art has a documented fallback.

Status: **dependency inventory passed; capture harness not yet implemented**.
All 115 wiki enemies map to scene inputs (114 exact names plus the three-way
Decimillipede Segment representative choice), and all five characters map
exactly. Of 126 creature scenes, 119 contain Spine, five are multi-Spine
compositions, 50 include particles, 20 include shaders, and eight reference
phobia alternatives. The PCK is Godot 4.5.1 and contains 164 baked skeleton
imports plus 170 baked atlas imports. The proof matrix is Frog Knight (simple
idle), Kin Follower (dynamic skin), Wriggler (phobia replacement), and
Decimillipede (multi-part/VFX stress case).

### Phase 4 — Extended media

- Replace the nine event images, then inventory potions, powers, orbs,
  character-select art, and other images as those entity pages need them.
- Add card-affliction previews (`bound`, `entangled`, `galvanized`, `hexed`,
  `ringing`, `smog`, and `tainted`) only after their shader/animation behavior
  can be reproduced consistently.
- Keep decorative VFX out of the critical path unless a page actually exposes
  them.

Exit gate: a repository-wide URL audit finds no unintended Spire Codex image
dependency.

## Quality and deployment gates

- No silent fallback: every fallback is named in the generated report.
- Static output budget: normally below 500 KiB; exceptions require visual
  justification.
- Animated output budget: normally below 4 MiB and 60 frames, with an infinite
  loop only when the game loops the source animation.
- All animated assets retain a useful first frame for reduced-motion clients
  and link previews.
- Validate alpha bounds and transparent-edge color to prevent halos.
- Compare representative outputs at native resolution and at their actual wiki
  display size.
- Upload a complete category to a staging prefix, validate it, then promote it
  atomically to stable keys. Never mix a partial category replacement into
  production.
- Keep the previous manifest and R2 object versions available for rollback.
