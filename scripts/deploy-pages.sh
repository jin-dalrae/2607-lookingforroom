#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

PROJECT_NAME="${PAGES_PROJECT_NAME:-2607-lookingforroom}"

echo "Regenerating HTML dashboards..."
python communication_page.py
python batch_apply.py

echo "Copying assets to site/..."
cp listing-mails-communication.html batch_apply.html site/

echo "Deploying to Cloudflare Pages ($PROJECT_NAME)..."
npx wrangler pages deploy site \
  --project-name="$PROJECT_NAME" \
  --commit-dirty=true

echo "Done."