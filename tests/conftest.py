import atexit
import os
import shutil
import tempfile
from pathlib import Path

_TEST_DB_DIR = Path(tempfile.mkdtemp(prefix="news48-tests-"))
_TEST_DB_PATH = _TEST_DB_DIR / "test.db"

# Enforce a test-only database path for the entire pytest process.
os.environ["DATABASE_PATH"] = str(_TEST_DB_PATH)


def _cleanup_test_db():
    """Remove the test database directory after tests complete."""
    if _TEST_DB_DIR.exists():
        shutil.rmtree(_TEST_DB_DIR, ignore_errors=True)


atexit.register(_cleanup_test_db)
