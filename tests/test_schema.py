"""tests/test_schema.py - checks Module 2's schema creates correctly."""
import sys
from pathlib import Path
sys.path.append(str(Path(__file__).resolve().parent.parent))

from database.init_db import SchemaManager  # noqa: E402
from database.models import MODEL_LOAD_ORDER  # noqa: E402
from utils.logger import get_logger  # noqa: E402

logger = get_logger(__name__)


def test_schema_creates_all_tables() -> None:
    manager = SchemaManager()
    manager.create_all()
    assert manager.verify_schema() is True
    expected_tables = {model.__tablename__ for model in MODEL_LOAD_ORDER}
    actual_tables = set(manager.list_tables())
    assert expected_tables.issubset(actual_tables)


if __name__ == "__main__":
    logger.info("Running standalone schema creation check...")
    manager = SchemaManager()
    manager.create_all()
    ok = manager.verify_schema()
    if ok:
        print("SUCCESS: All tables created and verified.")
        print("Tables:", sorted(manager.list_tables()))
    else:
        print("FAILED: Schema verification failed. See logs/app.log")
    sys.exit(0 if ok else 1)
