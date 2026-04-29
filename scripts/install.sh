#!/usr/bin/env bash
# =============================================================================
# news48 — Docker Installer
# =============================================================================
# Installs news48 on a new server by downloading only the files needed for
# Docker deployment (docker-compose.yml + .env). No source code is downloaded.
#
# Usage:
#   curl -fsSL https://raw.githubusercontent.com/malvavisc0/news48/master/scripts/install.sh | bash
#   ./scripts/install.sh              # Run locally
#
# Prerequisites: curl, docker (with docker compose v2)
# =============================================================================

set -euo pipefail

# GitHub repository
REPO_URL="https://raw.githubusercontent.com/malvavisc0/news48/master"

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
BOLD='\033[1m'
RESET='\033[0m'

# Counters
CHECKS_PASSED=0
CHECKS_FAILED=0
CHECKS_SKIPPED=0

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
info()  { printf "${BLUE}ℹ${RESET} %s\n" "$1"; }
success() { printf "${GREEN}✓${RESET} %s\n" "$1"; }
warn()  { printf "${YELLOW}⚠${RESET} %s\n" "$1"; }
error() { printf "${RED}✗${RESET} %s\n" "$1"; }

# ---------------------------------------------------------------------------
# System requirements check
# ---------------------------------------------------------------------------
printf "\n${BOLD}Checking system requirements...${RESET}\n\n"

# Check curl
printf "  ⏳ ${BOLD}curl${RESET} ... "
if command -v curl &>/dev/null; then
    CURL_VERSION=$(curl --version 2>/dev/null | head -1)
    success "$CURL_VERSION"
    CHECKS_PASSED=$((CHECKS_PASSED + 1))
else
    error "Not found"
    CHECKS_FAILED=$((CHECKS_FAILED + 1))
fi

# Check openssl
printf "  ⏳ ${BOLD}openssl${RESET} ... "
if command -v openssl &>/dev/null; then
    OPENSSL_VERSION=$(openssl version 2>/dev/null | head -1)
    success "$OPENSSL_VERSION"
    CHECKS_PASSED=$((CHECKS_PASSED + 1))
else
    error "Not found"
    CHECKS_FAILED=$((CHECKS_FAILED + 1))
fi

# Check git (optional but useful)
printf "  ⏳ ${BOLD}git${RESET} (optional) ... "
if command -v git &>/dev/null; then
    GIT_VERSION=$(git --version 2>/dev/null)
    success "$GIT_VERSION"
    CHECKS_PASSED=$((CHECKS_PASSED + 1))
else
    warn "Not found (optional, not required)"
    CHECKS_SKIPPED=$((CHECKS_SKIPPED + 1))
fi

# Check Docker
printf "  ⏳ ${BOLD}docker${RESET} ... "
if command -v docker &>/dev/null; then
    DOCKER_VERSION=$(docker --version 2>/dev/null)
    success "$DOCKER_VERSION"
    CHECKS_PASSED=$((CHECKS_PASSED + 1))
else
    error "Not found"
    warn "Docker is required for news48."
    read -rp "Install Docker now? (y/N): " install_docker <&3
    if [[ "$install_docker" =~ ^[Yy]$ ]]; then
        info "Installing Docker..."
        curl -fsSL https://get.docker.com | sh
        sudo usermod -aG docker "$USER"
        success "Docker installed. You may need to log out and back in for group changes."
        printf "  ⏳ ${BOLD}docker${RESET} ... "
        DOCKER_VERSION=$(docker --version 2>/dev/null)
        success "$DOCKER_VERSION"
        CHECKS_PASSED=$((CHECKS_PASSED + 1))
        CHECKS_FAILED=$((CHECKS_FAILED - 1))
    else
        error "Docker is required. Aborting."
        exit 1
    fi
fi

# Check Docker daemon
printf "  ⏳ ${BOLD}docker daemon${RESET} ... "
if docker info &>/dev/null; then
    success "Running"
    CHECKS_PASSED=$((CHECKS_PASSED + 1))
else
    error "Not running"
    CHECKS_FAILED=$((CHECKS_FAILED + 1))
fi

# Check Docker Compose v2
printf "  ⏳ ${BOLD}docker compose${RESET} ... "
if docker compose version &>/dev/null; then
    COMPOSE_VERSION=$(docker compose version --short 2>/dev/null || echo "unknown")
    success "v2 (version $COMPOSE_VERSION)"
    CHECKS_PASSED=$((CHECKS_PASSED + 1))
else
    error "Not available"
    CHECKS_FAILED=$((CHECKS_FAILED + 1))
fi

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
printf "\n${BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${RESET}\n"
printf "  ${BOLD}Results:${RESET} ${GREEN}${CHECKS_PASSED} passed${RESET}, ${RED}${CHECKS_FAILED} failed${RESET}, ${YELLOW}${CHECKS_SKIPPED} skipped${RESET}\n"

