# Production Deployment Checklist

Deploy news48 to a fresh server using pre-built images from GHCR.

## Prerequisites

- [ ] Docker Engine 24+ and Docker Compose v2
- [ ] NVIDIA drivers + [nvidia-container-toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/install-guide.html) (for llamacpp GPU)
- [ ] A HuggingFace token (if using gated/private models)

## 1. Server Setup

```bash
# Install Docker (Ubuntu/Debian)
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER

# Verify GPU access
docker run --rm --gpus all nvidia/cuda:12.0-base nvidia-smi
```

## 2. Copy Required Files

Create a project directory on the server with these files:

```
news48/
├── docker-compose.yml          # base compose file
├── docker-compose.prod.yml     # production overrides
├── .env                        # secrets (see below)
├── scripts/
│   ├── docker-entrypoint.sh    # mounted by db-migrate (via base image)
│   ├── download-model.sh       # mounted by llamacpp-init
│   └── llamacpp-entrypoint.sh  # mounted by llamacpp
└── searxng/
    └── settings.yml            # mounted by searxng
```

```bash
mkdir -p news48/scripts news48/searxng
# Copy files from your dev machine or repo
scp docker-compose.yml docker-compose.prod.yml user@server:~/news48/
scp scripts/*.sh user@server:~/news48/scripts/
scp searxng/settings.yml user@server:~/news48/searxng/
```

## 3. Create `.env` File

Copy `.env.example` and fill in real values:

```bash
cp .env.example .env
```

**Required variables:**

| Variable | Description | Example |
|----------|-------------|---------|
| `MODEL` | LLM model name for agents | `granite-4.1-8b` |
| `API_BASE` | LLM API base URL | `http://llamacpp:8080/v1` |
| `API_KEY` | LLM API key (can be empty for local) | `sk-...` or leave empty |
| `MYSQL_ROOT_PASSWORD` | MySQL root password | Generate with `openssl rand -hex 16` |
| `MYSQL_PASSWORD` | MySQL app user password | Generate with `openssl rand -hex 16` |
| `SEARXNG_SECRET` | SearXNG secret key | Generate with `python3 -c "import secrets; print(secrets.token_hex(32))"` |
| `HF_TOKEN` | HuggingFace token (if gated model) | `hf_...` |

**LLM model config:**

| Variable | Default | Description |
|----------|---------|-------------|
| `LLAMACPP_MODEL_REPO` | `mradermacher/claude-oss-i1-GGUF` | HuggingFace repo |
| `LLAMACPP_MODEL_FILE` | `claude-oss.i1-Q6_K.gguf` | GGUF filename |
| `LLAMACPP_CTX_SIZE` | `131072` | Context window size |
| `LLAMACPP_N_GPU_LAYERS` | `999` | GPU layers (999 = all) |
| `LLAMACPP_PARALLEL` | `4` | Parallel requests |

**Optional (email alerts):**

| Variable | Description |
|----------|-------------|
| `SMTP_HOST` | SMTP server |
| `SMTP_PORT` | SMTP port (default: 587) |
| `SMTP_USER` | SMTP username |
| `SMTP_PASS` | SMTP password |
| `SMTP_FROM` | Sender address |
| `MONITOR_EMAIL_TO` | Alert recipient |

## 4. Launch

```bash
cd ~/news48
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d
```

## 5. Verify

```bash
# Check all services are running
docker compose -f docker-compose.yml -f docker-compose.prod.yml ps

# Check logs
docker compose -f docker-compose.yml -f docker-compose.prod.yml logs -f

# Verify web health
curl http://localhost:8000/health

# Verify llamacpp health
curl http://localhost:8080/health

# Verify searxng health
curl http://localhost:8080/healthz
```

## 6. Useful Commands

```bash
# View logs for a specific service
docker compose -f docker-compose.yml -f docker-compose.prod.yml logs -f dramatiq-worker

# Restart a single service
docker compose -f docker-compose.yml -f docker-compose.prod.yml restart web

# Pull latest images and restart
docker compose -f docker-compose.yml -f docker-compose.prod.yml pull
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d

# Shell into llamacpp container
docker compose -f docker-compose.yml -f docker-compose.prod.yml exec llamacpp bash

# Shell into worker container
docker compose -f docker-compose.yml -f docker-compose.prod.yml exec dramatiq-worker bash

# Check model files
docker compose -f docker-compose.yml -f docker-compose.prod.yml exec llamacpp ls -lh /models
```

## Architecture Overview

```
┌─────────────┐     ┌──────────┐     ┌──────────┐
│   web:8000  │────▶│  mysql   │     │  redis   │
└──────┬──────┘     └──────────┘     └────┬─────┘
       │                                   │
       ▼                                   ▼
┌──────────────┐    ┌──────────────┐  ┌──────────────────┐
│   llamacpp   │    │   searxng    │  │ dramatiq-worker  │
│  :8080 (GPU) │    │   :8080      │  │                  │
└──────────────┘    └──────────────┘  └──────────────────┘
                                            │
                    ┌──────────┐            │
                    │  byparr  │◀───────────┘
                    └──────────┘
```

## Troubleshooting

| Problem | Solution |
|---------|----------|
| `llamacpp` fails to start | Check GPU access: `docker run --rm --gpus all nvidia/cuda:12.0-base nvidia-smi` |
| Model download fails | Check `HF_TOKEN` in `.env`; verify repo/file names |
| `db-migrate` fails | Check MySQL is healthy: `docker compose logs mysql` |
| Out of memory | Reduce `LLAMACPP_CTX_SIZE` or `LLAMACPP_PARALLEL` in `.env` |
| Web returns 502 | Check web logs: `docker compose logs web` |
