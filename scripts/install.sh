#!/usr/bin/env bash
set -euo pipefail

# ─── Terminal input ──────────────────────────────────────────────────────────
# Open /dev/tty once so interactive prompts work even when piped (curl | bash).
if [ -e /dev/tty ]; then
    exec 3< /dev/tty
else
    exec 3<&0
fi

# ─── Configuration ───────────────────────────────────────────────────────────
REPO_RAW="https://raw.githubusercontent.com/malvavisc0/news48/master"
INSTALL_DIR="${NEWS48_DIR:-$HOME/news48}"

# Files needed for Docker deployment
REQUIRED_FILES=(
    "Dockerfile"
    "docker-compose.yml"
    "docker-compose.prod.yml"
    "docker-compose.external-llm.yml"
    ".env.example"
    "seed.txt"
)
REQUIRED_SCRIPTS=(
    "scripts/docker-entrypoint.sh"
    "scripts/download-model.sh"
    "scripts/llamacpp-entrypoint.sh"
)
REQUIRED_CONFIGS=(
    "searxng/settings.yml"
)
REQUIRED_SCORING=(
    ".scoring/latest-assessment.json"
)

# ─── Colors & helpers ────────────────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
BOLD='\033[1m'
DIM='\033[2m'
RESET='\033[0m'

info()    { printf "${BLUE}[info]${RESET}  %s\n" "$*"; }
success() { printf "${GREEN}[ok]${RESET}    %s\n" "$*"; }
warn()    { printf "${YELLOW}[warn]${RESET}  %s\n" "$*"; }
error()   { printf "${RED}[error]${RESET} %s\n" "$*"; }

download() {
    local url="$1"
    local dest="$2"
    local dir
    dir=$(dirname "$dest")
    mkdir -p "$dir"
    if curl -fsSL "$url" -o "$dest" 2>/dev/null; then
        success "Downloaded $(basename "$dest")"
    else
        error "Failed to download $url"
        exit 1
    fi
}

# ─── Cleanup on Ctrl+C ──────────────────────────────────────────────────────
cleanup() {
    printf "\n${YELLOW}Installation cancelled.${RESET}\n"
    exit 1
}
trap cleanup INT

# ─── Banner ──────────────────────────────────────────────────────────────────
printf "\n"
printf "${BOLD}${CYAN}╔═══════════════════════════════════════════════╗${RESET}\n"
printf "${BOLD}${CYAN}║          🗞️  news48 — Docker Installer        ║${RESET}\n"
printf "${BOLD}${CYAN}╚═══════════════════════════════════════════════╝${RESET}\n"
printf "\n"

# ─── Preflight Checks ───────────────────────────────────────────────────────
printf "\n${BOLD}Checking system requirements...${RESET}\n\n"

CHECKS_PASSED=0
CHECKS_FAILED=0
CHECKS_SKIPPED=0

# Check curl
printf "  ⏳ ${BOLD}curl${RESET} ... "
if command -v curl &>/dev/null; then
    CURL_VERSION=$(curl --version 2>/dev/null | head -1)
    printf "${GREEN}✓${RESET} %s\n" "$CURL_VERSION"
    ((CHECKS_PASSED++))
else
    printf "${RED}✗${RESET} Not found\n"
    ((CHECKS_FAILED++))
fi

# Check openssl
printf "  ⏳ ${BOLD}openssl${RESET} ... "
if command -v openssl &>/dev/null; then
    OPENSSL_VERSION=$(openssl version 2>/dev/null | head -1)
    printf "${GREEN}✓${RESET} %s\n" "$OPENSSL_VERSION"
    ((CHECKS_PASSED++))
else
    printf "${RED}✗${RESET} Not found\n"
    ((CHECKS_FAILED++))
fi

# Check git (optional but useful)
printf "  ⏳ ${BOLD}git${RESET} (optional) ... "
if command -v git &>/dev/null; then
    GIT_VERSION=$(git --version 2>/dev/null)
    printf "${GREEN}✓${RESET} %s\n" "$GIT_VERSION"
    ((CHECKS_PASSED++))
