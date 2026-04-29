#!/usr/bin/env bash
# =============================================================================
# news48 — Update script for existing installations
# =============================================================================
# Pulls the latest Docker images from ghcr.io and restarts affected services.
#
# Usage:
#   ./scripts/update.sh              # Update all services
#   ./scripts/update.sh --dry-run    # Show what would happen without executing
#   ./scripts/update.sh --no-pull    # Skip image pull, just restart
# =============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
BOLD='\033[1m'
RESET='\033[0m'

# Flags
DRY_RUN=false
NO_PULL=false

# ---------------------------------------------------------------------------
# Parse arguments
# ---------------------------------------------------------------------------
while [[ $# -gt 0 ]]; do
    case "$1" in
        --dry-run)
            DRY_RUN=true
            shift
            ;;
        --no-pull)
            NO_PULL=true
            shift
            ;;
        --help|-h)
            echo "Usage: $0 [--dry-run] [--no-pull] [--help]"
            echo ""
            echo "Update news48 by pulling latest Docker images and restarting services."
            echo ""
            echo "Options:"
            echo "  --dry-run    Show what would happen without executing"
            echo "  --no-pull    Skip image pull, just restart existing containers"
            echo "  --help       Show this help message"
            exit 0
            ;;
        *)
            echo "Unknown option: $1"
            exit 1
            ;;
    esac
done

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
info()  { printf "${BLUE}ℹ${RESET} %s\n" "$1"; }
success() { printf "${GREEN}✓${RESET} %s\n" "$1"; }
warn()  { printf "${YELLOW}⚠${RESET} %s\n" "$1"; }
error() { printf "${RED}✗${RESET} %s\n" "$1"; }

run() {
    if $DRY_RUN; then
        echo "  [dry-run] $*"
    else
        "$@"
    fi
}

# ---------------------------------------------------------------------------
# Pre-flight checks
# ---------------------------------------------------------------------------
printf "\n${BOLD}🔄  news48 — Update${RESET}\n"
printf "${BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${RESET}\n\n"

# Check we're in the project directory
if [[ ! -f "$PROJECT_DIR/docker-compose.yml" ]]; then
    error "docker-compose.yml not found in $PROJECT_DIR"
    echo "Run this script from the news48 project root directory."
    exit 1
fi

# Check docker is available
if ! command -v docker &>/dev/null; then
    error "docker is not installed"
    exit 1
fi

# Check docker compose is available
if ! docker compose version &>/dev/null; then
    error "docker compose is not available"
    exit 1
fi

success "Environment ready"

# ---------------------------------------------------------------------------
# Step 1: Pull latest images
# ---------------------------------------------------------------------------
if $NO_PULL; then
    warn "Skipping image pull (--no-pull)"
else
    printf "\n${BOLD}Step 1/3: Pulling latest images${RESET}\n"
    info "Pulling from ghcr.io/malvavisc0/news48..."
    run docker compose pull
    success "Images up to date"
fi

# ---------------------------------------------------------------------------
# Step 2: Restart services
# ---------------------------------------------------------------------------
printf "\n${BOLD}Step 2/3: Restarting services${RESET}\n"
info "Restarting: web, dramatiq-worker, periodiq-scheduler, db-migrate"

run docker compose up -d web dramatiq-worker periodiq-scheduler db-migrate
success "Services restarted"

# ---------------------------------------------------------------------------
# Step 3: Verify
# ---------------------------------------------------------------------------
printf "\n${BOLD}Step 3/3: Verifying${RESET}\n"
sleep 3

# Check that services are running
RUNNING=$(run docker compose ps --format "{{.Name}}: {{.Status}}" | grep -c "Up" || true)
TOTAL=4

if [[ "$RUNNING" -ge "$TOTAL" ]]; then
    success "All $TOTAL services running"
else
    warn "$RUNNING of $TOTAL services running"
    info "Check logs with: docker compose logs --tail=50"
fi

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
printf "\n${BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${RESET}\n"
info "Service status:"
run docker compose ps

printf "\n${GREEN}${BOLD}Update complete!${RESET}\n\n"

# Show recent logs if not dry-run
if ! $DRY_RUN; then
    read -rp "Show recent logs? (y/N): " show_logs
    if [[ "$show_logs" =~ ^[Yy]$ ]]; then
        run docker compose logs --tail=30 web dramatiq-worker
    fi
fi