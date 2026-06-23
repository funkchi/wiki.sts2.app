# Deployment

The landing and wiki are static. Entity artwork is stored in the private `wiki-sts2` R2 bucket and served by a Pages Function at `/media/*`.

The build output in `public/` contains:

- `/index.html` and `/images/*` from `landing/`
- `/docs/*` from MkDocs

## Build

```bash
python3 -m pip install -r requirements.txt
bash scripts/build-site.sh
```

## Content Sync

Core wiki pages are generated from the public Spire Codex API.

```bash
python3 scripts/sync-spire-codex.py
```

To verify that generated pages are current without editing files:

```bash
python3 scripts/sync-spire-codex.py --check
```

Entity artwork can be synchronized to R2 with Spire Codex as the source. Character objects use the original `combat_*.webp` models from the Spire Codex CDN:

```bash
python3 scripts/sync-r2-media.py --bucket wiki-sts2
```

Downloaded files are cached in the ignored `.media-cache/` directory. The R2 bucket is bound to Pages as `WIKI_MEDIA` in `wrangler.toml` and does not need public bucket access.

The nightly `Check Data Freshness` workflow compares deterministic API and media manifests, publishes Markdown diff reports, uploads only changed artwork when Cloudflare credentials are present, and opens a pull request for source changes. Added or removed entities also create a dedicated GitHub issue; later detections append to the existing open issue so the alert remains visible without producing duplicates. A temporarily invalid or unavailable artwork response is reported as a workflow warning while its last known-good R2 manifest entry is preserved, allowing the remaining media scan to finish.

## Cloudflare Pages

Cloudflare Pages can host the whole site without a VPS.

Recommended Pages settings:

- Build command: `python3 -m pip install -r requirements.txt && bash scripts/build-site.sh`
- Build output directory: `public`
- Production branch: `main`
- Pages Function directory: `functions`
- R2 binding: `WIKI_MEDIA` to `wiki-sts2`
- Analytics Engine binding: `WIKI_ANALYTICS` to `wiki_sts2_events`

The GitHub Actions workflow also supports direct Pages deploys with Wrangler when these are configured:

- `CLOUDFLARE_API_TOKEN` repository secret
- `CLOUDFLARE_ACCOUNT_ID` repository secret
- `CLOUDFLARE_PROJECT_NAME` repository variable, optional; defaults to `wiki-sts2-app`
- `CLOUDFLARE_WEB_ANALYTICS_TOKEN` repository secret, optional; injects the Cloudflare beacon into every built HTML page
- `CLOUDFLARE_ANALYTICS_TOKEN` repository secret with `Account Analytics Read`; powers the weekly usage report
- `GOOGLE_SITE_VERIFICATION` repository secret, optional; injects Search Console verification into the root page

## Analytics

The repository deploys a first-party event endpoint at `/api/analytics`. Its Analytics Engine schema is:

- `blob1`: event type (`page_view`, `navigation`, `search`, or `search_empty`)
- `blob2`: current path
- `blob3`: navigation destination
- `blob4`: normalized search text
- `double1`: visible search-result count

No IP address, user agent, account ID, or persistent visitor ID is written to this dataset.

The `Report Wiki Usage` workflow runs each Monday and publishes both Markdown and JSON artifacts for the trailing 30 days. It covers popular pages, popular searches, empty searches, and internal navigation paths. It requires a dedicated `CLOUDFLARE_ANALYTICS_TOKEN`; keep this read-only token separate from the deployment token. If the Analytics credentials are missing, the workflow writes a setup report and opens or updates a GitHub issue instead of failing the scheduled run.

Enable Cloudflare Web Analytics for page popularity, referrers, navigation type, and performance:

1. Open Cloudflare **Workers & Pages**.
2. Select `wiki-sts2-app`.
3. Open **Metrics** and select **Enable** under Web Analytics.
4. Redeploy the project so Cloudflare injects its beacon.

Alternatively, copy the public beacon token from **Web Analytics → Manage site** into the `CLOUDFLARE_WEB_ANALYTICS_TOKEN` GitHub secret. The build then injects the same beacon deterministically.

Useful Analytics Engine SQL queries:

```sql
-- Most viewed pages
SELECT blob2 AS path, SUM(_sample_interval) AS views
FROM wiki_sts2_events
WHERE blob1 = 'page_view' AND timestamp >= NOW() - INTERVAL '30' DAY
GROUP BY path
ORDER BY views DESC
LIMIT 100;

-- Most frequent successful searches
SELECT blob4 AS search_term,
       SUM(_sample_interval) AS searches,
       SUM(_sample_interval * double1) / SUM(_sample_interval) AS average_results
FROM wiki_sts2_events
WHERE blob1 = 'search' AND timestamp >= NOW() - INTERVAL '30' DAY
GROUP BY search_term
ORDER BY searches DESC
LIMIT 50;

-- Searches that returned no visible result
SELECT blob4 AS search_term, SUM(_sample_interval) AS searches
FROM wiki_sts2_events
WHERE blob1 = 'search_empty' AND timestamp >= NOW() - INTERVAL '30' DAY
GROUP BY search_term
ORDER BY searches DESC
LIMIT 50;

-- Most common internal navigation edges
SELECT blob2 AS source_path, blob3 AS destination_path,
       SUM(_sample_interval) AS navigations
FROM wiki_sts2_events
WHERE blob1 = 'navigation' AND timestamp >= NOW() - INTERVAL '30' DAY
GROUP BY source_path, destination_path
ORDER BY navigations DESC
LIMIT 100;
```

Query the dataset through the Analytics Engine SQL API using an API token with `Account Analytics Read`.

## Search Console

Google Search Console requires verification in the site owner's Google account and cannot be completed by a repository deployment alone:

1. Add a Domain property for `wiki.sts2.app` (or the parent domain if preferred).
2. Add Google's verification TXT record to the Cloudflare DNS zone.
3. Submit `https://wiki.sts2.app/sitemap.xml`.
4. Confirm that `/robots.txt`, the root sitemap index, and sampled entity canonicals are accepted.

For a URL-prefix property, the HTML verification token can instead be stored as the `GOOGLE_SITE_VERIFICATION` GitHub secret and deployed through the build.

## VPS Migration

Cloudflare Pages is the production target. A VPS migration can still use the generated `public/` directory:

- Serve `public/` as the document root.
- Replace `/media/*` with a proxy to R2 or copy the R2 objects to local storage.
- Replace the Pages Functions analytics endpoint or disable `wiki-analytics.js`.
- Preserve root `/robots.txt`, `/sitemap.xml`, `/ads.txt`, and `/docs/*` paths.