else
    printf "${YELLOW}⊘${RESET} Not found (optional, not required)\n"
    ((CHECKS_SKIPPED++))
fi

# Check Docker
printf "  ⏳ ${BOLD}docker${RESET} ... "
if command -v docker &>/dev/null; then
    DOCKER_VERSION=$(docker --version 2>/dev/null)
    printf "${GREEN}✓${RESET} %s\n" "$DOCKER_VERSION"
    ((CHECKS_PASSED++))
else
    printf "${RED}✗${RESET} Not found\n"
    warn "Docker is required for news48."
    read -rp "Install Docker now? (y/N): " install_docker <&3
    if [[ "$install_docker" =~ ^[Yy]$ ]]; then
        info "Installing Docker..."
        curl -fsSL https://get.docker.com | sh
        sudo usermod -aG docker "$USER"
        success "Docker installed. You may need to log out and back in for group changes."
        printf "  ⏳ ${BOLD}docker${RESET} ... "
        DOCKER_VERSION=$(docker --version 2>/dev/null)
        printf "${GREEN}✓${RESET} %s\n" "$DOCKER_VERSION"
        ((CHECKS_PASSED++))
        ((CHECKS_FAILED--))
    else
        error "Docker is required. Aborting."
        exit 1
    fi
fi

# Check Docker daemon
printf "  ⏳ ${BOLD}docker daemon${RESET} ... "
if docker info &>/dev/null; then
    printf "${GREEN}✓${RESET} Running\n"
    ((CHECKS_PASSED++))
else
    printf "${RED}✗${RESET} Not running\n"
    ((CHECKS_FAILED++))
fi

# Check Docker Compose v2
printf "  ⏳ ${BOLD}docker compose${RESET} ... "
if docker compose version &>/dev/null; then
    COMPOSE_VERSION=$(docker compose version --short 2>/dev/null || echo "unknown")
    printf "${GREEN}✓${RESET} v2 (version $COMPOSE_VERSION)\n"
    ((CHECKS_PASSED++))
else
    printf "${RED}✗${RESET} Not available\n"
    ((CHECKS_FAILED++))
fi

printf "\n${BOLD}Requirements Summary:${RESET}\n"
printf "  ${GREEN}✓ Passed:${RESET}  %d\n" "$CHECKS_PASSED"
if [ $CHECKS_FAILED -gt 0 ]; then
    printf "  ${RED}✗ Failed:${RESET}  %d\n" "$CHECKS_FAILED"
fi
if [ $CHECKS_SKIPPED -gt 0 ]; then
    printf "  ${YELLOW}⊘ Skipped:${RESET} %d (optional)\n" "$CHECKS_SKIPPED"
fi
printf "\n"

# Exit if critical checks failed
if [ $CHECKS_FAILED -gt 0 ]; then
    error "Some required dependencies are missing or not working."
    error "Please install or fix the above items and try again."
    exit 1
fi

success "All requirements satisfied. Ready to proceed."

# ─── Download Repository ─────────────────────────────────────────────────────
printf "\n${BOLD}Downloading news48 to $INSTALL_DIR...${RESET}\n"

TARBALL_URL="https://github.com/malvavisc0/news48/archive/refs/heads/master.tar.gz"
TMP_TARBALL=$(mktemp)

if [ -d "$INSTALL_DIR" ] && [ "$(ls -A "$INSTALL_DIR" 2>/dev/null)" ]; then
    warn "$INSTALL_DIR is not empty."
    read -rp "Overwrite with fresh download? (y/N): " overwrite_dir <&3
    if [[ "$overwrite_dir" =~ ^[Yy]$ ]]; then
        rm -rf "$INSTALL_DIR"
    else
        error "Aborting. Choose a different directory or remove the existing one."
        exit 1
    fi
fi

