#!/usr/bin/env python3
"""Inject optional provider verification and analytics tags into built HTML."""

from __future__ import annotations

import argparse
import html
import os
import re
from pathlib import Path


TOKEN_PATTERN = re.compile(r"^[A-Za-z0-9_-]{8,160}$")


def validated_token(name: str, value: str | None) -> str | None:
    if not value:
        return None
    value = value.strip()
    if not TOKEN_PATTERN.fullmatch(value):
        raise ValueError(f"{name} contains unexpected characters or length")
    return value


def inject_before(text: str, marker: str, snippet: str, path: Path) -> str:
    if snippet in text:
        return text
    if marker not in text:
        raise ValueError(f"Missing {marker} in {path}")
    return text.replace(marker, f"  {snippet}\n{marker}", 1)


def configure(
    public_dir: Path,
    google_verification: str | None,
    cloudflare_analytics_token: str | None,
) -> tuple[int, int]:
    google_verification = validated_token("GOOGLE_SITE_VERIFICATION", google_verification)
    cloudflare_analytics_token = validated_token(
        "CLOUDFLARE_WEB_ANALYTICS_TOKEN", cloudflare_analytics_token
    )
    google_count = 0
    analytics_count = 0

    root_page = public_dir / "index.html"
    if google_verification:
        text = root_page.read_text()
        snippet = (
            '<meta name="google-site-verification" '
            f'content="{html.escape(google_verification, quote=True)}">'
        )
        updated = inject_before(text, "</head>", snippet, root_page)
        root_page.write_text(updated)
        google_count = 1

    if cloudflare_analytics_token:
        token = html.escape(cloudflare_analytics_token, quote=True)
        snippet = (
            '<script defer src="https://static.cloudflareinsights.com/beacon.min.js" '
            f'data-cf-beacon=\'{{"token":"{token}"}}\'></script>'
        )
        for path in sorted(public_dir.rglob("*.html")):
            text = path.read_text()
            if "</body>" not in text:
                continue
            updated = inject_before(text, "</body>", snippet, path)
            path.write_text(updated)
            analytics_count += 1

    return google_count, analytics_count


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("public_dir", type=Path, nargs="?", default=Path("public"))
    args = parser.parse_args()
    google_count, analytics_count = configure(
        args.public_dir,
        os.environ.get("GOOGLE_SITE_VERIFICATION"),
        os.environ.get("CLOUDFLARE_WEB_ANALYTICS_TOKEN"),
    )
    print(f"Provider tags: Search Console={google_count}, Web Analytics pages={analytics_count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
