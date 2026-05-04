#!/bin/sh
set -e
cd /app

# Wait until MariaDB accepts connections (covers rare races after depends_on healthy)
python -c "
import os, time, pymysql
host = os.environ.get('DB_HOST', 'db')
port = int(os.environ.get('DB_PORT', '3306'))
user = os.environ.get('DB_USER', '')
password = os.environ.get('DB_PASSWORD', '')
database = os.environ.get('DB_NAME', '')
for i in range(90):
    try:
        pymysql.connect(host=host, port=port, user=user, password=password, database=database, connect_timeout=5)
        print('Database accepts connections.')
        break
    except Exception as e:
        print(f'Waiting for database ({i + 1}/90): {e}')
        time.sleep(2)
else:
    raise SystemExit('Database did not become ready in time.')
"

alembic_ok=0
for attempt in 1 2 3 4 5; do
  if alembic upgrade head; then
    alembic_ok=1
    break
  fi
  echo "alembic failed (attempt ${attempt}/5), retrying in 5s..."
  sleep 5
done
if [ "$alembic_ok" != "1" ]; then
  echo "alembic upgrade failed after 5 attempts."
  exit 1
fi

if [ "${SEED_ON_START}" = "true" ]; then
  python -m app.seed
fi

exec uvicorn app.main:app --host 0.0.0.0 --port 8000
