# ─────────────────────────────────────────────────────────
# TPRM AI Assessment Platform — Production Dockerfile
# ─────────────────────────────────────────────────────────

FROM python:3.11-slim

# System deps needed for psycopg2-binary and PyMuPDF
RUN apt-get update && apt-get install -y --no-install-recommends \
        libpq-dev \
        libgl1 \
        libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies first (layer-cached until requirements change)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Create required runtime directories
RUN mkdir -p data assessments config

# Non-root user for security
RUN useradd -m -u 1000 tprm && chown -R tprm:tprm /app
USER tprm

EXPOSE 8085

# Uvicorn with 2 workers — increase workers for higher traffic
CMD ["uvicorn", "webapp.main:app", \
     "--host", "0.0.0.0", \
     "--port", "8085", \
     "--workers", "2", \
     "--log-level", "info", \
     "--access-log"]
