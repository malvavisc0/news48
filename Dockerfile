# =============================================================================
# Stage 1: web-builder — Install web-only dependencies
# =============================================================================
FROM python:3.12-slim AS web-builder

WORKDIR /app

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Copy dependency files for layer caching
COPY pyproject.toml uv.lock ./

# Install only the web dependency group
RUN uv sync --frozen --only-group web --no-dev --no-install-project

# =============================================================================
# Stage 2: orch-builder — Install ALL project dependencies (no dev)
# =============================================================================
FROM python:3.12-slim AS orch-builder

WORKDIR /app

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Copy dependency files for layer caching
COPY pyproject.toml uv.lock ./

# Install all project dependencies (excludes dev group)
RUN uv sync --frozen --no-dev --no-install-project

# =============================================================================
# Stage 2b: dev-builder — Install ALL dependencies INCLUDING dev
# =============================================================================
FROM python:3.12-slim AS dev-builder

WORKDIR /app

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Copy dependency files for layer caching
COPY pyproject.toml uv.lock ./

# Install all dependencies including dev group (black, isort, pytest)
RUN uv sync --frozen --no-install-project

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

# Copy only web-relevant source code
COPY web/ web/
COPY database/ database/
COPY config.py ./

# Create a minimal helpers/__init__.py that doesn't import heavy modules
RUN mkdir -p helpers && \
    echo '"""Web-only helpers."""' > helpers/__init__.py
COPY helpers/seo.py helpers/

# Copy and make entrypoint executable
COPY docker-entrypoint.sh /app/docker-entrypoint.sh
RUN chmod +x /app/docker-entrypoint.sh

# Set PATH to include venv bin
ENV PATH="/app/.venv/bin:$PATH"

# Ensure data directory exists
RUN mkdir -p /data && chown news48:news48 /data

# Switch to non-root user
USER news48

# Expose port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/')" || exit 1

# Default command (overridden by compose)
CMD ["uvicorn", "web.app:app", "--host", "0.0.0.0", "--port", "8000"]

# =============================================================================
# Stage 4: orchestrator — Production orchestrator image (full stack)
# =============================================================================
FROM python:3.12-slim AS orchestrator

WORKDIR /app

# Create non-root user
RUN groupadd -g 1000 news48 && \
    useradd -u 1000 -g news48 -m news48

# Copy installed packages from builder
COPY --from=orch-builder /app/.venv /app/.venv

# Copy all application source code
COPY . .

# Install the project itself (dependencies already in .venv from builder)
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv
RUN uv sync --frozen --no-dev

# Ensure entrypoint is executable
RUN chmod +x /app/docker-entrypoint.sh

# Set PATH to include venv bin
ENV PATH="/app/.venv/bin:$PATH"

# Set orchestrator command prefix for Docker
ENV ORCHESTRATOR_CMD_PREFIX=news48

# Ensure data directory exists
RUN mkdir -p /data && chown news48:news48 /data

# Switch to non-root user
USER news48

# Default command (overridden by compose)
CMD ["news48", "agents", "start"]

# =============================================================================
# Stage 5: web-dev — Development web image
# =============================================================================
FROM web AS web-dev

# Copy venv with ALL deps including dev (black, isort, pytest)
COPY --from=dev-builder /app/.venv /app/.venv

# Re-set PATH after copy
ENV PATH="/app/.venv/bin:$PATH"

# =============================================================================
# Stage 6: orchestrator-dev — Development orchestrator image
# =============================================================================
FROM orchestrator AS orchestrator-dev

# Copy venv with ALL deps including dev (black, isort, pytest)
COPY --from=dev-builder /app/.venv /app/.venv

# Re-set PATH after copy
ENV PATH="/app/.venv/bin:$PATH"
