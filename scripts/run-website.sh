#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# run-website.sh – Start the news48 web server in production or development mode.
#
# Usage:
#   ./run-website.sh --production   Production: multi-worker, localhost-only, proxy headers
#   ./run-website.sh --development  Development: single-worker, auto-reload, open bind
#
# All settings can be overridden via environment variables (see below) or the
# corresponding .env file loaded by the application at startup.
# ---------------------------------------------------------------------------

set -euo pipefail

# ── Defaults ────────────────────────────────────────────────────────────────

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

MODE=""

# Production defaults
PROD_HOST="${WEB_HOST:-127.0.0.1}"        # bind localhost – reverse proxy faces the world
PROD_PORT="${WEB_PORT:-8000}"
PROD_WORKERS="${WEB_WORKERS:-4}"           # one worker per CPU core is a good start
PROD_LOG_LEVEL="${WEB_LOG_LEVEL:-info}"
PROD_ACCESS_LOG="${WEB_ACCESS_LOG:-1}"     # 1 = enabled, 0 = disabled

# Development defaults
DEV_HOST="${WEB_HOST:-0.0.0.0}"           # open bind for local testing
DEV_PORT="${WEB_PORT:-8765}"
DEV_LOG_LEVEL="${WEB_LOG_LEVEL:-debug}"
DEV_RELOAD="${WEB_RELOAD:-1}"             # 1 = auto-reload on code changes

# PID / log files (production only)
RUN_DIR="${SCRIPT_DIR}/data/run"
PID_FILE="${RUN_DIR}/news48.pid"
LOG_DIR="${SCRIPT_DIR}/data/logs"
ACCESS_LOG="${LOG_DIR}/access.log"
ERROR_LOG="${LOG_DIR}/error.log"

# ── Helpers ─────────────────────────────────────────────────────────────────

usage() {
    cat <<EOF
Usage: $(basename "$0") --production | --development [options]

Modes (exactly one required):
  --production   Run with production settings (multi-worker, localhost, proxy headers)
  --development  Run with development settings (auto-reload, debug logging)

Options:
  --host HOST        Override bind host
  --port PORT        Override bind port
  --workers N        Override number of workers (production only)
  --log-level LEVEL  Override log level (debug|info|warning|error|critical)
  --no-access-log    Disable access logging (production only)
  --help             Show this help message

Environment variables take precedence over defaults; CLI flags override both.
EOF
    exit 0
}

log()  { printf '[%s] %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$*"; }
warn() { log "WARN: $*" >&2; }
die()  { log "FATAL: $*" >&2; exit 1; }

# ── Argument parsing ────────────────────────────────────────────────────────

OVERRIDE_HOST=""
OVERRIDE_PORT=""
OVERRIDE_WORKERS=""
OVERRIDE_LOG_LEVEL=""
OVERRIDE_NO_ACCESS_LOG=0

while [[ $# -gt 0 ]]; do
    case "$1" in
        --production)  MODE="production";  shift ;;
        --development) MODE="development"; shift ;;
        --host)        OVERRIDE_HOST="$2";   shift 2 ;;
        --port)        OVERRIDE_PORT="$2";   shift 2 ;;
        --workers)     OVERRIDE_WORKERS="$2"; shift 2 ;;
        --log-level)   OVERRIDE_LOG_LEVEL="$2"; shift 2 ;;
        --no-access-log) OVERRIDE_NO_ACCESS_LOG=1; shift ;;
        --help|-h)     usage ;;
        *)             die "Unknown option: $1. Use --help for usage." ;;
    esac
done

[[ -z "$MODE" ]] && die "No mode specified. Use --production or --development. See --help."

# ── Resolve effective settings ──────────────────────────────────────────────

if [[ "$MODE" == "production" ]]; then
    HOST="${OVERRIDE_HOST:-$PROD_HOST}"
    PORT="${OVERRIDE_PORT:-$PROD_PORT}"
    WORKERS="${OVERRIDE_WORKERS:-$PROD_WORKERS}"
    LOG_LEVEL="${OVERRIDE_LOG_LEVEL:-$PROD_LOG_LEVEL}"
    ACCESS_LOG_FLAG=""
    if [[ "$OVERRIDE_NO_ACCESS_LOG" -eq 1 ]]; then
        ACCESS_LOG_FLAG="--no-access-log"
    elif [[ "$PROD_ACCESS_LOG" == "1" ]]; then
        ACCESS_LOG_FLAG="--access-log"
    fi
    RELOAD_FLAG=""
    PROXY_HEADERS_FLAG="--proxy-headers"
    FORWARDED_ALLOW_IPS="${FORWARDED_ALLOW_IPS:-127.0.0.1}"
else
    HOST="${OVERRIDE_HOST:-$DEV_HOST}"
    PORT="${OVERRIDE_PORT:-$DEV_PORT}"
    WORKERS=1
    LOG_LEVEL="${OVERRIDE_LOG_LEVEL:-$DEV_LOG_LEVEL}"
    ACCESS_LOG_FLAG="--access-log"
    RELOAD_FLAG=""
    [[ "$DEV_RELOAD" == "1" ]] && RELOAD_FLAG="--reload"
    PROXY_HEADERS_FLAG=""
    FORWARDED_ALLOW_IPS=""
