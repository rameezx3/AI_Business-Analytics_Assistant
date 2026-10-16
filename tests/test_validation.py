"""
tests/test_validation.py

WHY THIS FILE EXISTS:
    Confirms Module 5 works end-to-end: every check runs without error,
    results are persisted to validation_log under a shared run_id, and
    - given the current, already-cleaned dataset - there are zero FAIL
    results (only the 3 known, real WARN cases).

    Run manually:  python tests/test_validation.py
    Or via pytest: pytest tests/test_validation.py -v
"""

import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))

from sqlalchemy import text  # noqa: E402

from database.connection import db  # noqa: E402
from services.data_cleaning import DataCleaner  # noqa: E402
from services.data_validation import DataValidator  # noqa: E402
from utils.logger import get_logger  # noqa: E402

logger = get_logger(__name__)


def test_validation_has_no_failures() -> None:
    """
    On the cleaned dataset, every check should PASS or WARN - never FAIL.

    WHY THIS RUNS THE CLEANER FIRST:
        Found by testing: running the full suite together, this test
        failed when it happened to run right after test_import.py's own
        test - which legitimately resets the database to its raw,
        uncleaned state as part of ITS test. This test was silently
        depending on cleaning already having been run by something
        else earlier, which made it fragile to test execution order.
        Running the cleaner here makes this test self-contained and
        correct regardless of what ran before it.
    """
    DataCleaner().run_all()

    validator = DataValidator()
    validator.run_all()
    summary = validator.summary()
    assert summary["failed"] == 0, f"{summary['failed']} validation checks failed unexpectedly."
    assert summary["total"] == 30


def test_validation_results_are_persisted() -> None:
    """Each run must write its results to validation_log under one shared run_id."""
    DataCleaner().run_all()
    validator = DataValidator()
    validator.run_all()

    with db.engine.connect() as conn:
        run_ids = conn.execute(
            text("SELECT DISTINCT run_id FROM validation_log ORDER BY run_id DESC LIMIT 1")
        ).fetchall()
        assert len(run_ids) == 1
        latest_run_id = run_ids[0][0]

        count = conn.execute(
            text("SELECT COUNT(*) FROM validation_log WHERE run_id = :rid"),
            {"rid": latest_run_id},
        ).scalar()
        assert count == 30


if __name__ == "__main__":
    logger.info("Running standalone data validation check...")

    DataCleaner().run_all()
    validator = DataValidator()
    results = validator.run_all()
    summary = validator.summary()

    for r in results:
        print(f"  [{r.status}] {r.check_name}: {r.message}")

    print(
        f"\nSummary: {summary['passed']} passed, {summary['warned']} warnings, "
        f"{summary['failed']} failed (of {summary['total']} checks)"
    )
    sys.exit(0 if summary["failed"] == 0 else 1)
