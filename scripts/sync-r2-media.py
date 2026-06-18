#!/usr/bin/env python3
"""Download Spire Codex artwork and upload it to the wiki R2 bucket."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any


API_BASE = "https://spire-codex.com/api"
SITE_BASE = "https://spire-codex.com"
CACHE_DIR = Path(".media-cache")
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
        request = urllib.request.Request(
            f"https://sts2.untapped.gg/en/characters/{character}",
            headers={"User-Agent": "wiki.sts2.app media sync"},
        )
        with urllib.request.urlopen(request, timeout=30) as response:
            page = response.read().decode()
        match = re.search(rf"/_next/static/media/{character}\.[a-z0-9]+\.webp", page)
        if not match:
            raise ValueError(f"Missing Untapped character art for {character}")
        return f"https://sts2.untapped.gg{match.group(0)}"
    value = item.get("image_url_card") if endpoint == "cards" else item.get("image_url")
    value = value or item.get("image_url")
    if not value:
        raise ValueError(f"Missing image URL for {endpoint}/{item.get('id')}")
    return f"{SITE_BASE}{value}" if str(value).startswith("/") else str(value)


def build_manifest() -> list[tuple[str, str]]:
    entries = []
    for endpoint, folder in ENDPOINTS.items():
        for item in fetch_json(endpoint):
            entries.append((f"{folder}/{slug(item['id'])}.webp", source_url(endpoint, item)))
    return entries


def download(entry: tuple[str, str]) -> tuple[str, Path]:
    key, url = entry
    destination = CACHE_DIR / key
    if destination.exists() and destination.stat().st_size > 0:
        return key, destination
    destination.parent.mkdir(parents=True, exist_ok=True)
    request = urllib.request.Request(url, headers={"User-Agent": "wiki.sts2.app media sync"})
    with urllib.request.urlopen(request, timeout=60) as response:
        data = response.read()
    if not data:
        raise ValueError(f"Empty image response for {key}")
    destination.write_bytes(data)
    return key, destination


def upload(bucket: str, entry: tuple[str, Path]) -> str:
    key, path = entry
    result = subprocess.run(
        [
            "wrangler",
            "r2",
            "object",
            "put",
            f"{bucket}/{key}",
            "--file",
            str(path),
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
        raise RuntimeError(f"Upload failed for {key}: {result.stderr or result.stdout}")
    return key


def run_parallel(label: str, function: Any, entries: list[Any], workers: int) -> list[Any]:
    results = []
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = [executor.submit(function, entry) for entry in entries]
        for index, future in enumerate(as_completed(futures), 1):
            results.append(future.result())
            if index % 50 == 0 or index == len(entries):
                print(f"{label}: {index}/{len(entries)}")
    return results


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bucket", default="wiki-sts2")
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--download-only", action="store_true")
    parser.add_argument(
        "--kinds",
        nargs="+",
        choices=sorted(ENDPOINTS.values()),
        help="limit the sync to one or more media folders",
    )
    args = parser.parse_args()

    manifest = build_manifest()
    if args.kinds:
        manifest = [entry for entry in manifest if entry[0].split("/", 1)[0] in args.kinds]
    if len(manifest) != len({key for key, _ in manifest}):
        raise ValueError("Media manifest contains duplicate object keys")
    print(f"Manifest: {len(manifest)} images")
    downloaded = run_parallel("Downloaded", download, manifest, args.workers)
    if not args.download_only:
        run_parallel("Uploaded", lambda entry: upload(args.bucket, entry), downloaded, args.workers)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
