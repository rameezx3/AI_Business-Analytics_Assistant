"""
database/models/data_quality_log.py

WHY THIS TABLE EXISTS:
    Module 4 (Automatic Data Cleaning) never silently fixes or drops
    data. Every issue it finds - whether it goes on to FIX it or only
    FLAG it - gets one row here: what table, what kind of issue, which
    record, and exactly what action (if any) was taken. A business user
    or teammate can audit the entire cleaning process from this table
    alone, instead of trusting a "data was cleaned" claim on faith.

WHY THE UNIQUE CONSTRAINT:
    Cleaning is meant to be safely re-runnable (e.g. after a future
    CSV refresh). Without a uniqueness guard, running the cleaner twice
    would log the same still-unfixed issue (like the 8 orders with a
    missing delivery date) a second time. The constraint + ON CONFLICT
    DO NOTHING in services/data_cleaning.py makes re-runs idempotent.
"""

from sqlalchemy import Column, Integer, String, DateTime, UniqueConstraint, func

from database.models.base import Base


class DataQualityLog(Base):
    """One row per data quality issue detected during cleaning."""

    __tablename__ = "data_quality_log"

    id: int = Column(Integer, primary_key=True, autoincrement=True)
    table_name: str = Column(String(50), nullable=False, index=True)
    issue_type: str = Column(String(50), nullable=False, index=True)
    record_identifier: str = Column(String(100), nullable=False)
    description: str = Column(String(500), nullable=False)
    action_taken: str = Column(String(500), nullable=False)
    detected_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        UniqueConstraint(
            "table_name", "issue_type", "record_identifier",
            name="uq_data_quality_log_issue",
        ),
    )

    def __repr__(self) -> str:
        return f"<DataQualityLog(table={self.table_name}, issue={self.issue_type})>"
