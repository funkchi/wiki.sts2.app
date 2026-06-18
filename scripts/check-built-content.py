#!/usr/bin/env python3
"""Validate generated entity images, anchors, and character cross-links."""

from __future__ import annotations

import json
import time
import urllib.request
from html.parser import HTMLParser
from pathlib import Path


API_BASE = "https://spire-codex.com/api"


class PageAudit(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.ids: list[tuple[str, str]] = []
        self.links: list[str] = []
        self.images: list[tuple[set[str], str]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        if values.get("id"):
            self.ids.append((tag, values["id"] or ""))
        if tag == "a" and values.get("href"):
            self.links.append(values["href"] or "")
        if tag == "img":
            self.images.append((set((values.get("class") or "").split()), values.get("src") or ""))


def fetch(endpoint: str) -> list[dict[str, object]]:
    request = urllib.request.Request(
        f"{API_BASE}/{endpoint}?lang=eng",
        headers={"User-Agent": "wiki.sts2.app build check"},
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


def parse(page: str) -> PageAudit:
    audit = PageAudit()
    audit.feed(Path("public/docs", page, "index.html").read_text())
    return audit


def anchors(page: PageAudit, prefix: str) -> set[str]:
    values = [value for tag, value in page.ids if tag == "a" and value.startswith(prefix)]
    if len(values) != len(set(values)):
        raise AssertionError(f"Duplicate {prefix} anchors")
    return set(values)


def image_count(page: PageAudit, class_name: str) -> int:
    sources = [source for classes, source in page.images if class_name in classes]
    if any(not source.startswith("/media/") for source in sources):
        raise AssertionError(f"{class_name} contains a non-R2 image path")
    return len(sources)


def main() -> int:
    source = {endpoint: fetch(endpoint) for endpoint in ("cards", "characters", "relics", "monsters")}
    cards, characters, relics, enemies = (parse(page) for page in ("cards", "characters", "relics", "enemies"))

    card_anchors = anchors(cards, "card-")
    relic_anchors = anchors(relics, "relic-")
    checks = {
        "card images": (image_count(cards, "wiki-image--card"), len(source["cards"])),
        "card anchors": (len(card_anchors), len(source["cards"])),
        "relic images": (image_count(relics, "wiki-image--relic"), len(source["relics"])),
        "relic anchors": (len(relic_anchors), len(source["relics"])),
        "character thumbnails": (image_count(characters, "wiki-image--character-thumb"), len(source["characters"])),
        "character portraits": (image_count(characters, "wiki-image--character"), len(source["characters"])),
        "enemy images": (image_count(enemies, "wiki-image--enemy"), len(source["monsters"])),
        "enemy anchors": (len(anchors(enemies, "enemy-")), len(source["monsters"])),
    }
    failures = {label: values for label, values in checks.items() if values[0] != values[1]}
    if failures:
        raise AssertionError(f"Entity coverage mismatch: {failures}")

    expected_links = sum(
        len(set(character.get("starting_deck", []))) + 2 * len(character.get("starting_relics", []))
        for character in source["characters"]
    )
    entity_links = [
        href
        for href in characters.links
        if "../cards/#card-" in href or "../relics/#relic-" in href
    ]
    if len(entity_links) != expected_links:
        raise AssertionError(f"Expected {expected_links} character entity links, found {len(entity_links)}")
    for href in entity_links:
        anchor = href.split("#", 1)[1]
        target = card_anchors if "/cards/" in href else relic_anchors
        if anchor not in target:
            raise AssertionError(f"Missing character link target: {href}")

    print("Built content coverage passed:")
    for label, (actual, _) in checks.items():
        print(f"  {label}: {actual}")
    print(f"  character card/relic links: {len(entity_links)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
