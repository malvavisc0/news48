#!/bin/sh
set -e

# Ensure data directory exists with correct permissions
mkdir -p /data

# Remove stale orchestrator PID file that may persist across container
# restarts on Docker volumes.  PID 1 is always alive in a container, so
# a leftover file containing PID=1 would prevent the orchestrator from
# starting ("daemon already running").
rm -f /data/orchestrator.pid

# Initialize SQLite database if it doesn't exist
DB_PATH="/data/news48.db"
if [ ! -f "$DB_PATH" ]; then
    echo "Initializing database at $DB_PATH"
    python -c "
from database.connection import init_database
from config import Database
init_database(Database.path)
print('Database initialized successfully')
" 2>/dev/null || echo "Note: Database initialization skipped (will happen on first access)"
fi

# Execute the passed command
exec "$@"