info "Downloading repository tarball..."
if ! curl -fsSL "$TARBALL_URL" -o "$TMP_TARBALL"; then
    error "Failed to download repository. Check your internet connection."
    rm -f "$TMP_TARBALL"
    exit 1
fi

mkdir -p "$INSTALL_DIR"
info "Extracting files..."
tar -xzf "$TMP_TARBALL" -C "$INSTALL_DIR" --strip-components=1
rm -f "$TMP_TARBALL"

cd "$INSTALL_DIR"

# Make scripts executable
for f in "${REQUIRED_SCRIPTS[@]}"; do
    chmod +x "$f" 2>/dev/null || true
done

# Download scoring data (may not be in tarball or may be stale)
for f in "${REQUIRED_SCORING[@]}"; do
    download "${REPO_RAW}/${f}" "${INSTALL_DIR}/${f}"
done

success "All files downloaded to $INSTALL_DIR"

# ─── Enter install directory ─────────────────────────────────────────────────
cd "$INSTALL_DIR"

# ─── Deployment Mode ─────────────────────────────────────────────────────────
printf "\n${BOLD}Select deployment mode:${RESET}\n"
printf "  ${CYAN}1)${RESET} Standard — NVIDIA GPU + Docker-managed LLM (llama.cpp)\n"
printf "  ${CYAN}2)${RESET} External LLM — Use OpenAI, Groq, Ollama, or any OpenAI-compatible API\n"
printf "\n"

DEPLOY_MODE=""
COMPOSE_CMD=()
while true; do
    read -rp "Enter choice [1-2]: " choice <&3
    case "$choice" in
        1)
            DEPLOY_MODE="standard"
            COMPOSE_CMD=(docker compose -f docker-compose.yml -f docker-compose.prod.yml)
            success "Standard deployment (Docker llama.cpp + NVIDIA GPU)"
            break
            ;;
        2)
            DEPLOY_MODE="external"
            COMPOSE_CMD=(docker compose -f docker-compose.yml -f docker-compose.prod.yml)
            success "External LLM deployment"
            break
            ;;
        *)
            warn "Invalid choice. Please enter 1 or 2."
            ;;
    esac
done

# ─── Strip llamacpp services for External LLM mode ──────────────────────────
if [ "$DEPLOY_MODE" = "external" ]; then
    printf "\n${BOLD}Removing llamacpp services from compose files...${RESET}\n"
    python3 << 'PYEOF'
import re

def remove_service_blocks(content, service_names):
    """Remove entire top-level service blocks from docker-compose YAML."""
    lines = content.split('\n')
    result = []
    skip = False
    skip_indent = 0

    for line in lines:
        # Detect a top-level service definition (2-space indent under services:)
        stripped = line.rstrip()
        if not skip:
            # Match service block start: "  servicename:" at indent level 2
            match = re.match(r'^  (\w[\w-]*):(\s|$)', line)
            if match and match.group(1) in service_names:
                skip = True
                skip_indent = 2
                continue
            result.append(line)
        else:
            # Skip until we hit a line at same or lesser indent (next service or end)
            if stripped == '':
                # Keep blank lines if next non-blank line is still under this service
                result.append(line)
                continue
            indent = len(line) - len(line.lstrip())
            if indent <= skip_indent:
                skip = False
                # This line starts a new block — check if it's another service to skip
                match = re.match(r'^  (\w[\w-]*):(\s|$)', line)
                if match and match.group(1) in service_names:
                    skip = True
                    continue
                result.append(line)
            # else: still inside skipped block, drop the line

    return '\n'.join(result)