if [[ "$CHECKS_FAILED" -gt 0 ]]; then
    printf "\n${RED}${BOLD}Installation aborted: some requirements not met.${RESET}\n"
    exit 1
fi

success "All requirements met!"

# ---------------------------------------------------------------------------
# Installation
# ---------------------------------------------------------------------------
printf "\n${BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${RESET}\n"
printf "${BOLD}📦  Installing news48${RESET}\n"
printf "${BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${RESET}\n\n"

# Determine install directory
if [[ -z "${INSTALL_DIR:-}" ]]; then
    INSTALL_DIR="$HOME/news48"
fi

# Create directory
if [[ -d "$INSTALL_DIR" ]]; then
    warn "Directory $INSTALL_DIR already exists"
    read -rp "Continue? This will overwrite docker-compose.yml and .env (y/N): " confirm
    if [[ ! "$confirm" =~ ^[Yy]$ ]]; then
        info "Aborted."
        exit 0
    fi
else
    info "Creating directory: $INSTALL_DIR"
    mkdir -p "$INSTALL_DIR"
fi

# ---------------------------------------------------------------------------
# Choose LLM deployment mode (MUST come before docker-compose.yml download)
# ---------------------------------------------------------------------------
printf "\n${BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${RESET}\n"
printf "${BOLD}🤖  LLM Deployment Mode${RESET}\n"
printf "${BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${RESET}\n\n"

echo "Choose your LLM deployment mode:"
echo ""
echo "  [1] Local LLM     — Run llama.cpp on your GPU (requires NVIDIA GPU + CUDA)"
echo "  [2] External API  — Use OpenAI, Groq, Ollama, etc. (recommended for production)"
echo ""
read -rp "Select (1-2, default=2): " LLM_MODE_CHOICE

LLM_MODE="external"
if [[ "$LLM_MODE_CHOICE" == "1" ]]; then
    # Check GPU availability
    if docker run --rm --gpus=all nvidia/cuda:12.8.0-base-ubuntu22.04 nvidia-smi &>/dev/null 2>&1; then
        LLM_MODE="local"
    else
        warn "No GPU detected — falling back to External API"
        LLM_MODE="external"
    fi
fi

# Save mode to .deploy file for update.sh to read
printf "%s\n" "$LLM_MODE" > "$INSTALL_DIR/.deploy"
info "LLM mode: $LLM_MODE (saved to .deploy)"

# Download the right docker-compose.yml for the chosen mode
printf "\n${BOLD}Downloading files...${RESET}\n"
if [[ "$LLM_MODE" == "external" ]]; then
    info "Using external LLM mode (llamacpp services excluded)"
    printf "  ⏳ ${BOLD}docker-compose.yml (no-llamacpp version)${RESET} ... "
    if curl -fsSL -o "$INSTALL_DIR/docker-compose.yml" "$REPO_URL/docker-compose.no-llamacpp.yml"; then
        success "Downloaded"
    else
        error "Failed to download docker-compose.no-llamacpp.yml"
        exit 1
    fi
else
    info "Using local LLM mode (llamacpp services included, requires GPU)"
    printf "  ⏳ ${BOLD}docker-compose.yml (with llamacpp)${RESET} ... "
    if curl -fsSL -o "$INSTALL_DIR/docker-compose.yml" "$REPO_URL/docker-compose.yml"; then
        success "Downloaded"
    else
        error "Failed to download docker-compose.yml"
        exit 1
    fi
fi

# Download remaining files
printf "  ⏳ ${BOLD}.env.example${RESET} ... "
if curl -fsSL -o "$INSTALL_DIR/.env.example" "$REPO_URL/.env.example"; then
    success "Downloaded"
else
    warn "Failed to download .env.example (optional)"
fi

printf "  ⏳ ${BOLD}seed.txt${RESET} ... "
if curl -fsSL -o "$INSTALL_DIR/seed.txt" "$REPO_URL/seed.txt"; then
    success "Downloaded"
else
    warn "Failed to download seed.txt (optional — feeds must be added manually)"
fi

printf "  ⏳ ${BOLD}searxng/settings.yml${RESET} ... "
if mkdir -p "$INSTALL_DIR/searxng" && curl -fsSL -o "$INSTALL_DIR/searxng/settings.yml" "$REPO_URL/searxng/settings.yml"; then
    success "Downloaded"
else
    error "Failed to download searxng/settings.yml (required)"
    exit 1
fi

# ---------------------------------------------------------------------------
# Configure .env
# ---------------------------------------------------------------------------
printf "\n${BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${RESET}\n"
printf "${BOLD}⚙️  Configuring .env${RESET}\n"
printf "${BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${RESET}\n\n"

ENV_FILE="$INSTALL_DIR/.env"

