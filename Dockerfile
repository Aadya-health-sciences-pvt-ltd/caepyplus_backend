# Use a minimal Python base image
FROM python:3.12-slim

# Set working directory in container
WORKDIR /app

# Ensure Python output is sent straight to terminal (useful for Docker logs)
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# Copy requirements first (to leverage Docker layer caching)
COPY requirements.txt .

# Install dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy all project files
COPY . .

RUN chmod +x /app/docker-entrypoint.sh

# Expose port (must match ECS task/container port)
EXPOSE 8000

ENTRYPOINT ["/app/docker-entrypoint.sh"]
# Default command
CMD ["uvicorn", "src.app.main:app", "--host", "0.0.0.0", "--port", "8000"]
