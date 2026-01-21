# CHAPTR - Personal Finance Projection System
# Multi-stage Dockerfile for production deployment

# ============================================================================
# Stage 1: Build stage
# ============================================================================
FROM python:3.13-slim AS builder

WORKDIR /app

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libffi-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install dependencies
COPY requirements.txt .

# Create virtual environment and install dependencies
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Install production dependencies only (exclude dev/test packages)
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir \
    fastapi>=0.104.0 \
    "uvicorn[standard]>=0.24.0" \
    motor>=3.3.0 \
    pymongo>=4.6.0 \
    pydantic>=2.5.0 \
    pydantic-settings>=2.1.0 \
    python-dotenv>=1.0.0 \
    "python-jose[cryptography]>=3.3.0" \
    "passlib[bcrypt]>=1.7.4" \
    "bcrypt>=4.0.0,<5.0.0" \
    python-multipart>=0.0.6 \
    apscheduler>=3.10.4 \
    python-dateutil>=2.8.2

# ============================================================================
# Stage 2: Production stage
# ============================================================================
FROM python:3.13-slim AS production

WORKDIR /app

# Create non-root user for security
RUN groupadd -r chaptr && useradd -r -g chaptr chaptr

# Copy virtual environment from builder
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Copy application code
COPY api/ ./api/
COPY core/ ./core/
COPY static/ ./static/

# Set ownership to non-root user
RUN chown -R chaptr:chaptr /app

# Switch to non-root user
USER chaptr

# Environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    ENVIRONMENT=production

# Expose port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/api/health')" || exit 1

# Run the application
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
