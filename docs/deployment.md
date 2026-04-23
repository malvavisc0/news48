# Deployment Guide

Two deployment modes:

| Mode | Use case | llama.cpp | Compose files |
|------|----------|-----------|---------------|
| **Standard** | x86 server with GPU | Docker container | `docker-compose.yml` + `docker-compose.prod.yml` |
| **Jetson** | ARM64 with host llama.cpp | Host process | `docker-compose.yml` + `docker-compose.jetson.yml` |

---

## Table of Contents

- [Compose File Reference](#compose-file-reference)
- [Standard Deployment (x86 Server)](#standard-deployment-x86-server)
- [Jetson / ARM64 Deployment](#jetson--arm64-deployment)
- [Environment Variables](#environment-variables)
- [Operations](#operations)
- [Architecture](#architecture)
- [Troubleshooting](#troubleshooting)

---

## Compose File Reference

| File | Purpose | Auto-loaded? |
|------|---------|--------------|
| [`docker-compose.yml`](../docker-compose.yml) | Base service definitions | Yes |
| [`docker-compose.override.yml`](../docker-compose.override.yml) | Dev overrides (hot reload, bind mounts) | Yes (dev only) |
| [`docker-compose.prod.yml`](../docker-compose.prod.yml) | Production overrides (pre-built images, resource limits, security hardening) | No — pass with `-f` |
| [`docker-compose.jetson.yml`](../docker-compose.jetson.yml) | Disables Docker llamacpp, uses host llama.cpp | No — pass with `-f` |

> **Tip:** Set a shell alias to avoid repeating the long command:
> ```bash
> alias dc='docker compose -f docker-compose.yml -f docker-compose.prod.yml'
> ```

---

## Standard Deployment (x86 Server)

Uses Docker-managed llama.cpp with GPU passthrough.

### Prerequisites

- [ ] Docker Engine 24+ and Docker Compose v2
- [ ] NVIDIA drivers + [nvidia-container-toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/install-guide.html)
- [ ] HuggingFace token (if using gated/private models)

### 1. Install Docker

```bash
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER
# Log out and back in, then verify:
docker run --rm --gpus all nvidia/cuda:12.0-base nvidia-smi
```

### 2. Copy Files to Server

```
news48/
├── docker-compose.yml
├── docker-compose.prod.yml
├── .env                        # create from .env.example
├── scripts/
│   ├── docker-entrypoint.sh
│   ├── download-model.sh       # mounted by llamacpp-init
│   └── llamacpp-entrypoint.sh  # mounted by llamacpp
└── searxng/
    └── settings.yml
```

```bash
mkdir -p ~/news48/scripts ~/news48/searxng
scp docker-compose.yml docker-compose.prod.yml user@server:~/news48/
scp scripts/*.sh user@server:~/news48/scripts/
scp searxng/settings.yml user@server:~/news48/searxng/
```

### 3. Configure Environment

```bash
cd ~/news48
cp .env.example .env
# Edit .env — see Environment Variables section below
```

### 4. Launch

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d
```

First run downloads the GGUF model (may take several minutes depending on model size).

### 5. Verify

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml ps
curl http://localhost:8000/health    # web
curl http://localhost:8080/health    # llamacpp
```

---

## Jetson / ARM64 Deployment

Uses a **host llama.cpp** instance instead of the Docker container. The [`docker-compose.jetson.yml`](../docker-compose.jetson.yml) override disables `llamacpp` and `llamacpp-init` via `profiles: ["disabled"]`.

### Prerequisites

- [ ] Docker Engine 24+ and Docker Compose v2
- [ ] llama.cpp running on the host (e.g., `http://jetson.tago.lan:7070/v1`)
- [ ] HuggingFace token (if using gated/private models)

### 1. Configure Environment

```bash
cd ~/news48
cp .env.example .env
```

Set these in `.env`:

```bash
API_BASE=http://jetson.tago.lan:7070/v1
API_KEY=
MODEL=granite-4.1-8b
```

### 2. Launch

```bash
docker compose -f docker-compose.yml -f docker-compose.jetson.yml up -d
```

### 3. Verify

```bash
# Check services
docker compose -f docker-compose.yml -f docker-compose.jetson.yml ps

# Verify llama.cpp is reachable from inside Docker
docker compose exec web python -c \
  "import urllib.request; print(urllib.request.urlopen('http://jetson.tago.lan:7070/v1/models').read())"
```

### Combining Jetson + Production Overrides

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml -f docker-compose.jetson.yml up -d
```

---

## Environment Variables

### Required

| Variable | Description | Example |
|----------|-------------|---------|
| `MODEL` | LLM model name for agents | `granite-4.1-8b` |
| `API_BASE` | LLM API base URL | `http://llamacpp:8080/v1` or `http://jetson.tago.lan:7070/v1` |
| `API_KEY` | LLM API key (empty for local llama.cpp) | `sk-...` or leave empty |
| `MYSQL_ROOT_PASSWORD` | MySQL root password | `openssl rand -hex 16` |
| `MYSQL_PASSWORD` | MySQL app user password | `openssl rand -hex 16` |
| `SEARXNG_SECRET` | SearXNG secret key | `python3 -c "import secrets; print(secrets.token_hex(32))"` |

### LLM Model (Docker llama.cpp only)

Only needed when using the Docker-managed llamacpp container (not Jetson).

| Variable | Default | Description |
|----------|---------|-------------|
| `LLAMACPP_MODEL_REPO` | `mradermacher/claude-oss-i1-GGUF` | HuggingFace repo |
| `LLAMACPP_MODEL_FILE` | `claude-oss.i1-Q6_K.gguf` | GGUF filename |
| `LLAMACPP_CTX_SIZE` | `131072` | Context window size |
| `LLAMACPP_N_GPU_LAYERS` | `999` | GPU layers (999 = all) |
| `LLAMACPP_PARALLEL` | `4` | Parallel requests |
| `HF_TOKEN` | — | HuggingFace token for gated models |

### Optional (Email Alerts)

| Variable | Description |
|----------|-------------|
| `SMTP_HOST` | SMTP server |
| `SMTP_PORT` | SMTP port (default: 587) |
| `SMTP_USER` | SMTP username |
| `SMTP_PASS` | SMTP password |
| `SMTP_FROM` | Sender address |
| `MONITOR_EMAIL_TO` | Alert recipient |

---

## Operations

### Update to Latest Images

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml pull
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d
```

### View Logs

```bash
# All services
docker compose -f docker-compose.yml -f docker-compose.prod.yml logs -f

# Single service
docker compose -f docker-compose.yml -f docker-compose.prod.yml logs -f dramatiq-worker
```

### Shell into a Container

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml exec dramatiq-worker bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml exec llamacpp bash
```

### Restart a Service

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml restart web
```

### Stop Everything

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml down
```

---

## Architecture

### Standard (Docker llama.cpp)

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

### Jetson (Host llama.cpp)

```
┌─────────────────────────────────────────────┐
│  Host: Jetson Orin NX                       │
│                                             │
│  ┌──────────────┐                           │
│  │  llama.cpp   │ :7070 (native, GPU)       │
│  └──────┬───────┘                           │
│         │ API_BASE=http://jetson.tago.lan   │
│         │           :7070/v1                │
│  ┌──────┴──────────────────────────────┐    │
│  │  Docker Compose                     │    │
│  │  ┌─────────┐  ┌─────┐  ┌────────┐  │    │
│  │  │   web   │  │mysql│  │ redis  │  │    │
│  │  └────┬────┘  └─────┘  └───┬────┘  │    │
│  │       │                     │       │    │
│  │       ▼                     ▼       │    │
│  │  ┌──────────────┐  ┌─────────────┐  │    │
│  │  │   searxng    │  │ dramatiq-   │  │    │
│  │  └──────────────┘  │  worker     │  │    │
│  │                    └─────────────┘  │    │
│  └─────────────────────────────────────┘    │
└─────────────────────────────────────────────┘
```

---

## Troubleshooting

| Problem | Solution |
|---------|----------|
| `llamacpp` fails to start | Check GPU: `docker run --rm --gpus all nvidia/cuda:12.0-base nvidia-smi` |
| Model download fails | Check `HF_TOKEN` in `.env`; verify repo/file names |
| `db-migrate` fails | Check MySQL: `docker compose -f docker-compose.yml -f docker-compose.prod.yml logs mysql` |
| Out of memory | Reduce `LLAMACPP_CTX_SIZE` or `LLAMACPP_PARALLEL` in `.env` |
| Web returns 502 | Check web logs: `docker compose logs web` |
| Jetson: llama.cpp unreachable | Verify DNS resolves: `docker compose exec web nslookup jetson.tago.lan` |
| Jetson: connection refused | Ensure llama.cpp binds to `0.0.0.0` (not just `127.0.0.1`) |
