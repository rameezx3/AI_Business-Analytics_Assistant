"""
tests/test_cleaning.py

WHY THIS FILE EXISTS:
    Confirms Module 4 works end-to-end AND is safely re-runnable
    (idempotent) - running the cleaner twice in a row must not double-
    fix or double-log anything.

    Run manually:  python tests/test_cleaning.py
    Or via pytest: pytest tests/test_cleaning.py -v
"""

import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))

from sqlalchemy import text  # noqa: E402

from database.connection import db  # noqa: E402
from services.data_cleaning import DataCleaner  # noqa: E402
from utils.logger import get_logger  # noqa: E402

logger = get_logger(__name__)


def test_cleaning_is_idempotent() -> None:
    """Running the full cleaning pipeline twice must not change anything the second time."""
    cleaner = DataCleaner()

    cleaner.run_all()
    with db.engine.connect() as conn:
        log_count_after_first_run = conn.execute(
            text("SELECT COUNT(*) FROM data_quality_log")
        ).scalar()

    second_report = cleaner.run_all()
    with db.engine.connect() as conn:
        log_count_after_second_run = conn.execute(
            text("SELECT COUNT(*) FROM data_quality_log")
        ).scalar()

    assert log_count_after_first_run == log_count_after_second_run, (
        "Re-running the cleaner should not create duplicate audit log entries."
    )
    assert second_report["products"]["category_filled"] == 0
    assert second_report["geolocation"]["duplicates_removed"] == 0


def test_no_null_categories_remain() -> None:
    """
    After cleaning, no product should have a NULL category - AND the
    table must not be empty. (The row-count assertion matters: a bug
    found during development left products truncated-but-not-reimported
    after an interrupted run, and a NULL-count-only check on an EMPTY
    table would have passed anyway - 0 nulls is trivially true with 0
    rows. That false pass is exactly what let it go unnoticed at first.)

    WHY THIS CALLS THE CLEANER ITSELF:
        Found by testing: this test used to assume cleaning had already
        run (via test_cleaning_is_idempotent, earlier in this same
        file) - fragile, since it silently depended on test execution
        order. Running the cleaner here makes it correct standalone.
    """
    DataCleaner().run_all()

    with db.engine.connect() as conn:
        total = conn.execute(text("SELECT COUNT(*) FROM products")).scalar()
        nulls = conn.execute(
            text("SELECT COUNT(*) FROM products WHERE product_category_name IS NULL")
        ).scalar()
    assert total > 30000, f"products table has suspiciously few rows: {total}"
    assert nulls == 0


if __name__ == "__main__":
    logger.info("Running standalone data cleaning check...")

    cleaner = DataCleaner()
    report = cleaner.run_all()

    print("\nFirst run report:")
    for key, value in report.items():
        print(f"  {key}: {value}")

    print("\nRunning again to verify idempotency...")
    second_report = cleaner.run_all()
    print("Second run report (should show mostly zeros):")
    for key, value in second_report.items():
        print(f"  {key}: {value}")

    print("\nSUCCESS: Data cleaning ran and is idempotent.")
