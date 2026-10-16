"""tests/test_import.py - checks Module 3's CSV import works end-to-end."""
import sys
from pathlib import Path
sys.path.append(str(Path(__file__).resolve().parent.parent))

from database.import_csv import CSVImporter  # noqa: E402
from database.init_db import SchemaManager  # noqa: E402
from utils.logger import get_logger  # noqa: E402

logger = get_logger(__name__)

EXPECTED_MINIMUM_ROWS = {
    "category_translation": 70, "customers": 99000, "geolocation": 900000,
    "sellers": 3000, "products": 32000, "orders": 99000,
    "order_items": 112000, "order_payments": 103000, "order_reviews": 99000,
}


def test_import_all_tables() -> None:
    manager = SchemaManager()
    manager.create_all()
    importer = CSVImporter()
    results = importer.import_all(truncate=True)
    assert importer.validate_row_counts(results) is True
    for table_name, minimum in EXPECTED_MINIMUM_ROWS.items():
        assert results.get(table_name, 0) >= minimum


if __name__ == "__main__":
    logger.info("Running standalone CSV import check...")
    manager = SchemaManager()
    manager.create_all()
    importer = CSVImporter()
    results = importer.import_all(truncate=True)
    print("\nImport summary:")
    for table, count in results.items():
        print(f"  {table}: {count} rows")
    ok = importer.validate_row_counts(results)
    print("\nSUCCESS: All tables imported and validated." if ok else
          "\nFAILED: Row count validation failed. See logs/app.log")
    sys.exit(0 if ok else 1)
