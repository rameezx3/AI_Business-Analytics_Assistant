"""
database/models/validation_log.py

WHY THIS TABLE EXISTS:
    Module 5 (Data Validation) runs a fixed suite of health checks
    against the database and needs somewhere to record the RESULT of
    every check, every time it's run - not just the current state, but
    a history of pass/warn/fail over time. Each call to
    DataValidator.run_all() writes one batch of rows sharing the same
    run_id, so "how has data health trended since we started importing
    new data" is a query away, not something you have to remember.

    This is deliberately a separate table from data_quality_log
    (Module 4): data_quality_log records ISSUES FOUND AND FIXED (or
    flagged) once; validation_log records CHECK RESULTS every run,
    including checks that pass - it's a health-check log, not an
    issue tracker.
"""

from sqlalchemy import Column, Integer, String, DateTime, func

from database.models.base import Base


class ValidationLog(Base):
    """One row per validation check, per run."""

    __tablename__ = "validation_log"

    id: int = Column(Integer, primary_key=True, autoincrement=True)
    run_id: str = Column(String(36), nullable=False, index=True)
    check_name: str = Column(String(100), nullable=False, index=True)
    category: str = Column(String(50), nullable=False, index=True)
    status: str = Column(String(10), nullable=False, index=True)  # PASS / WARN / FAIL
    expected: str = Column(String(300), nullable=True)
    actual: str = Column(String(300), nullable=True)
    message: str = Column(String(500), nullable=False)
    checked_at = Column(DateTime(timezone=True), server_default=func.now())

    def __repr__(self) -> str:
        return f"<ValidationLog(check={self.check_name}, status={self.status})>"