def remove_depends_on_llamacpp(content):
    """Remove llamacpp dependency from other services' depends_on blocks."""
    lines = content.split('\n')
    result = []
    in_depends = False
    dep_indent = 0

    for line in lines:
        stripped = line.rstrip()
        if not in_depends:
            if re.match(r'^(\s+)depends_on:\s*$', line):
                in_depends = True
                dep_indent = len(line) - len(line.lstrip())
                result.append(line)
            else:
                result.append(line)
        else:
            indent = len(line) - len(line.lstrip()) if stripped else dep_indent + 2
            if indent <= dep_indent:
                in_depends = False
                result.append(line)
            elif re.match(r'^\s+llamacpp:\s*$', line):
                # Skip the llamacpp depends_on entry
                continue
            elif re.match(r'^\s+condition:\s*service_healthy\s*$', line):
                # Check if previous kept line was the llamacpp entry we removed
                # If the last result line is the depends_on: header and we just removed llamacpp,
                # this condition line belongs to llamacpp — skip it
                if result and re.match(r'^\s+depends_on:\s*$', result[-1]):
                    # This condition belongs to a service we already kept, don't skip
                    result.append(line)
                elif result and not re.match(r'^\s+\w[\w-]*:\s*$', result[-1]):
                    # Previous line wasn't a service key — this condition is orphaned, skip
                    continue
                else:
                    result.append(line)
            else:
                result.append(line)

    return '\n'.join(result)

services_to_remove = {'llamacpp', 'llamacpp-init'}

for fname in ['docker-compose.yml', 'docker-compose.prod.yml']:
    try:
        with open(fname) as f:
            content = f.read()

        # Remove entire service blocks
        cleaned = remove_service_blocks(content, services_to_remove)

        # Remove depends_on references to llamacpp
        cleaned = remove_depends_on_llamacpp(cleaned)

        if cleaned != content:
            with open(fname, 'w') as f:
                f.write(cleaned)
            print(f'  llamacpp services removed from {fname}')
        else:
            print(f'  No llamacpp services found in {fname}')
    except FileNotFoundError:
        print(f'  {fname} not found, skipping')

print('Done')
PYEOF
fi

# ─── NVIDIA Check (Standard mode only) ──────────────────────────────────────
if [ "$DEPLOY_MODE" = "standard" ]; then
    printf "\n${BOLD}Checking NVIDIA GPU support...${RESET}\n"

    if command -v nvidia-smi &>/dev/null; then
        success "nvidia-smi found"
        nvidia-smi --query-gpu=name,memory.total --format=csv,noheader 2>/dev/null | while read -r line; do
            info "  GPU: $line"
        done
    else
        warn "nvidia-smi not found. GPU acceleration may not work."
    fi

    if docker run --rm --gpus all nvidia/cuda:12.0-base nvidia-smi &>/dev/null; then
        success "NVIDIA Container Toolkit working"
    else
        warn "NVIDIA Container Toolkit test failed."
        warn "Install it: https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/install-guide.html"
        read -rp "Continue anyway? (y/N): " continue_no_gpu <&3
        if [[ ! "$continue_no_gpu" =~ ^[Yy]$ ]]; then
            error "Aborting. Please install NVIDIA Container Toolkit first."
            exit 1
        fi
    fi

    printf "\n"
    read -rp "HuggingFace token (leave empty for public models): " hf_token <&3
fi

# ─── Environment Configuration ───────────────────────────────────────────────
printf "\n${BOLD}Configuring environment...${RESET}\n"

if [ -f ".env" ]; then
    warn ".env file already exists."
    read -rp "Overwrite with fresh configuration? (y/N): " overwrite_env <&3
    if [[ ! "$overwrite_env" =~ ^[Yy]$ ]]; then
        info "Keeping existing .env"
    else
        cp .env.example .env
        success "Created .env from .env.example"
    fi
else
    cp .env.example .env
    success "Created .env from .env.example"
fi

# Generate secure passwords
MYSQL_ROOT_PASSWORD=$(openssl rand -hex 16)
MYSQL_PASSWORD=$(openssl rand -hex 16)
SEARXNG_SECRET=$(python3 -c "import secrets; print(secrets.token_hex(32))" 2>/dev/null || openssl rand -hex 32)