if [[ -f "$ENV_FILE" ]]; then
    warn "$ENV_FILE already exists"
    read -rp "Overwrite? (y/N): " confirm
    if [[ ! "$confirm" =~ ^[Yy]$ ]]; then
        info "Keeping existing .env"
    else
        info "Generating new .env from .env.example"
        cp "$ENV_FILE" "${ENV_FILE}.bak" 2>/dev/null || true
        cp ".env.example" "$ENV_FILE" 2>/dev/null || touch "$ENV_FILE"
    fi
else
    info "Creating .env from .env.example"
    if [[ -f "$INSTALL_DIR/.env.example" ]]; then
        cp "$INSTALL_DIR/.env.example" "$ENV_FILE"
    else
        touch "$ENV_FILE"
    fi
fi

# Generate secrets if not set
if grep -q "MYSQL_ROOT_PASSWORD=" "$ENV_FILE" 2>/dev/null; then
    if ! grep -q "^MYSQL_ROOT_PASSWORD=" "$ENV_FILE" 2>/dev/null || grep -q "rootpassword" "$ENV_FILE"; then
        info "Generating random MySQL password..."
        MYSQL_PASS=$(openssl rand -base64 24)
        MYSQL_ROOT_PASS=$(openssl rand -base64 24)
        sed -i "s/^MYSQL_ROOT_PASSWORD=.*/MYSQL_ROOT_PASSWORD=$MYSQL_ROOT_PASS/" "$ENV_FILE"
        sed -i "s/^MYSQL_PASSWORD=.*/MYSQL_PASSWORD=$MYSQL_PASS/" "$ENV_FILE"
        success "MySQL credentials generated"
    fi
fi

if grep -q "SEARXNG_SECRET=" "$ENV_FILE" 2>/dev/null; then
    if ! grep -q "^SEARXNG_SECRET=" "$ENV_FILE" 2>/dev/null || grep -q "changeme" "$ENV_FILE"; then
        info "Generating random SearXNG secret..."
        SEARXNG_SECRET=$(openssl rand -hex 32)
        sed -i "s/^SEARXNG_SECRET=.*/SEARXNG_SECRET=$SEARXNG_SECRET/" "$ENV_FILE"
        success "SearXNG secret generated"
    fi
fi

# ---------------------------------------------------------------------------
# Pull and start
# ---------------------------------------------------------------------------
printf "\n${BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${RESET}\n"
printf "${BOLD}🚀  Starting news48${RESET}\n"
printf "${BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${RESET}\n\n"

cd "$INSTALL_DIR"

printf "  ⏳ ${BOLD}Pulling Docker images...${RESET}\n"
docker compose pull
success "Images pulled"

printf "\n  ⏳ ${BOLD}Starting services...${RESET}\n"
docker compose up -d
success "Services started"

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
printf "\n${BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${RESET}\n"
printf "${BOLD}🎉  Installation complete!${RESET}\n"
printf "${BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${RESET}\n\n"

printf "  ${BOLD}Installed to:${RESET}  $INSTALL_DIR\n"
printf "  ${BOLD}LLM mode:${RESET}      $LLM_MODE\n"
printf "  ${BOLD}Web UI:${RESET}         http://localhost:8000\n"
printf "  ${BOLD}Monitor API:${RESET}    http://localhost:8000/live/monitor\n"
printf "  ${BOLD}Docker logs:${RESET}    docker compose logs -f\n"
printf "  ${BOLD}Update:${RESET}         cd $INSTALL_DIR && ./scripts/update.sh\n"

# Seed the database if seed.txt was downloaded
if [[ -f "$INSTALL_DIR/seed.txt" ]]; then
    printf "\n${BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${RESET}\n"
    printf "${BOLD}🌱  Seeding database${RESET}\n"
    printf "${BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${RESET}\n\n"
    info "Seeding database with initial feeds from seed.txt..."
    cd "$INSTALL_DIR"
    # Copy seed.txt into the web container for the seed command
    if docker cp seed.txt web:/tmp/seed.txt && \
       docker compose exec -T web news48 seed /tmp/seed.txt; then
        success "Database seeded successfully"
    else
        warn "Database seeding failed (feeds can be added manually later)"
    fi
    # Clean up the file inside the container
    docker exec web rm -f /tmp/seed.txt 2>/dev/null || true
fi

printf "\n${BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${RESET}\n"
printf "${BOLD}Next steps:${RESET}\n"
if [[ "$LLM_MODE" == "external" ]]; then
    printf "  1. Open http://localhost:8000 in your browser\n"
    printf "  2. Set API_BASE in .env to your LLM endpoint\n"
    printf "  3. Start fetching: docker compose exec web news48 fetch\n"
    printf "  4. Monitor: docker compose logs -f\n"
else
    printf "  1. Wait for model download to complete (may take minutes)\n"
    printf "  2. Open http://localhost:8000 in your browser\n"
    printf "  3. Start fetching: docker compose exec web news48 fetch\n"
    printf "  4. Monitor: docker compose logs -f\n"
fi
printf "\n${BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${RESET}\n"