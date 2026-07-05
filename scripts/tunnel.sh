#!/usr/bin/env bash
# Expose the local Apply API to Cloudflare Pages via a quick tunnel.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

API_PORT="${API_PORT:-8787}"
PROJECT_NAME="${PAGES_PROJECT_NAME:-2607-lookingforroom}"
RUN_DIR="${RUN_DIR:-$ROOT/.run}"
LOG_DIR="$RUN_DIR/logs"
PID_FILE="$RUN_DIR/pids/tunnel.pid"

mkdir -p "$LOG_DIR" "$RUN_DIR/pids"

if ! curl -sf "http://127.0.0.1:$API_PORT/api/health" >/dev/null 2>&1; then
  echo "Apply API is not running on :$API_PORT — starting workers..."
  "$ROOT/scripts/workers.sh" start
fi

if ! command -v cloudflared >/dev/null 2>&1; then
  echo "cloudflared not found. Install with: brew install cloudflared" >&2
  exit 1
fi

if [[ -f "$PID_FILE" ]]; then
  old_pid="$(cat "$PID_FILE" 2>/dev/null || true)"
  if [[ "$old_pid" =~ ^[0-9]+$ ]] && kill -0 "$old_pid" 2>/dev/null; then
    echo "Tunnel already running (pid $old_pid). Log: $LOG_DIR/tunnel.log"
    if [[ -f "$LOG_DIR/tunnel.url" ]]; then
      echo "Origin: $(cat "$LOG_DIR/tunnel.url")"
    fi
    exit 0
  fi
fi

echo "Starting Cloudflare quick tunnel → http://127.0.0.1:$API_PORT"
: >"$LOG_DIR/tunnel.log"
nohup cloudflared tunnel --url "http://127.0.0.1:$API_PORT" \
  >>"$LOG_DIR/tunnel.log" 2>&1 &
echo $! >"$PID_FILE"
disown -h $! 2>/dev/null || true

origin=""
for _ in {1..60}; do
  origin="$(grep -Eo 'https://[a-z0-9-]+\.trycloudflare\.com' "$LOG_DIR/tunnel.log" | head -1 || true)"
  if [[ -n "$origin" ]]; then
    break
  fi
  sleep 0.5
done

if [[ -z "$origin" ]]; then
  echo "Timed out waiting for tunnel URL — see $LOG_DIR/tunnel.log" >&2
  exit 1
fi

printf '%s\n' "$origin" >"$LOG_DIR/tunnel.url"
echo "Tunnel origin: $origin"
echo "Updating Cloudflare Pages secret APPLY_API_ORIGIN..."
printf '%s' "$origin" | npx wrangler pages secret put APPLY_API_ORIGIN \
  --project-name="$PROJECT_NAME"

echo ""
echo "Done. Redeploy if needed: scripts/deploy-pages.sh"
echo "Tunnel log: $LOG_DIR/tunnel.log"