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

# Expose port
EXPOSE 6555
# Default command
CMD ["uvicorn", "src.app.main:app", "--host", "0.0.0.0", "--port", "6555"]