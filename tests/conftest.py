import os
import tempfile
from pathlib import Path

_TEST_DB_DIR = Path(tempfile.mkdtemp(prefix="news48-tests-"))
_TEST_DB_PATH = _TEST_DB_DIR / "test.db"

# Enforce a test-only database path for the entire pytest process.
os.environ["DATABASE_PATH"] = str(_TEST_DB_PATH)
