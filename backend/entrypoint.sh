#!/bin/sh
set -e
cd /app
alembic upgrade head
if [ "${SEED_ON_START}" = "true" ]; then
  python -m app.seed
fi
exec uvicorn app.main:app --host 0.0.0.0 --port 8000
