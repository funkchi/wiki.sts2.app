#!/usr/bin/env python3
"""Validate built entity indexes, detail pages, links, media, and sitemaps."""

from __future__ import annotations

import json
import os
import re
import time
import urllib.request
import xml.etree.ElementTree as ET
from html.parser import HTMLParser
from pathlib import Path


API_BASE = "https://spire-codex.com/api"
SITE_BASE = "https://wiki.sts2.app"
DOCS_ROOT = Path("public/docs")
EDITORIAL_GUIDES = {
    "beginner-guide",
    "deckbuilding-and-scaling",
    "character-archetypes",
    "boss-preparation",
}


class PageAudit(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.ids: list[tuple[str, str]] = []
        self.links: list[str] = []
        self.images: list[tuple[set[str], str]] = []
        self.canonicals: list[str] = []
        self.descriptions: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        if values.get("id"):
            self.ids.append((tag, values["id"] or ""))
        if tag == "a" and values.get("href"):
            self.links.append(values["href"] or "")
        if tag == "img":
            self.images.append((set((values.get("class") or "").split()), values.get("src") or ""))
        if tag == "link" and "canonical" in (values.get("rel") or "").split():
            self.canonicals.append(values.get("href") or "")
        if tag == "meta" and values.get("name") == "description":
            self.descriptions.append(values.get("content") or "")


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


def slug(value: object) -> str:
    return re.sub(r"[^a-z0-9]+", "-", str(value).lower()).strip("-")


def parse_path(path: Path) -> PageAudit:
    audit = PageAudit()
    audit.feed(path.read_text())
    return audit


def parse(page: str) -> PageAudit:
    return parse_path(DOCS_ROOT / page / "index.html")


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


def expected_slugs(items: list[dict[str, object]], kind: str) -> set[str]:
    values = [slug(item["id"]) for item in items]
    if len(values) != len(set(values)):
        raise AssertionError(f"Source IDs produce duplicate {kind} URLs")
    return set(values)


def check_index_links(page: PageAudit, folder: str, expected: set[str]) -> None:
    found = {
        href[:-1]
        for href in page.links
        if href.endswith("/") and href != "./" and "/" not in href[:-1]
    }
    missing = expected - found
    extra = found - expected
    if missing or extra:
        raise AssertionError(
            f"{folder} index link mismatch: missing={sorted(missing)[:5]}, extra={sorted(extra)[:5]}"
        )


def check_detail_pages(folder: str, expected: set[str], image_class: str) -> set[str]:
    built = {path.parent.name for path in (DOCS_ROOT / folder).glob("*/index.html")}
    if built != expected:
        raise AssertionError(
            f"{folder} detail page mismatch: missing={sorted(expected - built)[:5]}, "
            f"extra={sorted(built - expected)[:5]}"
        )

    urls: set[str] = set()
    for item_slug in sorted(expected):
        audit = parse_path(DOCS_ROOT / folder / item_slug / "index.html")
        url = f"{SITE_BASE}/docs/{folder}/{item_slug}/"
        if audit.canonicals != [url]:
            raise AssertionError(f"Invalid canonical for {url}: {audit.canonicals}")
        if len(audit.descriptions) != 1 or not audit.descriptions[0].strip():
            raise AssertionError(f"Missing meta description for {url}")
        if image_count(audit, image_class) != 1:
            raise AssertionError(f"Expected one {image_class} image on {url}")
        html = (DOCS_ROOT / folder / item_slug / "index.html").read_text()
        if "| Property | Value |" in html or "| Stat | Value |" in html:
            raise AssertionError(f"Unrendered Markdown table on {url}")
        urls.add(url)
    return urls


def xml_locations(path: Path) -> set[str]:
    return {
        element.text.strip()
        for element in ET.parse(path).iter()
        if element.tag.rsplit("}", 1)[-1] == "loc" and element.text
    }


def main() -> int:
    source = {endpoint: fetch(endpoint) for endpoint in ("cards", "characters", "relics", "monsters")}
    cards, characters, relics, enemies = (parse(page) for page in ("cards", "characters", "relics", "enemies"))
    browser_script = DOCS_ROOT / "javascripts/entity-browser.js"
    if not browser_script.is_file():
        raise AssertionError("Missing built entity browser script")
    browser_source = browser_script.read_text()
    for label in ("Character / Pool", "Cost", "Type", "Rarity", "Pool", "Class", "Act"):
        if label not in browser_source:
            raise AssertionError(f"Missing browser filter: {label}")
    for script_name in ("consent.js", "wiki-analytics.js"):
        script_path = DOCS_ROOT / "javascripts" / script_name
        if not script_path.is_file() or not script_path.read_text().strip():
            raise AssertionError(f"Missing built privacy/analytics script: {script_name}")
    landing_html = Path("public/index.html").read_text()
    consent_position = landing_html.find("javascripts/consent.js")
    ads_position = landing_html.find("pagead2.googlesyndication.com")
    if consent_position < 0 or ads_position < 0 or consent_position > ads_position:
        raise AssertionError("Advertising consent defaults must load before AdSense")
    google_verification = os.environ.get("GOOGLE_SITE_VERIFICATION", "").strip()
    if google_verification and f'content="{google_verification}"' not in landing_html:
        raise AssertionError("Configured Search Console verification is missing from landing page")
    cloudflare_token = os.environ.get("CLOUDFLARE_WEB_ANALYTICS_TOKEN", "").strip()
    if cloudflare_token:
        html_pages = [path for path in Path("public").rglob("*.html") if "</body>" in path.read_text()]
        missing_beacons = [
            path for path in html_pages if "static.cloudflareinsights.com/beacon.min.js" not in path.read_text()
        ]
        if missing_beacons:
            raise AssertionError(f"Cloudflare beacon missing from built pages: {missing_beacons[:5]}")
    analytics_function = Path("functions/api/analytics.js").read_text()
    if not all(event in analytics_function for event in ("navigation", "search", "search_empty")):
        raise AssertionError("Analytics endpoint is missing required event types")
    wrangler_config = Path("wrangler.toml").read_text()
    if 'binding = "WIKI_ANALYTICS"' not in wrangler_config:
        raise AssertionError("Missing Analytics Engine binding")
    for page, kind in (("cards", "cards"), ("relics", "relics"), ("enemies", "enemies")):
        html = (DOCS_ROOT / page / "index.html").read_text()
        if f'data-wiki-browser="{kind}"' not in html:
            raise AssertionError(f"Missing {kind} browser mount")
        if "javascripts/entity-browser.js" not in html:
            raise AssertionError(f"Missing {kind} browser script reference")
    enemy_html = (DOCS_ROOT / "enemies/index.html").read_text()
    if "<th>Act</th>" not in enemy_html:
        raise AssertionError("Enemy index is missing its Act column")
    groups = {
        "cards": (source["cards"], cards, "card-", "wiki-image--card", "wiki-image--card-detail"),
        "characters": (
            source["characters"],
            characters,
            None,
            "wiki-image--character-thumb",
            "wiki-image--character-detail",
        ),
        "relics": (source["relics"], relics, "relic-", "wiki-image--relic", "wiki-image--relic-detail"),
        "enemies": (source["monsters"], enemies, "enemy-", "wiki-image--enemy", "wiki-image--enemy-detail"),
    }

    slugs: dict[str, set[str]] = {}
    detail_urls: set[str] = set()
    checks: dict[str, tuple[int, int]] = {}
    for folder, (items, index, anchor_prefix, index_image_class, detail_image_class) in groups.items():
        expected = expected_slugs(items, folder)
        slugs[folder] = expected
        checks[f"{folder} index images"] = (image_count(index, index_image_class), len(items))
        if anchor_prefix:
            checks[f"{folder} index anchors"] = (len(anchors(index, anchor_prefix)), len(items))
        check_index_links(index, folder, expected)
        detail_urls.update(check_detail_pages(folder, expected, detail_image_class))

    # The character index has both compact starter-kit links and expanded detail links.
    expected_links = sum(
        len(set(character.get("starting_deck", []))) + 2 * len(character.get("starting_relics", []))
        for character in source["characters"]
    )
    entity_links = [
        href
        for href in characters.links
        if re.fullmatch(r"\.\./(?:cards|relics)/[a-z0-9-]+/", href)
    ]
    if len(entity_links) != expected_links:
        raise AssertionError(f"Expected {expected_links} character entity links, found {len(entity_links)}")
    for href in entity_links:
        _, folder, item_slug, _ = href.split("/")
        if item_slug not in slugs[folder]:
            raise AssertionError(f"Missing character link target: {href}")

    failures = {label: values for label, values in checks.items() if values[0] != values[1]}
    if failures:
        raise AssertionError(f"Entity coverage mismatch: {failures}")

    guide_index = parse("guides")
    guide_links = {
        href.removesuffix("/")
        for href in guide_index.links
        if href.endswith("/") and "/" not in href.removesuffix("/")
    }
    if not EDITORIAL_GUIDES <= guide_links:
        raise AssertionError(f"Editorial guides missing from guide index: {sorted(EDITORIAL_GUIDES - guide_links)}")
    editorial_urls = set()
    for guide_slug in sorted(EDITORIAL_GUIDES):
        source_path = Path("docs/guides") / f"{guide_slug}.md"
        if len(source_path.read_text().split()) < 500:
            raise AssertionError(f"Editorial guide is too thin: {source_path}")
        audit = parse_path(DOCS_ROOT / "guides" / guide_slug / "index.html")
        url = f"{SITE_BASE}/docs/guides/{guide_slug}/"
        if audit.canonicals != [url]:
            raise AssertionError(f"Invalid editorial canonical for {url}: {audit.canonicals}")
        if len(audit.descriptions) != 1 or not audit.descriptions[0].strip():
            raise AssertionError(f"Missing editorial meta description for {url}")
        editorial_urls.add(url)

    root_sitemap = xml_locations(Path("public/sitemap.xml"))
    expected_sitemaps = {f"{SITE_BASE}/sitemap-pages.xml", f"{SITE_BASE}/docs/sitemap.xml"}
    if root_sitemap != expected_sitemaps:
        raise AssertionError(f"Root sitemap index mismatch: {root_sitemap}")
    if f"{SITE_BASE}/" not in xml_locations(Path("public/sitemap-pages.xml")):
        raise AssertionError("Landing page is missing from sitemap-pages.xml")
    docs_sitemap = xml_locations(DOCS_ROOT / "sitemap.xml")
    missing_detail_urls = detail_urls - docs_sitemap
    if missing_detail_urls:
        raise AssertionError(f"Detail pages missing from docs sitemap: {sorted(missing_detail_urls)[:5]}")
    missing_editorial_urls = editorial_urls - docs_sitemap
    if missing_editorial_urls:
        raise AssertionError(f"Editorial guides missing from docs sitemap: {sorted(missing_editorial_urls)}")
    robots = Path("public/robots.txt").read_text()
    if f"Sitemap: {SITE_BASE}/sitemap.xml" not in robots:
        raise AssertionError("robots.txt does not advertise the root sitemap")

    print("Built content coverage passed:")
    for label, (actual, _) in checks.items():
        print(f"  {label}: {actual}")
    print(f"  detail pages with canonical metadata: {len(detail_urls)}")
    print(f"  character card/relic links: {len(entity_links)}")
    print(f"  detail URLs in docs sitemap: {len(detail_urls)}")
    print(f"  original editorial guides: {len(editorial_urls)}")
    print("  entity browser mounts: 3")
    print("  consent-safe AdSense loading: enabled")
    print("  first-party analytics events: navigation, search, search_empty")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