fi

# ── Pre-flight checks ──────────────────────────────────────────────────────

# Ensure uv is available
if ! command -v uv &>/dev/null; then
    die "'uv' not found in PATH. Install it: https://docs.astral.sh/uv/"
fi

# Ensure .env exists (warn only – the app can run without it for dev)
if [[ "$MODE" == "production" && ! -f .env ]]; then
    die ".env file not found. Copy .env.example to .env and configure it."
fi

# ── Port conflict detection ────────────────────────────────────────────────

check_port() {
    if ss -tlnp 2>/dev/null | grep -q ":${1} "; then
        die "Port $1 is already in use. Stop the existing process or use --port to pick another."
    fi
}

check_port "$PORT"

# ── Production: directory setup & PID management ────────────────────────────

if [[ "$MODE" == "production" ]]; then
    mkdir -p "$RUN_DIR" "$LOG_DIR"

    # Stale PID cleanup
    if [[ -f "$PID_FILE" ]]; then
        OLD_PID="$(cat "$PID_FILE")"
        if [[ -n "$OLD_PID" ]] && kill -0 "$OLD_PID" 2>/dev/null; then
            die "news48 is already running (PID $OLD_PID). Stop it first or remove $PID_FILE."
        fi
        warn "Removing stale PID file (was $OLD_PID)"
        rm -f "$PID_FILE"
    fi
fi

# ── Signal handling (production graceful shutdown) ──────────────────────────

cleanup() {
    if [[ "$MODE" == "production" ]]; then
        log "Shutting down (received signal)..."
        if [[ -f "$PID_FILE" ]]; then
            PID="$(cat "$PID_FILE")"
            if [[ -n "$PID" ]] && kill -0 "$PID" 2>/dev/null; then
                kill -TERM "$PID" 2>/dev/null || true
                # Wait up to 30s for the process to exit
                for _ in $(seq 1 30); do
                    kill -0 "$PID" 2>/dev/null || break
                    sleep 1
                done
                if kill -0 "$PID" 2>/dev/null; then
                    warn "Process $PID did not exit in time, sending KILL"
                    kill -KILL "$PID" 2>/dev/null || true
                fi
            fi
            rm -f "$PID_FILE"
        fi
    fi
    log "Goodbye."
    exit 0
}

trap cleanup SIGINT SIGTERM

# ── Build uvicorn command ──────────────────────────────────────────────────

CMD=(
    uv run uvicorn
    news48.web.app:app
    --host "$HOST"
    --port "$PORT"
    --log-level "$LOG_LEVEL"
    $ACCESS_LOG_FLAG
    $RELOAD_FLAG
    $PROXY_HEADERS_FLAG
)

if [[ -n "$FORWARDED_ALLOW_IPS" ]]; then
    CMD+=(--forwarded-allow-ips "$FORWARDED_ALLOW_IPS")
fi

if [[ "$MODE" == "production" ]]; then
    CMD+=(--workers "$WORKERS")
fi

# ── Launch ──────────────────────────────────────────────────────────────────

log "Starting news48 in ${MODE} mode"
log "  Host:    $HOST"
log "  Port:    $PORT"
if [[ "$MODE" == "production" ]]; then
    log "  Workers: $WORKERS"
    log "  Proxy headers: enabled (trust X-Forwarded-* from $FORWARDED_ALLOW_IPS)"
    log "  PID file: $PID_FILE"
    log "  Logs:    $LOG_DIR"
fi
if [[ "$MODE" == "development" ]]; then
    log "  Reload:  $([ -n "$RELOAD_FLAG" ] && echo "enabled" || echo "disabled")"
fi
log "  Log level: $LOG_LEVEL"
log "  Command: ${CMD[*]}"
echo ""

if [[ "$MODE" == "production" ]]; then
    # Start uvicorn in the background, redirect logs
    "${CMD[@]}" \
        >>"$ACCESS_LOG" 2>>"$ERROR_LOG" &
    SERVER_PID=$!
    echo "$SERVER_PID" > "$PID_FILE"
    log "Server started (PID $SERVER_PID)"

    # Wait a beat and confirm the process is still alive
    sleep 1
    if ! kill -0 "$SERVER_PID" 2>/dev/null; then
        die "Server process exited immediately. Check $ERROR_LOG for details."
    fi

    log "Server is running. Logs → $LOG_DIR"
    log "To stop: kill $SERVER_PID"

    # Keep the script alive so the trap can forward signals
    wait "$SERVER_PID" 2>/dev/null && EXIT_CODE=$? || EXIT_CODE=$?
    rm -f "$PID_FILE"
    log "Server exited with code $EXIT_CODE"
    exit "$EXIT_CODE"
else
    # Development: run in foreground (Ctrl+C to stop)
    log "Press Ctrl+C to stop"
    echo ""
    exec "${CMD[@]}"
fi
