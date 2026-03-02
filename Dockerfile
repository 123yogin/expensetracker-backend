# ============================================
# Backend Dockerfile - Production-Ready
# ============================================
# Multi-stage build for minimal image size
# ============================================

FROM python:3.12-slim AS base

# Security: Run as non-root user
RUN groupadd -r appuser && useradd -r -g appuser appuser

# Install system dependencies for psycopg2
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# ---- Dependencies stage ----
FROM base AS dependencies

COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt && \
    pip install --no-cache-dir gunicorn flask-limiter

# ---- Production stage ----
FROM dependencies AS production

# Copy application code
COPY . .

# Create upload directory
RUN mkdir -p uploads/receipts && chown -R appuser:appuser /app

# Switch to non-root user
USER appuser

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:5001/health')" || exit 1

# Expose port
EXPOSE 5001

# Production WSGI server
CMD ["gunicorn", \
     "--config", "gunicorn.conf.py", \
     "app:app"]
