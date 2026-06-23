#!/usr/bin/env python3
"""Query Cloudflare Analytics Engine and publish a compact usage report."""

from __future__ import annotations

import argparse
import json
import os
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DATASET = "wiki_sts2_events"
QUERIES = {
    "popular_pages": f"""
SELECT blob2 AS path, SUM(_sample_interval) AS views
FROM {DATASET}
WHERE blob1 = 'page_view' AND timestamp >= NOW() - INTERVAL '30' DAY
GROUP BY path ORDER BY views DESC LIMIT 100
""".strip(),
    "searches": f"""
SELECT blob4 AS search_term, SUM(_sample_interval) AS searches,
       SUM(_sample_interval * double1) / SUM(_sample_interval) AS average_results
FROM {DATASET}
WHERE blob1 = 'search' AND timestamp >= NOW() - INTERVAL '30' DAY
GROUP BY search_term ORDER BY searches DESC LIMIT 100
""".strip(),
    "empty_searches": f"""
SELECT blob4 AS search_term, SUM(_sample_interval) AS searches
FROM {DATASET}
WHERE blob1 = 'search_empty' AND timestamp >= NOW() - INTERVAL '30' DAY
GROUP BY search_term ORDER BY searches DESC LIMIT 100
""".strip(),
    "navigation_paths": f"""
SELECT blob2 AS source_path, blob3 AS destination_path,
       SUM(_sample_interval) AS navigations
FROM {DATASET}
WHERE blob1 = 'navigation' AND timestamp >= NOW() - INTERVAL '30' DAY
GROUP BY source_path, destination_path ORDER BY navigations DESC LIMIT 100
""".strip(),
}


def extract_rows(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return payload
    if not isinstance(payload, dict):
        raise ValueError("Analytics API returned an unsupported response")
    rows = payload.get("data")
    if rows is None and isinstance(payload.get("result"), dict):
        rows = payload["result"].get("data")
    if not isinstance(rows, list):
        raise ValueError("Analytics API response does not contain a data array")
    return rows


def query(account_id: str, token: str, sql: str) -> list[dict[str, Any]]:
    url = f"https://api.cloudflare.com/client/v4/accounts/{account_id}/analytics_engine/sql"
    request = urllib.request.Request(
        url,
        data=sql.encode(),
        method="POST",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "text/plain; charset=utf-8",
            "User-Agent": "wiki.sts2.app usage reporter",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            return extract_rows(json.load(response))
    except urllib.error.HTTPError as error:
        detail = error.read().decode(errors="replace")[:500]
        raise RuntimeError(f"Analytics API returned HTTP {error.code}: {detail}") from error


def markdown_table(rows: list[dict[str, Any]], columns: list[tuple[str, str]]) -> str:
    if not rows:
        return "_No events in this period._\n"
    header = "| " + " | ".join(label for _, label in columns) + " |"
    divider = "| " + " | ".join("---" for _ in columns) + " |"
    lines = [header, divider]
    for row in rows:
        values = []
        for key, _ in columns:
            value = row.get(key, "")
            if isinstance(value, float):
                value = f"{value:.1f}"
            values.append(str(value).replace("|", "\\|").replace("\n", " "))
        lines.append("| " + " | ".join(values) + " |")
    return "\n".join(lines) + "\n"


def render_report(results: dict[str, list[dict[str, Any]]], generated_at: str) -> str:
    sections = [
        ("Popular pages", "popular_pages", [("path", "Path"), ("views", "Views")]),
        (
            "Popular searches",
            "searches",
            [("search_term", "Search"), ("searches", "Searches"), ("average_results", "Avg. results")],
        ),
        ("Empty searches", "empty_searches", [("search_term", "Search"), ("searches", "Searches")]),
        (
            "Navigation paths",
            "navigation_paths",
            [("source_path", "From"), ("destination_path", "To"), ("navigations", "Navigations")],
        ),
    ]
    output = ["# Wiki usage report", "", f"Generated: {generated_at}", "", "Window: trailing 30 days.", ""]
    for heading, key, columns in sections:
        output.extend([f"## {heading}", "", markdown_table(results.get(key, []), columns).rstrip(), ""])
    return "\n".join(output).rstrip() + "\n"


def render_missing_credentials_report(generated_at: str) -> str:
    return "\n".join(
        [
            "# Wiki usage report",
            "",
            f"Generated: {generated_at}",
            "",
            "Usage reporting is not active yet because Cloudflare Analytics credentials are missing.",
            "",
            "Set these GitHub repository secrets to enable the scheduled report:",
            "",
            "- `CLOUDFLARE_ACCOUNT_ID`",
            "- `CLOUDFLARE_ANALYTICS_TOKEN` with Account Analytics Read access",
            "",
            "The site can still collect first-party events when the Pages project has the `WIKI_ANALYTICS` Analytics Engine binding.",
        ]
    ).rstrip() + "\n"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fixture", type=Path, help="Render previously queried JSON instead of calling Cloudflare")
    parser.add_argument("--output-dir", type=Path, default=Path("artifacts/analytics"))
    parser.add_argument(
        "--allow-missing-credentials",
        action="store_true",
        help="write a setup report instead of exiting non-zero when Cloudflare credentials are absent",
    )
    args = parser.parse_args()

    generated_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    status = "ok"
    if args.fixture:
        fixture = json.loads(args.fixture.read_text())
        results = fixture.get("results", fixture)
        generated_at = fixture.get("generated_at", generated_at)
    else:
        account_id = os.environ.get("CLOUDFLARE_ACCOUNT_ID", "").strip()
        token = os.environ.get("CLOUDFLARE_ANALYTICS_TOKEN", "").strip()
        if not account_id or not token:
            if args.allow_missing_credentials:
                status = "missing_credentials"
                results = {}
            else:
                raise SystemExit("CLOUDFLARE_ACCOUNT_ID and CLOUDFLARE_ANALYTICS_TOKEN are required")
        else:
            results = {name: query(account_id, token, sql) for name, sql in QUERIES.items()}

    args.output_dir.mkdir(parents=True, exist_ok=True)
    if status == "missing_credentials":
        payload = {"generated_at": generated_at, "window_days": 30, "status": status, "results": {}}
        report = render_missing_credentials_report(generated_at)
    else:
        payload = {"generated_at": generated_at, "window_days": 30, "status": status, "results": results}
        report = render_report(results, generated_at)
    (args.output_dir / "usage-report.json").write_text(json.dumps(payload, indent=2) + "\n")
    (args.output_dir / "usage-report.md").write_text(report)
    print(report)


if __name__ == "__main__":
    main()