# Apply generated values to .env
if [ -f ".env" ]; then
    sed -i "s|^MYSQL_ROOT_PASSWORD=.*|MYSQL_ROOT_PASSWORD=${MYSQL_ROOT_PASSWORD}|" .env
    sed -i "s|^MYSQL_PASSWORD=.*|MYSQL_PASSWORD=${MYSQL_PASSWORD}|" .env
    sed -i "s|^DATABASE_URL=.*|DATABASE_URL=mysql+mysqlconnector://news48:${MYSQL_PASSWORD}@mysql:3306/news48|" .env
    sed -i "s|^SEARXNG_SECRET=.*|SEARXNG_SECRET=${SEARXNG_SECRET}|" .env
    sed -i "s|^WEB_RELOAD=.*|WEB_RELOAD=0|" .env

    # Apply HF token if provided during NVIDIA check
    if [ -n "${hf_token:-}" ]; then
        sed -i "s|^HF_TOKEN=.*|HF_TOKEN=${hf_token}|" .env
        success "HF_TOKEN configured"
    fi

    success "Generated secure passwords for MySQL and SearXNG"
fi

# External LLM configuration
if [ "$DEPLOY_MODE" = "external" ]; then
    printf "\n${BOLD}Configure external LLM endpoint:${RESET}\n"
    printf "${DIM}Examples:${RESET}\n"
    printf "  OpenAI:      https://api.openai.com/v1\n"
    printf "  Groq:        https://api.groq.com/openai/v1\n"
    printf "  Ollama:      http://localhost:11434/v1\n"
    printf "  Host llama:  http://localhost:8080/v1\n"
    printf "\n"

    read -rp "API_BASE URL: " api_base <&3
    read -rp "API_KEY (leave empty for local): " api_key <&3
    read -rp "MODEL name (e.g. gpt-4o, llama3.1-8b): " model_name <&3

    if [ -z "$api_base" ]; then
        error "API_BASE is required for external LLM mode."
        exit 1
    fi

    sed -i "s|^API_BASE=.*|API_BASE=${api_base}|" .env
    sed -i "s|^API_KEY=.*|API_KEY=${api_key:-nokey}|" .env
    sed -i "s|^MODEL=.*|MODEL=${model_name}|" .env

    success "External LLM configured: ${api_base} (${model_name})"
fi

# ─── Create data directory ──────────────────────────────────────────────────
mkdir -p "$INSTALL_DIR/data"
success "Data directory ready"

# ─── Clean stale volumes ────────────────────────────────────────────────────
# If we generated fresh passwords, old MySQL volumes will have mismatched
# credentials. Remove them so MySQL re-initializes with the new passwords.
if [ -n "${MYSQL_PASSWORD:-}" ]; then
    printf "\n${BOLD}Cleaning stale Docker volumes...${RESET}\n"
    "${COMPOSE_CMD[@]}" down -v 2>/dev/null || true
    success "Volumes cleaned"
fi

# ─── Launch Services ─────────────────────────────────────────────────────────
printf "\n${BOLD}Pulling images and starting services...${RESET}\n"
info "This may take several minutes on first run (pulling images, starting containers)."
printf "\n"

"${COMPOSE_CMD[@]}" up -d --pull always --no-build

printf "\n"
success "Services started!"

# ─── Health Check ────────────────────────────────────────────────────────────
printf "\n${BOLD}Waiting for services to become healthy...${RESET}\n"

MAX_WAIT=180
ELAPSED=0
SPINNER=('⠋' '⠙' '⠹' '⠸' '⠼' '⠴' '⠦' '⠧' '⠇' '⠏')

while [ $ELAPSED -lt $MAX_WAIT ]; do
    if curl -sf http://localhost:8000/health &>/dev/null; then
        printf "\r${GREEN}[ok]${RESET}    Web UI is healthy!                    \n"
        break
    fi

    SPINNER_CHAR="${SPINNER[$((ELAPSED % ${#SPINNER[@]}))]}"
    printf "\r  ${CYAN}${SPINNER_CHAR}${RESET} Waiting for services... (${ELAPSED}s / ${MAX_WAIT}s)"
    sleep 2
    ELAPSED=$((ELAPSED + 2))
done

