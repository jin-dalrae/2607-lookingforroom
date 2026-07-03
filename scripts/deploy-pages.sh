#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

PROJECT_NAME="${PAGES_PROJECT_NAME:-2607-lookingforroom}"

echo "Exporting apply queue..."
python listings_page.py

echo "Deploying to Cloudflare Pages ($PROJECT_NAME)..."
npx wrangler pages deploy site \
  --project-name="$PROJECT_NAME" \
  --commit-dirty=true

echo "Done."