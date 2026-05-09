FROM python:3.12-slim

# Build deps for C extensions (curl_cffi, pycparser, cffi)
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libffi-dev \
    libssl-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt uvicorn[standard]

COPY . .

# Data volume: DB + Garmin session cache
RUN mkdir -p /data
ENV DATABASE_URL=sqlite:////data/fitness.db
ENV GARMIN_SESSION_DIR=/data
ENV PYTHONPATH=/app

COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

EXPOSE 8000
ENTRYPOINT ["/entrypoint.sh"]
