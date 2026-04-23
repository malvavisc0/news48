# Deployment Guide

Two deployment modes:

| Mode | Use case | llama.cpp | Compose files |
|------|----------|-----------|---------------|
| **Standard** | x86 server with NVIDIA GPU | Docker container | `docker-compose.yml` + `docker-compose.prod.yml` |
| **Jetson** | ARM64 with host llama.cpp | Host process | `docker-compose.yml` + `docker-compose.jetson.yml` |

---

## Table of Contents

- [Compose File Reference](#compose-file-reference)
- [Standard Deployment (x86 Server)](#standard-deployment-x86-server)
- [Jetson / ARM64 Deployment](#jetson--arm64-deployment)
- [Environment Variables](#environment-variables)
- [Operations](#operations)
- [Data & Volumes](#data--volumes)
- [Security Hardening](#security-hardening)
- [Architecture](#architecture)
- [Local Development](#local-development)
- [Troubleshooting](#troubleshooting)

---

## Compose File Reference

| File | Purpose | Auto-loaded? |
|------|---------|--------------|
| [`docker-compose.yml`](../docker-compose.yml) | Base service definitions (all 10 services) | Yes |
| [`docker-compose.override.yml`](../docker-compose.override.yml) | Dev overrides (hot reload, bind mounts, debug logging) | Yes (dev only) |
| [`docker-compose.prod.yml`](../docker-compose.prod.yml) | Production overrides (pre-built images, resource limits, security hardening) | No — pass with `-f` |
| [`docker-compose.jetson.yml`](../docker-compose.jetson.yml) | Replaces Docker llamacpp with no-op stubs for host llama.cpp | No — pass with `-f` |

> **How Docker Compose merges files:** When you pass multiple `-f` flags, later files override earlier ones. The override file is loaded automatically in development but **not** in production — you must explicitly specify `docker-compose.prod.yml`.

> **Tip:** Set a shell alias to avoid repeating the long command:
> ```bash
> alias dc='docker compose -f docker-compose.yml -f docker-compose.prod.yml'
> ```

---

## Standard Deployment (x86 Server)

Uses Docker-managed llama.cpp with NVIDIA GPU passthrough.

### Prerequisites

- Docker Engine 24+ and Docker Compose v2
- NVIDIA drivers + [nvidia-container-toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/install-guide.html)
- HuggingFace token (only if using gated/private models)

### 1. Install Docker & NVIDIA Container Toolkit

```bash
# Install Docker
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER
# Log out and back in for group changes to take effect

# Verify GPU passthrough works
docker run --rm --gpus all nvidia/cuda:12.0-base nvidia-smi
```

### 2. Copy Files to Server

Only these files are needed on the production server — no source code required since production uses pre-built images from GHCR:

```
news48/
├── docker-compose.yml
├── docker-compose.prod.yml
├── .env                        # create from .env.example
├── seed.txt                    # initial feed URLs (mounted by dramatiq-worker)
├── scripts/
│   ├── docker-entrypoint.sh    # waits for MySQL, then exec's the CMD
│   ├── download-model.sh       # mounted by llamacpp-init
│   └── llamacpp-entrypoint.sh  # mounted by llamacpp
└── searxng/
    └── settings.yml            # SearXNG engine configuration
```

```bash
mkdir -p ~/news48/scripts ~/news48/searxng
scp docker-compose.yml docker-compose.prod.yml seed.txt user@server:~/news48/
scp scripts/*.sh user@server:~/news48/scripts/
scp searxng/settings.yml user@server:~/news48/searxng/
scp .env.example user@server:~/news48/.env
```

### 3. Configure Environment

```bash
cd ~/news48
# Edit .env — see the Environment Variables section below for all options
vim .env
```

**At minimum, generate secure passwords for production:**

```bash
# Generate random passwords
echo "MYSQL_ROOT_PASSWORD=$(openssl rand -hex 16)" >> .env
echo "MYSQL_PASSWORD=$(openssl rand -hex 16)" >> .env
echo "SEARXNG_SECRET=$(python3 -c 'import secrets; print(secrets.token_hex(32))')" >> .env
```

> ⚠️ **Important:** If you change `MYSQL_PASSWORD`, you must also update the `DATABASE_URL` to match:
> ```
> DATABASE_URL=mysql+mysqlconnector://news48:<your-password>@mysql:3306/news48
> ```

### 4. Launch

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d
```

On first run, the `llamacpp-init` container downloads the GGUF model file. This can take several minutes depending on model size and network speed. Monitor progress with:

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml logs -f llamacpp-init
```

### Startup Order

The services start in a specific dependency order managed by Docker Compose healthchecks:

1. **mysql** starts and waits for healthcheck (`mysqladmin ping`)
2. **redis** starts and waits for healthcheck (`redis-cli ping`)
3. **llamacpp-init** downloads the model, then exits
4. **llamacpp** starts after init completes, waits for healthcheck (`curl /health`)
5. **db-migrate** runs Alembic migrations once MySQL is healthy, then exits
6. **web**, **dramatiq-worker**, **periodiq-scheduler** start after all dependencies are healthy
7. **searxng**, **byparr**, **dozzle** start independently

### 5. Verify

```bash
# Check all services are running
docker compose -f docker-compose.yml -f docker-compose.prod.yml ps

# Test individual endpoints
curl -s http://localhost:8000/health    # web (FastAPI)
curl -s http://localhost:8080/health    # llamacpp

# Check logs for errors
docker compose -f docker-compose.yml -f docker-compose.prod.yml logs --tail=50
```

---

## Jetson / ARM64 Deployment

Uses a **host-native llama.cpp** instance instead of the Docker container. The [`docker-compose.jetson.yml`](../docker-compose.jetson.yml) override replaces `llamacpp` and `llamacpp-init` with no-op busybox stubs that always report healthy. This avoids pulling CUDA images that may not work on ARM64.

### Prerequisites

- Docker Engine 24+ and Docker Compose v2
- llama.cpp compiled and running on the host (e.g., `http://jetson:7070/v1`)
- The hostname `jetson` must resolve from inside Docker containers (or use the host's IP address)

### 1. Configure Environment

```bash
cd ~/news48
cp .env.example .env
```

Set these values in `.env` to point at your host llama.cpp:

```bash
API_BASE=http://jetson:7070/v1   # or http://<host-ip>:7070/v1
API_KEY=                          # leave empty for local llama.cpp
MODEL=granite-4.1-8b              # must match the model loaded in llama.cpp
```

### 2. Launch

```bash
docker compose -f docker-compose.yml -f docker-compose.jetson.yml up -d
```

### 3. Verify

```bash
# Check services are running (llamacpp will show as "running" but is just a stub)
docker compose -f docker-compose.yml -f docker-compose.jetson.yml ps

# Verify llama.cpp is reachable from inside Docker
docker compose exec web python -c \
  "import urllib.request; print(urllib.request.urlopen('http://jetson:7070/v1/models').read())"
```

### Combining Jetson + Production Overrides

For a hardened Jetson deployment with resource limits and pre-built images:

```bash
docker compose \
  -f docker-compose.yml \
  -f docker-compose.prod.yml \
  -f docker-compose.jetson.yml \
  up -d
```

> **Note:** The Jetson override must come **after** the prod override so it correctly replaces the llamacpp service.

---

## Environment Variables

Create your `.env` file from [`.env.example`](../.env.example). Below is the complete reference.

### Core / Required

| Variable | Description | Default | Example |
|----------|-------------|---------|---------|
| `MODEL` | LLM model name passed to agents | — | `granite-4.1-8b` |
| `API_BASE` | LLM API base URL | — | `http://llamacpp:8080/v1` |
| `API_KEY` | LLM API key (empty string for local llama.cpp) | — | `nokey` |
| `CONTEXT_WINDOW` | Max context window for agent prompts | `49152` | `131072` |
| `DATABASE_URL` | Full MySQL connection string | — | `mysql+mysqlconnector://news48:news48@mysql:3306/news48` |
| `MYSQL_ROOT_PASSWORD` | MySQL root password | `rootpassword` | Use `openssl rand -hex 16` |
| `MYSQL_DATABASE` | MySQL database name | `news48` | `news48` |
| `MYSQL_USER` | MySQL application user | `news48` | `news48` |
| `MYSQL_PASSWORD` | MySQL application user password | `news48` | Use `openssl rand -hex 16` |
| `REDIS_URL` | Redis connection URL | `redis://redis:6379/0` | `redis://redis:6379/0` |
| `SEARXNG_SECRET` | SearXNG secret key | `changeme` | Use `python3 -c "import secrets; print(secrets.token_hex(32))"` |

### LLM / llama.cpp (Docker mode only)

These configure the Docker-managed llamacpp container. Not needed for Jetson deployments.

| Variable | Default | Description |
|----------|---------|-------------|
| `LLAMACPP_MODEL_REPO` | `mradermacher/claude-oss-i1-GGUF` | HuggingFace repository |
| `LLAMACPP_MODEL_FILE` | `claude-oss.i1-Q6_K.gguf` | GGUF filename within the repo |
| `LLAMACPP_CTX_SIZE` | `131072` | Context window size (tokens) |
| `LLAMACPP_N_GPU_LAYERS` | `999` | Layers to offload to GPU (`999` = all) |
| `LLAMACPP_PARALLEL` | `4` | Max concurrent inference requests |
| `LLAMACPP_THREADS` | `8` | CPU threads for computation |
| `LLAMACPP_PORT` | `8080` | Server listen port |
| `LLAMACPP_CACHE_TYPE_K` | `q8_0` | KV-cache quantization for keys |
| `LLAMACPP_CACHE_TYPE_V` | `q8_0` | KV-cache quantization for values |
| `LLAMACPP_FLASH_ATTN` | `on` | Enable flash attention |
| `HF_TOKEN` | — | HuggingFace token for gated/private models |

### Web Server

| Variable | Default | Description |
|----------|---------|-------------|
| `WEB_HOST` | `0.0.0.0` | Bind address |
| `WEB_PORT` | `8000` | Listen port |
| `WEB_WORKERS` | `1` (dev) / `4` (prod) | Uvicorn worker count |
| `WEB_LOG_LEVEL` | `info` | Log verbosity (`debug`, `info`, `warning`, `error`) |
| `WEB_RELOAD` | `0` | Auto-reload on code changes (`1` = enabled, dev only) |
| `WEB_ACCESS_LOG` | `1` | Enable HTTP access logging |
| `FORWARDED_ALLOW_IPS` | `127.0.0.1` | Trusted proxy IPs (set to `*` behind a reverse proxy) |

### External Services

| Variable | Default | Description |
|----------|---------|-------------|
| `BYPARR_API_URL` | `http://byparr:8191/v1` | Byparr headless browser API |
| `SEARXNG_URL` | `http://searxng:8080` | SearXNG search API |

### Email Alerts (Optional)

| Variable | Default | Description |
|----------|---------|-------------|
| `SMTP_HOST` | — | SMTP server hostname |
| `SMTP_PORT` | `587` | SMTP port |
| `SMTP_USER` | — | SMTP username |
| `SMTP_PASS` | — | SMTP password |
| `SMTP_FROM` | — | Sender email address |
| `MONITOR_EMAIL_TO` | — | Alert recipient email |

---

## Operations

All examples below use the production compose command. If you set up the alias from the [Compose File Reference](#compose-file-reference), replace the long command with `dc`.

### Update to Latest Images

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml pull
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d
```

> Images are published to `ghcr.io/malvavisc0/news48:latest-web` and `ghcr.io/malvavisc0/news48:latest-worker`.

### View Logs

```bash
# All services (follow mode)
docker compose -f docker-compose.yml -f docker-compose.prod.yml logs -f

# Single service
docker compose -f docker-compose.yml -f docker-compose.prod.yml logs -f dramatiq-worker

# Last 100 lines
docker compose -f docker-compose.yml -f docker-compose.prod.yml logs --tail=100 web
```

> **Dozzle** provides a web-based log viewer. In dev, it's available at `http://localhost:9999`. It supports live tailing, filtering, and container shell access.

### Shell into a Container

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml exec dramatiq-worker bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml exec web bash
```

> **Note:** The production web container runs with `read_only: true` — you can't write to the filesystem except `/tmp` and `/data`.

### Run CLI Commands

```bash
# Run a news48 CLI command inside the worker container
docker compose -f docker-compose.yml -f docker-compose.prod.yml exec dramatiq-worker \
  python -m news48.cli.main stats
```

### Restart a Service

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml restart web
```

### Stop Everything

```bash
# Stop containers (preserves volumes)
docker compose -f docker-compose.yml -f docker-compose.prod.yml down

# Stop and remove volumes (⚠️ DESTROYS ALL DATA)
docker compose -f docker-compose.yml -f docker-compose.prod.yml down -v
```

### Run Database Migrations Manually

Migrations run automatically on startup via the `db-migrate` init container. To run manually:

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml run --rm db-migrate
```

---

## Data & Volumes

The stack uses five named Docker volumes:

| Volume | Service | Contents |
|--------|---------|----------|
| `mysql-data` | mysql | Database files |
| `redis-data` | redis | Redis AOF + RDB snapshots |
| `llamacpp-models` | llamacpp-init, llamacpp | Downloaded GGUF model files |
| `news48-data` | web, dramatiq-worker, periodiq-scheduler | Application data (downloaded articles, etc.) |
| `dozzle-data` | dozzle | Dozzle UI state |

### Backup MySQL

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml exec mysql \
  mysqldump -u root -p"$MYSQL_ROOT_PASSWORD" news48 > backup_$(date +%Y%m%d).sql
```

### Restore MySQL

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml exec -i mysql \
  mysql -u root -p"$MYSQL_ROOT_PASSWORD" news48 < backup_20250423.sql
```

### Change the LLM Model

To switch to a different GGUF model:

1. Update `LLAMACPP_MODEL_REPO`, `LLAMACPP_MODEL_FILE`, and `MODEL` in `.env`
2. Remove the old model volume: `docker volume rm news48_llamacpp-models`
3. Restart: the `llamacpp-init` container will download the new model

---

## Security Hardening

The production compose file (`docker-compose.prod.yml`) applies these security measures:

| Measure | Services | Description |
|---------|----------|-------------|
| `read_only: true` | web | Read-only root filesystem |
| `cap_drop: ALL` | web | Drop all Linux capabilities |
| `no-new-privileges` | web | Prevent privilege escalation |
| `tmpfs: /tmp` | web | Writable temp with `noexec,nosuid` (64 MB) |
| Resource limits | all | CPU and memory limits per container |
| `restart: unless-stopped` | all | Auto-restart on failure |
| Healthchecks | all | Automatic health monitoring |

### Production Resource Limits

| Service | Memory | CPU |
|---------|--------|-----|
| web | 512 MB | 1.0 |
| mysql | 512 MB | 1.0 |
| searxng | 512 MB | 1.0 |
| byparr | 512 MB | 1.0 |
| redis | 512 MB | 1.0 |
| dramatiq-worker | 2 GB | 2.0 |
| periodiq-scheduler | 256 MB | 0.5 |
| llamacpp | — (GPU) | — |

> Adjust these in `docker-compose.prod.yml` based on your server's resources. The dramatiq-worker needs more memory as it runs LLM agents.

---

## Architecture

### Services Overview

| Service | Role | Port |
|---------|------|------|
| **web** | FastAPI web frontend | 8000 |
| **mysql** | Primary database (MySQL 8.0) | 3306 |
| **redis** | Task queue broker (Dramatiq) + cache | 6379 (API), 8001 (RedisInsight) |
| **llamacpp** | LLM inference server (llama.cpp) | 8080 |
| **llamacpp-init** | One-shot model downloader | — |
| **db-migrate** | One-shot Alembic migration runner | — |
| **dramatiq-worker** | Background task worker (agents) | — |
| **periodiq-scheduler** | Periodic task scheduler (cron-like) | — |
| **searxng** | Meta-search engine for fact-checking | 8080 (internal) |
| **byparr** | Headless browser for scraping | 8191 (internal) |
| **dozzle** | Web-based log viewer | 8080 (internal), 9999 (dev) |

### Standard (Docker llama.cpp)

```
                           ┌──────────────────┐
                           │   llamacpp-init   │  (one-shot: downloads model)
                           └────────┬─────────┘
                                    │ volume: llamacpp-models
                                    ▼
┌─────────────┐     ┌──────────┐  ┌──────────────┐  ┌──────────┐
│  web :8000  │────▶│  mysql   │  │   llamacpp   │  │  redis   │
└──────┬──────┘     │  :3306   │  │  :8080 (GPU) │  │  :6379   │
       │            └──────────┘  └──────────────┘  └────┬─────┘
       │                 ▲                ▲               │
       │                 │                │               ▼
       │            ┌────┴─────┐          │     ┌──────────────────┐
       │            │db-migrate│          │     │ dramatiq-worker  │
       │            │(one-shot)│          │     └────────┬─────────┘
       │            └──────────┘          │              │
       │                                  │              ▼
       │  ┌────────────────────┐    ┌─────┴────┐  ┌──────────┐
       │  │periodiq-scheduler  │    │ searxng   │  │  byparr  │
       │  │   (cron tasks)     │    └──────────┘  └──────────┘
       │  └────────────────────┘
       │
       ▼
┌──────────┐
│  dozzle  │  (log viewer)
└──────────┘
```

### Jetson (Host llama.cpp)

```
┌──────────────────────────────────────────────────────┐
│  Host: Jetson Orin NX                                │
│                                                      │
│  ┌──────────────┐                                    │
│  │  llama.cpp   │ :7070 (native GPU, no Docker)      │
│  └──────┬───────┘                                    │
│         │  API_BASE=http://jetson:7070/v1             │
│  ┌──────┴───────────────────────────────────────┐    │
│  │  Docker Compose                              │    │
│  │                                              │    │
│  │  ┌─────────┐  ┌─────────┐  ┌─────────────┐  │    │
│  │  │   web   │  │  mysql  │  │    redis    │  │    │
│  │  │  :8000  │  │  :3306  │  │    :6379    │  │    │
│  │  └────┬────┘  └─────────┘  └──────┬──────┘  │    │
│  │       │                           │          │    │
│  │       │    ┌──────────────┐  ┌────┴────────┐ │    │
│  │       │    │   searxng    │  │  dramatiq-  │ │    │
│  │       │    └──────────────┘  │   worker    │ │    │
│  │       │                      └──────┬──────┘ │    │
│  │       │    ┌──────────────┐  ┌──────┴──────┐ │    │
│  │       │    │   periodiq   │  │   byparr    │ │    │
│  │       │    └──────────────┘  └─────────────┘ │    │
│  │       │    ┌──────────────┐                  │    │
│  │       └───▶│   dozzle     │                  │    │
│  │            └──────────────┘                  │    │
│  └──────────────────────────────────────────────┘    │
└──────────────────────────────────────────────────────┘
```

> **Key difference:** On Jetson, `llamacpp` and `llamacpp-init` are replaced with busybox no-op stubs. The dramatiq-worker connects directly to the host llama.cpp via `API_BASE`.

---

## Local Development

For development, Docker Compose automatically loads `docker-compose.override.yml` which:

- Builds dev image targets (`web-dev`, `worker-dev`) with dev dependencies (pytest, black, etc.)
- Bind-mounts the source code for hot reload
- Enables `WEB_RELOAD=1` and `WEB_LOG_LEVEL=debug`
- Maps web to port **8765** (avoids conflicts with local services)
- Maps Dozzle to port **9999**

```bash
# Start development stack (auto-loads override)
docker compose up -d

# Run tests inside the worker container
docker compose exec dramatiq-worker pytest

# Access the dev web app
open http://localhost:8765

# Access Dozzle log viewer
open http://localhost:9999

# Access RedisInsight
open http://localhost:8001
```

---

## Troubleshooting

| Problem | Diagnosis | Solution |
|---------|-----------|----------|
| `llamacpp` fails to start | `docker logs <container>` | Check GPU: `docker run --rm --gpus all nvidia/cuda:12.0-base nvidia-smi` |
| Model download hangs/fails | `docker compose logs llamacpp-init` | Verify `HF_TOKEN` in `.env`; check repo/file names on HuggingFace |
| `db-migrate` fails | `docker compose logs db-migrate` | Check MySQL is healthy: `docker compose logs mysql` |
| Out of GPU memory | llamacpp logs show OOM | Reduce `LLAMACPP_CTX_SIZE`, `LLAMACPP_PARALLEL`, or use a smaller quantization (Q4 vs Q6) |
| Out of system memory | `docker stats` shows high usage | Reduce resource limits in `docker-compose.prod.yml` or add swap |
| Web returns 502 | `docker compose logs web` | Check web healthcheck; ensure MySQL and llamacpp are healthy |
| Web filesystem errors | `read_only: true` in prod | Write to `/tmp` or `/data` only; other paths are read-only |
| Jetson: llama.cpp unreachable | `docker compose exec web nslookup jetson` | Verify DNS resolves; try using the host IP directly in `API_BASE` |
| Jetson: connection refused | Port not listening on host | Ensure llama.cpp binds to `0.0.0.0` (not `127.0.0.1`) |
| Containers keep restarting | `docker compose logs <service>` | Check for crash loops; inspect healthcheck failures |
| Redis data loss | Redis not persisting | Verify `redis-data` volume exists: `docker volume ls` |
