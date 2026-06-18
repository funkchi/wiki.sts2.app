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

Entity artwork can be synchronized to R2 with the Spire Codex API as the primary source and transparent full-character artwork from Untapped.gg:

```bash
python3 scripts/sync-r2-media.py --bucket wiki-sts2
```

Downloaded files are cached in the ignored `.media-cache/` directory. The R2 bucket is bound to Pages as `WIKI_MEDIA` in `wrangler.toml` and does not need public bucket access.

## Cloudflare Pages

Cloudflare Pages can host the whole site without a VPS.

Recommended Pages settings:

- Build command: `python3 -m pip install -r requirements.txt && bash scripts/build-site.sh`
- Build output directory: `public`
- Production branch: `main`
- Pages Function directory: `functions`
- R2 binding: `WIKI_MEDIA` to `wiki-sts2`

The GitHub Actions workflow also supports direct Pages deploys with Wrangler when these are configured:

- `CLOUDFLARE_API_TOKEN` repository secret
- `CLOUDFLARE_ACCOUNT_ID` repository secret
- `CLOUDFLARE_PROJECT_NAME` repository variable, optional; defaults to `wiki-sts2-app`

## VPS

The workflow still supports the existing VPS layout when these repository secrets are configured:

- `DEPLOY_KEY`
- `DEPLOY_HOST`
- `DEPLOY_USER`

It deploys:

- `public/` excluding `/docs/` to `/home/xiaochi/sts2-wiki/landing/`
- `public/docs/` to `/home/xiaochi/sts2-wiki/site/`

The web server should route `/` to the landing directory and `/docs/` to the MkDocs directory.
