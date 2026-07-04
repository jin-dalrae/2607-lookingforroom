#!/usr/bin/env bash
# Detached queue UI + Apply API workers (not tied to a terminal session).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

STATIC_PORT="${STATIC_PORT:-8765}"
API_PORT="${API_PORT:-8787}"
RUN_DIR="${RUN_DIR:-$ROOT/.run}"
PID_DIR="$RUN_DIR/pids"
LOG_DIR="$RUN_DIR/logs"
API_PID_FILE="$PID_DIR/api.pid"
UI_PID_FILE="$PID_DIR/ui.pid"

PYTHON="${PYTHON:-$ROOT/.venv/bin/python}"
if [[ ! -x "$PYTHON" ]]; then
  PYTHON="$(command -v python3)"
fi

mkdir -p "$PID_DIR" "$LOG_DIR"

port_pids() {
  local port="$1"
  lsof -ti ":$port" 2>/dev/null || true
}

read_pid() {
  local file="$1"
  [[ -f "$file" ]] || return 1
  local pid
  pid="$(cat "$file" 2>/dev/null || true)"
  [[ "$pid" =~ ^[0-9]+$ ]] || return 1
  if kill -0 "$pid" 2>/dev/null; then
    echo "$pid"
    return 0
  fi
  rm -f "$file"
  return 1
}

stop_pid_file() {
  local name="$1"
  local file="$2"
  local pid
  if pid="$(read_pid "$file")"; then
    echo "Stopping $name (pid $pid)..."
    kill "$pid" 2>/dev/null || true
    for _ in {1..20}; do
      kill -0 "$pid" 2>/dev/null || break
      sleep 0.2
    done
    kill -9 "$pid" 2>/dev/null || true
  fi
  rm -f "$file"
}

stop_port() {
  local port="$1"
  local pids
  pids="$(port_pids "$port")"
  if [[ -n "$pids" ]]; then
    echo "Stopping process(es) on :$port ($pids)..."
    kill $pids 2>/dev/null || true
    sleep 0.5
    kill -9 $pids 2>/dev/null || true
  fi
}

export_queue() {
  echo "Exporting queue data..."
  DETAIL_BACKFILL_LIMIT="${DETAIL_BACKFILL_LIMIT:-0}" \
  FB_TITLE_BACKFILL_LIMIT="${FB_TITLE_BACKFILL_LIMIT:-0}" \
  POSTED_BACKFILL_LIMIT="${POSTED_BACKFILL_LIMIT:-0}" \
  "$PYTHON" listings_page.py
}

send_telegram_digest() {
  if [[ "${TELEGRAM_ALERT:-0}" != "1" ]]; then
    return 0
  fi
  echo "Sending Telegram digest (if configured)..."
  TELEGRAM_STATUS="${TELEGRAM_STATUS:-0}" "$PYTHON" "$ROOT/scripts/telegram_digest.py" || true
}

start_api() {
  if read_pid "$API_PID_FILE" >/dev/null; then
    echo "Apply API already running (pid $(cat "$API_PID_FILE"))."
    return 0
  fi
  stop_port "$API_PORT"
  echo "Starting Apply API on :$API_PORT..."
  nohup "$PYTHON" api.py --port "$API_PORT" --host 127.0.0.1 \
    >>"$LOG_DIR/api.log" 2>>"$LOG_DIR/api.err.log" &
  echo $! >"$API_PID_FILE"
  disown -h $! 2>/dev/null || true
}

start_ui() {
  if read_pid "$UI_PID_FILE" >/dev/null; then
    echo "Queue UI already running (pid $(cat "$UI_PID_FILE"))."
    return 0
  fi
  stop_port "$STATIC_PORT"
  echo "Starting queue UI on :$STATIC_PORT..."
  nohup "$PYTHON" -m http.server "$STATIC_PORT" --directory site \
    >>"$LOG_DIR/ui.log" 2>>"$LOG_DIR/ui.err.log" &
  echo $! >"$UI_PID_FILE"
  disown -h $! 2>/dev/null || true
}

