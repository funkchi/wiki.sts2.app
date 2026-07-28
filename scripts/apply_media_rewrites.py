#!/usr/bin/env python3
"""Apply the URL rewrites recorded in the first-party cutover plan.

Reads artifacts/generated-media/cutover-plan.json and rewrites the image
fields in data/wiki/*.json to their stable /media/... URLs. Refuses to act if
the plan has validation errors, and reports any field whose current value no
longer matches what the plan recorded.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PLAN = Path("artifacts/generated-media/cutover-plan.json")
WIKI_ROOT = Path("data/wiki")

# kind -> (file stem, array key)
DATASETS = {
    "cards": "cards",
    "relics": "relics",
    "enchantments": "enchantments",
    "events": "events",
    "characters": "characters",
}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path, default=PLAN)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    plan = json.loads(args.plan.read_text())
    if plan.get("errors"):
        raise SystemExit("refusing to apply rewrites from a plan with errors")

    by_kind: dict[str, list[dict]] = {}
    for rewrite in plan["rewrites"]:
        by_kind.setdefault(rewrite["kind"], []).append(rewrite)

    total = 0
    stale = 0
    for kind, rewrites in sorted(by_kind.items()):
        stem = DATASETS[kind]
        path = WIKI_ROOT / f"{stem}.json"
        payload = json.loads(path.read_text())
        by_id = {entity["id"]: entity for entity in payload[stem]}
        applied = 0
        for rewrite in rewrites:
            entity = by_id.get(rewrite["id"])
            if entity is None:
                print(f"stale: {kind}/{rewrite['id']} no longer exists", file=sys.stderr)
                stale += 1
                continue
            current = entity.get(rewrite["field"]) or ""
            if current == rewrite["to"]:
                continue
            if current != rewrite["from"]:
                print(
                    f"stale: {kind}/{rewrite['id']}.{rewrite['field']} is "
                    f"{current!r}, plan expected {rewrite['from']!r}",
                    file=sys.stderr,
                )
                stale += 1
                continue
            entity[rewrite["field"]] = rewrite["to"]
            applied += 1
        if applied and not args.dry_run:
            path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
        total += applied
        print(f"{kind}: {applied} field{'s' if applied != 1 else ''} rewritten", file=sys.stderr)

    print(
        f"{'would rewrite' if args.dry_run else 'rewrote'} {total} fields; {stale} stale",
        file=sys.stderr,
    )
    return 1 if stale else 0


if __name__ == "__main__":
    raise SystemExit(main())
