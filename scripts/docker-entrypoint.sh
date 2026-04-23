#!/bin/sh
set -e

# Ensure data directory exists with correct permissions
mkdir -p /data

# Wait for MySQL to be ready (belt-and-suspenders with Docker healthcheck)
echo "Waiting for MySQL..."
MAX_RETRIES=30
RETRY=0
until python -c "
from sqlalchemy import create_engine, text
import os
e = create_engine(os.getenv('DATABASE_URL'))
with e.connect() as c:
    c.execute(text('SELECT 1'))
    print('MySQL is ready')
" 2>/dev/null; do
    RETRY=$((RETRY + 1))
    if [ "$RETRY" -ge "$MAX_RETRIES" ]; then
        echo "ERROR: MySQL not ready after $MAX_RETRIES attempts"
        exit 1
    fi
    echo "MySQL not ready yet (attempt $RETRY/$MAX_RETRIES)..."
    sleep 2
done

# Execute the passed command
exec "$@"