if [ $ELAPSED -ge $MAX_WAIT ]; then
    printf "\r${YELLOW}[warn]${RESET}  Services may still be starting. Check logs below.       \n"
fi

# ─── Service Status ──────────────────────────────────────────────────────────
printf "\n${BOLD}Service status:${RESET}\n"
"${COMPOSE_CMD[@]}" ps --format "table {{.Name}}\t{{.Status}}\t{{.Ports}}" 2>/dev/null || \
    "${COMPOSE_CMD[@]}" ps

# ─── Install CLI wrapper ───────────────────────────────────────────────────
printf "\n${BOLD}Installing CLI wrapper...${RESET}\n"

WRAPPER_DIR="${HOME}/.local/bin"
WRAPPER_PATH="${WRAPPER_DIR}/news48"

mkdir -p "$WRAPPER_DIR"

cat > "$WRAPPER_PATH" << WRAPPER_EOF
#!/usr/bin/env bash
# news48 CLI — installed by the news48 Docker installer.
# Runs commands inside the dramatiq-worker container.
cd "${INSTALL_DIR}" || { echo "news48: cannot cd to ${INSTALL_DIR}" >&2; exit 1; }
exec docker compose -f docker-compose.yml -f docker-compose.prod.yml \\
    exec -T dramatiq-worker news48 "\$@"
WRAPPER_EOF

chmod +x "$WRAPPER_PATH"

# Ensure ~/.local/bin is in PATH
SHELL_RC=""
if [ -f "$HOME/.zshrc" ] && { [ -n "${ZSH_VERSION:-}" ] || command -v zsh &>/dev/null; }; then
    SHELL_RC="$HOME/.zshrc"
elif [ -f "$HOME/.bashrc" ]; then
    SHELL_RC="$HOME/.bashrc"
fi

if ! echo "$PATH" | tr ':' '\n' | grep -qx "${WRAPPER_DIR}"; then
    if [ -n "$SHELL_RC" ]; then
        {
            echo ''
            echo '# news48 CLI wrapper'
            echo 'export PATH="$HOME/.local/bin:$PATH"'
        } >> "$SHELL_RC"
        success "Added ~/.local/bin to PATH in $(basename "$SHELL_RC")"
        info "Run 'source $(basename "$SHELL_RC")' or open a new terminal to use 'news48' directly"
    else
        info "Add ~/.local/bin to your PATH to use 'news48' directly"
    fi
else
    success "~/.local/bin already in PATH"
fi

success "CLI wrapper installed at $WRAPPER_PATH"

# ─── Seed Database ──────────────────────────────────────────────────────────
COMPOSE_CMD_STR="${COMPOSE_CMD[*]}"
printf "\n${BOLD}Seeding database...${RESET}\n"
if "${COMPOSE_CMD[@]}" exec -T dramatiq-worker news48 seed /app/seed.txt 2>&1; then
    success "Feeds seeded"
else
    warn "Seeding failed — you can run it manually later:"
    info "  ${COMPOSE_CMD_STR} exec dramatiq-worker news48 seed /app/seed.txt"
fi

# ─── Detect IP ───────────────────────────────────────────────────────────────
# Try to get the machine's LAN IP for remote access
HOST_IP=$(hostname -I 2>/dev/null | awk '{print $1}')
[ -z "$HOST_IP" ] && HOST_IP=$(ip -4 addr show scope global 2>/dev/null | awk '/inet /{print $2}' | cut -d/ -f1 | head -1)
[ -z "$HOST_IP" ] && HOST_IP=$(ifconfig 2>/dev/null | awk '/inet /{print $2}' | grep -v '127.0.0.1' | head -1)
[ -z "$HOST_IP" ] && HOST_IP="localhost"

# ─── Summary ─────────────────────────────────────────────────────────────────
printf "\n"
printf "${BOLD}${GREEN}╔════════════════════════════════════════════════════════╗${RESET}\n"
printf "${BOLD}${GREEN}║                                                        ║${RESET}\n"
printf "${BOLD}${GREEN}║          🎉  news48 Installation Complete  🎉          ║${RESET}\n"
printf "${BOLD}${GREEN}║                                                        ║${RESET}\n"
printf "${BOLD}${GREEN}╚════════════════════════════════════════════════════════╝${RESET}\n"
printf "\n"

