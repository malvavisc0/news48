# =============================================================================
# Stage 1: web-builder — Install runtime dependencies for web
# =============================================================================
FROM python:3.12-slim AS web-builder

WORKDIR /app

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Copy dependency files for layer caching
COPY pyproject.toml uv.lock ./

# Install ALL dependencies — web app imports agents/tools which needs markdownify,
# llama_index, and other cli extras. Clean web/worker split not feasible.
RUN uv sync --frozen --no-dev --extra all --no-install-project

# =============================================================================
# Stage 2: worker-builder — Install ALL project dependencies (no dev)
# =============================================================================
FROM python:3.12-slim AS worker-builder

WORKDIR /app
ENV DEBIAN_FRONTEND=noninteractive

# Install build tools (needed for Rust-based packages like html-to-markdown)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential curl && \
    curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y && \
    rm -rf /var/lib/apt/lists/*
ENV PATH="/root/.cargo/bin:$PATH"

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Copy dependency files for layer caching
COPY pyproject.toml uv.lock ./

# Install all project dependencies (excludes dev group)
RUN uv sync --frozen --no-dev --extra all --no-install-project

# =============================================================================
# Stage 2b: dev-builder — Install ALL dependencies INCLUDING dev
# =============================================================================
FROM python:3.12-slim AS dev-builder

WORKDIR /app
ENV DEBIAN_FRONTEND=noninteractive

# Install build tools (needed for Rust-based packages like html-to-markdown)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential curl && \
    curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y && \
    rm -rf /var/lib/apt/lists/*
ENV PATH="/root/.cargo/bin:$PATH"

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Copy dependency files for layer caching
COPY pyproject.toml uv.lock ./

# Install all dependencies including dev group (black, isort, pytest)
RUN uv sync --frozen --extra all --no-install-project

# =============================================================================
# Stage 3: web — Production web image (minimal)
# =============================================================================
FROM python:3.12-slim AS web

WORKDIR /app

# Create non-root user
RUN groupadd -g 1000 news48 && \
    useradd -u 1000 -g news48 -m news48

# Copy installed packages from builder
COPY --from=web-builder /app/.venv /app/.venv

# Copy the entire news48 package (includes core + web subpackages)
COPY news48/ news48/

# Copy Alembic (entrypoint runs migrations)
COPY alembic/ alembic/
COPY alembic.ini ./

# Copy and make entrypoint executable
COPY scripts/docker-entrypoint.sh /app/scripts/docker-entrypoint.sh
RUN chmod +x /app/scripts/docker-entrypoint.sh

# Set PATH to include venv bin
ENV PATH="/app/.venv/bin:$PATH"

# Web server defaults (overridable at runtime)
ENV WEB_HOST=0.0.0.0
ENV WEB_PORT=8000

# Ensure data directory exists
RUN mkdir -p /data && chown news48:news48 /data

# Switch to non-root user
USER news48

# Expose port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --retries=3 \
    CMD python -c "import os, urllib.request; urllib.request.urlopen(f'http://localhost:{os.environ[\"WEB_PORT\"]}/health')" || exit 1

# Default command (overridden by compose)
CMD ["sh", "-c", "uvicorn news48.web.app:app --host ${WEB_HOST} --port ${WEB_PORT}"]

# =============================================================================
# Stage 4: worker — Production worker image (full stack)
# =============================================================================
FROM python:3.12-slim AS worker

WORKDIR /app

# Create non-root user
RUN groupadd -g 1000 news48 && \
    useradd -u 1000 -g news48 -m news48

# Copy installed packages from builder
COPY --from=worker-builder /app/.venv /app/.venv

# Copy all application source code
COPY . .

# Install the project itself (dependencies already in .venv from builder)
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv
RUN uv sync --frozen --no-dev --extra all

# Ensure entrypoint is executable
RUN chmod +x /app/scripts/docker-entrypoint.sh

# Set PATH to include venv bin
ENV PATH="/app/.venv/bin:$PATH"

# Ensure data directory exists
RUN mkdir -p /data && chown news48:news48 /data

# Switch to non-root user
USER news48

# Default command (overridden by compose)
CMD ["dramatiq", "news48.core.agents.actors", "--processes", "1", "--threads", "8"]

# =============================================================================
# Stage 5: web-dev — Development web image
# =============================================================================
FROM web AS web-dev

# Copy venv with ALL deps including dev (black, isort, pytest)
COPY --from=dev-builder /app/.venv /app/.venv

# Re-set PATH after copy
ENV PATH="/app/.venv/bin:$PATH"

# =============================================================================
# Stage 6: worker-dev — Development worker image
# =============================================================================
FROM worker AS worker-dev

# Copy venv with ALL deps including dev (black, isort, pytest)
COPY --from=dev-builder /app/.venv /app/.venv

# Re-set PATH after copy
ENV PATH="/app/.venv/bin:$PATH"
