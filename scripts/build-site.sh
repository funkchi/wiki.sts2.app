#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

rm -rf public site
mkdir -p public

if [ -x ".venv/bin/mkdocs" ]; then
  MKDOCS=".venv/bin/mkdocs"
else
  MKDOCS="mkdocs"
fi

cp -R landing/. public/
"$MKDOCS" build --strict --site-dir public/docs

test -f public/index.html
test -f public/ads.txt
test -f public/robots.txt
test -f public/sitemap.xml
test -f public/sitemap-pages.xml
test -f public/docs/index.html
test -f public/images/hero.png
test -f public/docs/images/hero.png
