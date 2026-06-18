#!/usr/bin/env python3
"""Compare the live Spire Codex API with the wiki's committed data baseline."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import urllib.request
from pathlib import Path
from typing import Any


API_BASE = "https://spire-codex.com/api"
COLLECTIONS = ("cards", "characters", "relics", "monsters", "guides")
DEFAULT_SNAPSHOT = Path("data/spire-codex-snapshot.json")
DEFAULT_REPORT = Path("artifacts/spire-codex-diff.md")


def canonical_hash(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode()).hexdigest()


def fetch_json(endpoint: str) -> Any:
    suffix = "" if endpoint == "stats" else "?lang=eng"
    request = urllib.request.Request(
        f"{API_BASE}/{endpoint}{suffix}",
        headers={"User-Agent": "wiki.sts2.app freshness check"},
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response)


def entity_name(item: dict[str, Any]) -> str:
    return str(item.get("name") or item.get("title") or item["id"])


def entity_media(item: dict[str, Any]) -> list[str]:
    values = [
        item.get("image_url"),
        item.get("image_url_card"),
        item.get("image_url_card_upg"),
        item.get("beta_image_url"),
    ]
    return sorted({str(value) for value in values if value})


def build_snapshot() -> dict[str, Any]:
    collections: dict[str, list[dict[str, Any]]] = {}
    for endpoint in COLLECTIONS:
        entities = []
        for item in fetch_json(endpoint):
            entities.append(
                {
                    "id": str(item["id"]),
                    "name": entity_name(item),
                    "content_sha256": canonical_hash(item),
                    "media": entity_media(item),
                }
            )
        collections[endpoint] = sorted(entities, key=lambda item: item["id"])
    stats = fetch_json("stats")
    return {
        "schema_version": 1,
        "collections": collections,
        "stats": {"content_sha256": canonical_hash(stats), "values": stats},
    }


def index_entities(snapshot: dict[str, Any], endpoint: str) -> dict[str, dict[str, Any]]:
    return {item["id"]: item for item in snapshot.get("collections", {}).get(endpoint, [])}


def compare(previous: dict[str, Any], current: dict[str, Any]) -> dict[str, Any]:
    collections = {}
    entity_set_changed = False
    content_changed = previous.get("stats", {}).get("content_sha256") != current["stats"]["content_sha256"]
    for endpoint in COLLECTIONS:
        before = index_entities(previous, endpoint)
        after = index_entities(current, endpoint)
        added_ids = sorted(after.keys() - before.keys())
        removed_ids = sorted(before.keys() - after.keys())
        changed_ids = sorted(
            entity_id
            for entity_id in before.keys() & after.keys()
            if before[entity_id].get("content_sha256") != after[entity_id]["content_sha256"]
        )
        entity_set_changed = entity_set_changed or bool(added_ids or removed_ids)
        content_changed = content_changed or bool(added_ids or removed_ids or changed_ids)
        collections[endpoint] = {
            "before": len(before),
            "after": len(after),
            "added": [after[entity_id] for entity_id in added_ids],
            "removed": [before[entity_id] for entity_id in removed_ids],
            "changed": [after[entity_id] for entity_id in changed_ids],
        }
    return {
        "changed": content_changed,
        "entity_set_changed": entity_set_changed,
        "stats_changed": previous.get("stats", {}).get("content_sha256") != current["stats"]["content_sha256"],
        "collections": collections,
    }


def item_list(items: list[dict[str, Any]], limit: int = 100) -> str:
    if not items:
        return "None"
    lines = [f"- **{item['name']}** (`{item['id']}`)" for item in items[:limit]]
    if len(items) > limit:
        lines.append(f"- ...and {len(items) - limit} more")
    return "\n".join(lines)


def render_report(diff: dict[str, Any]) -> str:
    lines = [
        "# Spire Codex data diff",
        "",
        "No source changes detected."
        if not diff["changed"]
        else "Source changes detected. Review generated pages and media before merging.",
        "",
        "| Collection | Previous | Current | Added | Removed | Changed |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for endpoint, values in diff["collections"].items():
        lines.append(
            f"| {endpoint.title()} | {values['before']} | {values['after']} | "
            f"{len(values['added'])} | {len(values['removed'])} | {len(values['changed'])} |"
        )
    lines += ["", f"Stats changed: **{'yes' if diff['stats_changed'] else 'no'}**"]
    for endpoint, values in diff["collections"].items():
        if not any(values[key] for key in ("added", "removed", "changed")):
            continue
        lines += ["", f"## {endpoint.title()}"]
        for label, key in (("Added", "added"), ("Removed", "removed"), ("Changed", "changed")):
            if values[key]:
                lines += ["", f"### {label}", "", item_list(values[key])]
    return "\n".join(lines).rstrip() + "\n"


def write_output(path: str | None, values: dict[str, bool]) -> None:
    if not path:
        return
    with Path(path).open("a") as output:
        for key, value in values.items():
            output.write(f"{key}={'true' if value else 'false'}\n")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot", type=Path, default=DEFAULT_SNAPSHOT)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--update", action="store_true", help="replace the baseline with current API data")
    parser.add_argument("--fail-on-change", action="store_true")
    parser.add_argument("--github-output", default=os.environ.get("GITHUB_OUTPUT"))
    args = parser.parse_args()

    previous = json.loads(args.snapshot.read_text()) if args.snapshot.exists() else {"collections": {}, "stats": {}}
    current = build_snapshot()
    diff = compare(previous, current)
    report = render_report(diff)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(report)
    if args.update:
        args.snapshot.parent.mkdir(parents=True, exist_ok=True)
        args.snapshot.write_text(json.dumps(current, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
    write_output(
        args.github_output,
        {"changed": diff["changed"], "entity_set_changed": diff["entity_set_changed"]},
    )
    print(report, end="")
    return 1 if args.fail_on_change and diff["changed"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
