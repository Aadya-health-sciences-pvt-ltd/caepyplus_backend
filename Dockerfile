# Use a minimal Python base image
FROM python:3.12-slim

# Set working directory in container
WORKDIR /app

# Ensure Python output is sent straight to terminal (useful for Docker logs)
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PATH="/app/.venv/bin:$PATH"

# Install uv binary (no pip)
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Copy project metadata first (layer caching)
COPY pyproject.toml uv.lock README.md ./

# Install runtime deps only (skip local package — needs src/ + static CSV)
RUN uv sync --frozen --no-dev --no-install-project

# Copy all project files
COPY . .

# Re-sync so the local package is installed into the venv (first sync is deps-only)
RUN uv sync --frozen --no-dev

RUN sed -i 's/\r$//' /app/docker-entrypoint.sh && chmod +x /app/docker-entrypoint.sh

# Expose port (must match ECS task/container port — 8000)
EXPOSE 8000

ENTRYPOINT ["/app/docker-entrypoint.sh"]
# Default command (ECS / production)
CMD ["uvicorn", "src.app.main:app", "--host", "0.0.0.0", "--port", "8000"]
