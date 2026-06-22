#!/usr/bin/env python3
"""Hash Spire artwork and upload only changed objects to the wiki R2 bucket."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Callable


API_BASE = "https://spire-codex.com/api"
SITE_BASE = "https://spire-codex.com"
CACHE_DIR = Path(".media-cache")
DEFAULT_MANIFEST = Path("data/media-manifest.json")
ENDPOINTS = {
    "cards": "cards",
    "characters": "characters",
    "relics": "relics",
    "monsters": "enemies",
}


def fetch_json(endpoint: str) -> list[dict[str, Any]]:
    request = urllib.request.Request(
        f"{API_BASE}/{endpoint}?lang=eng",
        headers={"User-Agent": "wiki.sts2.app media sync"},
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response)


def slug(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "-", str(value).lower()).strip("-")


def source_url(endpoint: str, item: dict[str, Any]) -> str:
    if endpoint == "characters":
        character = slug(item["id"])
        return f"https://cdn.spire-codex.com/characters/combat_{character}.webp"
    value = item.get("image_url_card") if endpoint == "cards" else item.get("image_url")
    value = value or item.get("image_url")
    if not value:
        raise ValueError(f"Missing image URL for {endpoint}/{item.get('id')}")
    return f"{SITE_BASE}{value}" if str(value).startswith("/") else str(value)


def build_source_manifest() -> list[dict[str, str]]:
    entries = []
    for endpoint, folder in ENDPOINTS.items():
        for item in fetch_json(endpoint):
            entries.append(
                {
                    "key": f"{folder}/{slug(item['id'])}.webp",
                    "source_url": source_url(endpoint, item),
                }
            )
    return sorted(entries, key=lambda entry: entry["key"])


def is_webp(data: bytes) -> bool:
    return len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP"


def download(entry: dict[str, str], refresh: bool) -> dict[str, Any]:
    destination = CACHE_DIR / entry["key"]
    if refresh or not destination.exists() or destination.stat().st_size == 0:
        request = urllib.request.Request(
            entry["source_url"], headers={"User-Agent": "wiki.sts2.app media sync"}
        )
        with urllib.request.urlopen(request, timeout=60) as response:
            data = response.read()
        if not is_webp(data):
            raise ValueError(f"Invalid WebP response for {entry['key']}")
        destination.parent.mkdir(parents=True, exist_ok=True)
        if not destination.exists() or destination.read_bytes() != data:
            destination.write_bytes(data)
    data = destination.read_bytes()
    if not is_webp(data):
        raise ValueError(f"Invalid cached WebP for {entry['key']}")
    return {
        **entry,
        "sha256": hashlib.sha256(data).hexdigest(),
        "size": len(data),
        "path": destination,
    }


def upload(bucket: str, entry: dict[str, Any]) -> str:
    result = subprocess.run(
        [
            "wrangler",
            "r2",
            "object",
            "put",
            f"{bucket}/{entry['key']}",
            "--file",
            str(entry["path"]),
            "--content-type",
            "image/webp",
            "--cache-control",
            "public, max-age=604800",
            "--remote",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode:
        raise RuntimeError(f"Upload failed for {entry['key']}: {result.stderr or result.stdout}")
    return entry["key"]


def run_parallel(label: str, function: Callable[[Any], Any], entries: list[Any], workers: int) -> list[Any]:
    if not entries:
        print(f"{label}: 0")
        return []
    results = []
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = [executor.submit(function, entry) for entry in entries]
        for index, future in enumerate(as_completed(futures), 1):
            results.append(future.result())
            if index % 50 == 0 or index == len(entries):
                print(f"{label}: {index}/{len(entries)}")
    return results


def scan_parallel(
    entries: list[dict[str, str]], workers: int, refresh: bool
) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    results = []
    unavailable = []
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {executor.submit(download, entry, refresh): entry for entry in entries}
        for index, future in enumerate(as_completed(futures), 1):
            entry = futures[future]
            try:
                results.append(future.result())
            except Exception as error:
                unavailable.append(
                    {
                        "key": entry["key"],
                        "source_url": entry["source_url"],
                        "error": str(error),
                    }
                )
            if index % 50 == 0 or index == len(entries):
                print(f"Hashed: {index}/{len(entries)}")
    return results, sorted(unavailable, key=lambda entry: entry["key"])


def load_manifest(path: Path) -> dict[str, dict[str, Any]]:
    if not path.exists():
        return {}
    payload = json.loads(path.read_text())
    if payload.get("schema_version") != 1:
        raise ValueError(f"Unsupported media manifest schema in {path}")
    return payload.get("items", {})


def public_entry(entry: dict[str, Any]) -> dict[str, Any]:
    return {key: entry[key] for key in ("source_url", "sha256", "size")}


def write_report(
    path: Path,
    total: int,
    changed: list[dict[str, Any]],
    removed: list[str],
    unavailable: list[dict[str, str]],
) -> None:
    lines = [
        "# R2 media diff",
        "",
        f"Scanned **{total}** objects. **{len(changed)}** changed or new; **{len(removed)}** removed.",
    ]
    if changed:
        lines += ["", "## Changed or new", ""]
        lines += [f"- `{entry['key']}` ({entry['size']:,} bytes)" for entry in changed]
    if removed:
        lines += ["", "## Removed from source", ""]
        lines += [f"- `{key}`" for key in removed]
    if unavailable:
        lines += ["", "## Temporarily unavailable", ""]
        lines += [
            f"- `{entry['key']}` from `{entry['source_url']}`: {entry['error']}"
            for entry in unavailable
        ]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines).rstrip() + "\n")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bucket", default="wiki-sts2")
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--download-only", action="store_true")
    parser.add_argument("--plan", action="store_true", help="report changes without uploading or updating the manifest")
    parser.add_argument("--refresh", action="store_true", help="redownload files before hashing")
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--report", type=Path, default=Path("artifacts/r2-media-diff.md"))
    parser.add_argument("--github-output", default=os.environ.get("GITHUB_OUTPUT"))
    parser.add_argument(
        "--kinds",
        nargs="+",
        choices=sorted(ENDPOINTS.values()),
        help="limit the sync to one or more media folders",
    )
    args = parser.parse_args()

    sources = build_source_manifest()
    if args.kinds:
        sources = [entry for entry in sources if entry["key"].split("/", 1)[0] in args.kinds]
    if len(sources) != len({entry["key"] for entry in sources}):
        raise ValueError("Media manifest contains duplicate object keys")

    previous = load_manifest(args.manifest)
    print(f"Manifest: {len(sources)} images")
    scanned, unavailable = scan_parallel(sources, args.workers, args.refresh)
    downloaded = sorted(scanned, key=lambda entry: entry["key"])
    changed = [entry for entry in downloaded if previous.get(entry["key"], {}).get("sha256") != entry["sha256"]]
    current_keys = {entry["key"] for entry in sources}
    selected_folders = set(args.kinds or ENDPOINTS.values())
    removed = sorted(
        key
        for key in previous
        if key.split("/", 1)[0] in selected_folders and key not in current_keys
    )
    write_report(args.report, len(sources), changed, removed, unavailable)
    print(
        f"Changed or new: {len(changed)}; removed from source: {len(removed)}; "
        f"temporarily unavailable: {len(unavailable)}"
    )
    for entry in unavailable:
        print(f"::warning file={entry['key']}::{entry['error']}")
    if args.github_output:
        with Path(args.github_output).open("a") as output:
            output.write(f"changed={'true' if changed or removed else 'false'}\n")
            output.write(f"changed_count={len(changed)}\n")
            output.write(f"removed_count={len(removed)}\n")
            output.write(f"unavailable_count={len(unavailable)}\n")

    if not args.download_only and not args.plan:
        run_parallel("Uploaded", lambda entry: upload(args.bucket, entry), changed, args.workers)

    if args.plan:
        return 0

    next_items = dict(previous)
    for key in removed:
        next_items.pop(key, None)
    next_items.update({entry["key"]: public_entry(entry) for entry in downloaded})
    args.manifest.parent.mkdir(parents=True, exist_ok=True)
    args.manifest.write_text(
        json.dumps({"schema_version": 1, "items": dict(sorted(next_items.items()))}, indent=2) + "\n"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
