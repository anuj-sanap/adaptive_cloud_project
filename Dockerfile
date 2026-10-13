# ==============================================================================
# Dockerfile - Production Container for Central Telemetry FastAPI Backend
# Optimized for Microsoft Azure App Service (Linux) & Azure Container Apps
# ==============================================================================

FROM python:3.11-slim AS runtime

# Set Python operational environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/src \
    PORT=8000 \
    TELEMETRY_DB_PATH=/app/data/telemetry.db

# Install system dependencies (curl needed for container healthcheck)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Create application directory
WORKDIR /app

# Create non-root user for security hardening
RUN groupadd -g 1001 appgroup && \
    useradd -u 1001 -g appgroup -s /bin/bash -m appuser

# Install Python requirements
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source code, machine learning model artifacts, and configurations
COPY src/ ./src/
COPY models/ ./models/
COPY config/ ./config/

# Create data directory for persistent SQLite database & set ownership
RUN mkdir -p /app/data && chown -R appuser:appgroup /app

# Switch to non-root user
USER appuser

# Declare data volume mount point for persistent storage
VOLUME ["/app/data"]

# Expose default HTTP port (Azure App Service / Container Apps maps this dynamically)
EXPOSE 8000

# Docker native healthcheck probe pointing to /health endpoint
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD curl -f http://127.0.0.1:${PORT:-8000}/health || exit 1

# Launch production server with proxy headers enabled for Azure reverse proxy/TLS termination
CMD ["sh", "-c", "uvicorn central_server.api:app --host 0.0.0.0 --port ${PORT:-8000} --proxy-headers --forwarded-allow-ips '*'"]