printf "${BOLD}📦  Installation Details${RESET}\n"
printf "   └─ ${BOLD}Location:${RESET}   $INSTALL_DIR\n"
printf "   └─ ${BOLD}Mode:${RESET}       $([ "$DEPLOY_MODE" = "standard" ] && echo "Standard (NVIDIA GPU)" || echo "External LLM")\n"
printf "   └─ ${BOLD}Wrapper:${RESET}    ${CYAN}$WRAPPER_PATH${RESET}\n"
printf "\n"

printf "${BOLD}🌐  Access Your Installation${RESET}\n"
printf "   ├─ ${BOLD}Web UI:${RESET}      ${CYAN}http://${HOST_IP}:8000${RESET}\n"
printf "   ├─ ${BOLD}Health Check:${RESET} ${CYAN}http://${HOST_IP}:8000/health${RESET}\n"
printf "   └─ ${BOLD}Local Access:${RESET}  Open a new terminal and use 'news48' directly\n"
printf "      ${DIM}(or run: source ~/.bashrc or source ~/.zshrc)${RESET}\n"
printf "\n"

printf "${BOLD}⚡  Quick Start Commands${RESET}\n"
printf "   ${DIM}# After opening a new terminal:${RESET}\n"
printf "   ├─ ${CYAN}news48 stats${RESET}             ${DIM}View system information${RESET}\n"
printf "   ├─ ${CYAN}news48 feeds list${RESET}        ${DIM}Show all configured feeds${RESET}\n"
printf "   ├─ ${CYAN}news48 briefing${RESET}          ${DIM}Get the latest news briefing${RESET}\n"
printf "   └─ ${CYAN}news48 mcp create-key${RESET}    ${DIM}Create MCP API key${RESET}\n"
printf "\n"

printf "${BOLD}🐳  Docker Management${RESET}\n"
printf "   ${DIM}# Run from: %s${RESET}\n" "$INSTALL_DIR"
printf "   ├─ ${CYAN}%s logs -f${RESET}\n" "$COMPOSE_CMD_STR"
printf "   ├─ ${CYAN}%s ps${RESET}\n" "$COMPOSE_CMD_STR"
printf "   ├─ ${CYAN}%s restart dramatiq-worker${RESET}\n" "$COMPOSE_CMD_STR"
printf "   └─ ${CYAN}%s down${RESET}\n" "$COMPOSE_CMD_STR"
printf "\n"

printf "${BOLD}📝  Next Steps${RESET}\n"
printf "   1. ${DIM}Edit${RESET} ${BOLD}${INSTALL_DIR}/seed.txt${RESET} ${DIM}to add your RSS feed URLs${RESET}\n"
printf "   2. ${DIM}Seed the database:${RESET} ${CYAN}news48 seed /app/seed.txt${RESET}\n"
printf "   3. ${DIM}Monitor progress:${RESET} ${CYAN}%s logs -f dramatiq-worker${RESET}\n" "$COMPOSE_CMD_STR"
printf "\n"

printf "${BOLD}📚  Documentation${RESET}\n"
printf "   ├─ Deployment Guide:   ${CYAN}${INSTALL_DIR}/docs/deployment.md${RESET}\n"
printf "   ├─ MCP Tools:          ${CYAN}${INSTALL_DIR}/docs/mcp-tools.md${RESET}\n"
printf "   └─ GitHub Repo:        ${CYAN}https://github.com/malvavisc0/news48${RESET}\n"
printf "\n"

printf "${DIM}💡 Note: The sentinel agent will auto-seed if the database is empty.${RESET}\n"
printf "${DIM}📧 For troubleshooting, check logs: ${COMPOSE_CMD_STR} logs${RESET}\n"
printf "\n"