wait_healthy() {
  local tries="${1:-20}"
  for ((i = 1; i <= tries; i++)); do
    if curl -sf "http://127.0.0.1:$API_PORT/api/health" >/dev/null 2>&1 \
      && curl -sf "http://127.0.0.1:$STATIC_PORT/" >/dev/null 2>&1; then
      return 0
    fi
    sleep 0.25
  done
  return 1
}

cmd_pull() {
  exec "$ROOT/scripts/daily-pull.sh"
}

cmd_start() {
  export_queue
  send_telegram_digest
  start_api
  start_ui
  if wait_healthy; then
    echo ""
    echo "Workers running (detached):"
    echo "  UI:  http://127.0.0.1:$STATIC_PORT/"
    echo "  API: http://127.0.0.1:$API_PORT/"
    echo "  Logs: $LOG_DIR"
    echo "  PIDs: $PID_DIR"
  else
    echo "Workers started but health check failed — see $LOG_DIR/*.err.log" >&2
    return 1
  fi
}

cmd_stop() {
  stop_pid_file "Apply API" "$API_PID_FILE"
  stop_pid_file "Queue UI" "$UI_PID_FILE"
  stop_port "$API_PORT"
  stop_port "$STATIC_PORT"
  echo "Workers stopped."
}

cmd_status() {
  local api_pid ui_pid
  api_pid="$(read_pid "$API_PID_FILE" 2>/dev/null || echo "")"
  ui_pid="$(read_pid "$UI_PID_FILE" 2>/dev/null || echo "")"
  if [[ -n "$api_pid" ]]; then
    echo "Apply API :$API_PORT — running (pid $api_pid)"
  else
    echo "Apply API :$API_PORT — stopped"
  fi
  if [[ -n "$ui_pid" ]]; then
    echo "Queue UI  :$STATIC_PORT — running (pid $ui_pid)"
  else
    echo "Queue UI  :$STATIC_PORT — stopped"
  fi
}

cmd_install() {
  local agent_dir="$HOME/Library/LaunchAgents"
  mkdir -p "$agent_dir"
  for svc in api ui; do
    local src="$ROOT/scripts/com.lookingforroom.$svc.plist"
    local dst="$agent_dir/com.lookingforroom.$svc.plist"
    sed \
      -e "s|__ROOT__|$ROOT|g" \
      -e "s|__PYTHON__|$PYTHON|g" \
      -e "s|__API_PORT__|$API_PORT|g" \
      -e "s|__STATIC_PORT__|$STATIC_PORT|g" \
      "$src" >"$dst"
    launchctl bootout "gui/$(id -u)/com.lookingforroom.$svc" 2>/dev/null || true
    launchctl bootstrap "gui/$(id -u)" "$dst"
    echo "Installed $dst"
  done
  echo "LaunchAgents loaded - workers start at login and restart on crash."
}

cmd_uninstall() {
  for svc in api ui; do
    launchctl bootout "gui/$(id -u)/com.lookingforroom.$svc" 2>/dev/null || true
    rm -f "$HOME/Library/LaunchAgents/com.lookingforroom.$svc.plist"
  done
  cmd_stop
  echo "LaunchAgents removed."
}

usage() {
  cat <<EOF
Usage: scripts/workers.sh <command>

Commands:
  start      Export queue + start detached UI and API workers
  pull       Daily pipeline: scout, filter, export, Telegram, restart workers
  stop       Stop workers
  restart    stop then start
  status     Show worker state
  install    Register macOS LaunchAgents (survives reboot)
  uninstall  Remove LaunchAgents and stop workers

Env: STATIC_PORT, API_PORT, RUN_DIR, PYTHON
      TELEGRAM_ALERT=1 on start/restart — send deduped high-score digest after export
      TELEGRAM_STATUS=1 — also send queue + match count (used by pull)
EOF
}

main() {
  local cmd="${1:-status}"
  case "$cmd" in
    start) cmd_start ;;
    pull) cmd_pull ;;
    stop) cmd_stop ;;
    restart) cmd_stop; cmd_start ;;
    status) cmd_status ;;
    install) cmd_install ;;
    uninstall) cmd_uninstall ;;
    -h|--help|help) usage ;;
    *) echo "Unknown command: $cmd" >&2; usage >&2; return 1 ;;
  esac
}

main "$@"