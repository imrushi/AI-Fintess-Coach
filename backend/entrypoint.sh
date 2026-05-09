#!/bin/sh
set -e

export PYTHONPATH=/app

echo "Running Alembic migrations..."
alembic upgrade head

echo "Starting backend..."
exec uvicorn main:app --host 0.0.0.0 --port 8000
