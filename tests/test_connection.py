"""tests/test_connection.py - checks Module 1's DB connection works."""
import sys
from pathlib import Path
sys.path.append(str(Path(__file__).resolve().parent.parent))

from database.connection import db  # noqa: E402
from utils.logger import get_logger  # noqa: E402

logger = get_logger(__name__)


def test_database_connection() -> None:
    assert db.test_connection() is True, (
        "Database connection failed - check your .env file and confirm PostgreSQL is running."
    )


if __name__ == "__main__":
    logger.info("Running standalone database connection check...")
    success = db.test_connection()
    print("SUCCESS: Connected to PostgreSQL." if success else
          "FAILED: Could not connect to PostgreSQL. See logs/app.log for details.")
    sys.exit(0 if success else 1)
