"""
services/data_validation.py

WHY THIS FILE EXISTS:
    Module 5: runs a fixed suite of automated health checks against the
    database and records a timestamped PASS/WARN/FAIL result for each
    one, every time it's run. This is distinct from Module 4 (Automatic
    Data Cleaning): cleaning fixes or flags issues ONCE; validation is a
    repeatable health check you'd run after every future data refresh
    to catch regressions - most checks here are expected to PASS today,
    but exist so they'd catch a problem automatically if it appeared.

    Every threshold and expected value below was derived by querying
    the live database first (see each method's docstring).

WHERE THIS FILE BELONGS:
    AI_Business_Analytics_Assistant/services/data_validation.py

USAGE:
    python services/data_validation.py
"""

import sys
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import List

sys.path.append(str(Path(__file__).resolve().parent.parent))

from sqlalchemy import text, inspect
from sqlalchemy.exc import SQLAlchemyError

from database.connection import db
from database.models import ValidationLog, MODEL_LOAD_ORDER
from utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class ValidationResult:
    """One check's outcome. status is one of 'PASS', 'WARN', 'FAIL'."""
    check_name: str
    category: str
    status: str
    expected: str
    actual: str
    message: str


class DataValidator:
    """
    Runs every validation check and persists the results. Checks are
    grouped by category: schema, row_counts, nulls, uniqueness,
    referential_integrity, domain, date_logic, business_consistency.
    """

    # Minimums verified directly against the Module 3 import (and, for
    # geolocation, the Module 4 post-dedup count of 738,336).
    EXPECTED_MIN_ROWS = {
        "category_translation": 70,
        "customers": 99000,
        "geolocation": 700000,
        "sellers": 3000,
        "products": 32000,
        "orders": 99000,
        "order_items": 112000,
        "order_payments": 103000,
        "order_reviews": 99000,
    }

    VALID_ORDER_STATUSES = {
        "delivered", "shipped", "canceled", "unavailable",
        "invoiced", "processing", "created", "approved",
    }
    VALID_PAYMENT_TYPES = {"boleto", "credit_card", "debit_card", "voucher", "not_defined"}

    # Verified against the live DB: 775 orders have no order_items, and
    # 767 of those are 'unavailable' or 'canceled' - i.e. expected,
    # since those orders never got fulfilled. The remaining ~8 (in
    # 'created'/'invoiced'/'shipped') are genuine anomalies worth a
    # WARNING, which is exactly what check_business_consistency() flags.
    STATUSES_ALLOWED_WITHOUT_ITEMS = {"unavailable", "canceled"}

    def __init__(self) -> None:
        self.engine = db.engine
        self.results: List[ValidationResult] = []

    def _check(
        self, check_name: str, category: str, status: str,
        expected: object, actual: object, message: str,
    ) -> None:
        self.results.append(
            ValidationResult(check_name, category, status, str(expected), str(actual), message)
        )

    def check_tables_exist(self) -> None:
        """All 11 tables (9 data tables + 2 audit-log tables) must exist."""
        inspector = inspect(self.engine)
        existing = set(inspector.get_table_names())
        expected_tables = {m.__tablename__ for m in MODEL_LOAD_ORDER} | {
            "data_quality_log", "validation_log",
        }
        missing = expected_tables - existing
        status = "PASS" if not missing else "FAIL"
        self._check(
            "tables_exist", "schema", status,
            f"{len(expected_tables)} tables", f"{len(existing & expected_tables)} present",
            "All expected tables present." if status == "PASS" else f"Missing: {sorted(missing)}",
        )

    def check_row_counts(self) -> None:
        """Every core table must have at least its Module 3 verified minimum row count."""
        with self.engine.connect() as conn:
            for table, minimum in self.EXPECTED_MIN_ROWS.items():
                actual = conn.execute(text(f'SELECT COUNT(*) FROM "{table}"')).scalar()
                status = "PASS" if actual >= minimum else "FAIL"
                self._check(
                    f"row_count_{table}", "row_counts", status, f">= {minimum}", actual,
                    f"{table} has {actual} rows.",
                )

    def check_no_null_categories(self) -> None:
        """
        After Module 4's cleaning, no product should have a NULL
        category (all 610 were set to 'unknown'). This should PASS -
        if it ever fails, it means new dirty data arrived without
        re-running the cleaner.
        """
        with self.engine.connect() as conn:
            count = conn.execute(
                text("SELECT COUNT(*) FROM products WHERE product_category_name IS NULL")
            ).scalar()
        status = "PASS" if count == 0 else "FAIL"
        self._check(
            "products_no_null_category", "nulls", status, 0, count,
            "No NULL product categories." if count == 0
            else f"{count} products still have a NULL category - re-run Module 4's cleaner.",
        )

    def check_primary_key_uniqueness(self) -> None:
        """
        Defense-in-depth: PostgreSQL already enforces these as primary
        keys, but explicitly re-checking catches any future bypass
        (e.g. a raw INSERT that skips the ORM) rather than assuming.
        """
        checks = [
            ("customers", "customer_id"),
            ("sellers", "seller_id"),
            ("products", "product_id"),
            ("orders", "order_id"),
        ]
        with self.engine.connect() as conn:
            for table, pk in checks:
                total = conn.execute(text(f'SELECT COUNT(*) FROM "{table}"')).scalar()
                distinct = conn.execute(text(f'SELECT COUNT(DISTINCT {pk}) FROM "{table}"')).scalar()
                status = "PASS" if total == distinct else "FAIL"
                self._check(
                    f"unique_pk_{table}", "uniqueness", status, total, distinct,
                    f"{table}.{pk}: {total} rows, {distinct} distinct." if status == "FAIL"
                    else f"{table}.{pk} is unique across {total} rows.",
                )

    def check_referential_integrity(self) -> None:
        """
        Defense-in-depth on top of the DB's own foreign keys (Module 2)
        - orphaned rows should be structurally impossible, but this
        check would catch it immediately if a schema migration ever
        weakened a constraint.
        """
        checks = [
            ("order_items_orphaned_orders",
             'SELECT COUNT(*) FROM order_items oi LEFT JOIN orders o ON oi.order_id=o.order_id WHERE o.order_id IS NULL'),
            ("order_items_orphaned_products",
             'SELECT COUNT(*) FROM order_items oi LEFT JOIN products p ON oi.product_id=p.product_id WHERE p.product_id IS NULL'),
            ("order_items_orphaned_sellers",
             'SELECT COUNT(*) FROM order_items oi LEFT JOIN sellers s ON oi.seller_id=s.seller_id WHERE s.seller_id IS NULL'),
            ("orders_orphaned_customers",
             'SELECT COUNT(*) FROM orders o LEFT JOIN customers c ON o.customer_id=c.customer_id WHERE c.customer_id IS NULL'),
            ("reviews_orphaned_orders",
             'SELECT COUNT(*) FROM order_reviews r LEFT JOIN orders o ON r.order_id=o.order_id WHERE o.order_id IS NULL'),
            ("payments_orphaned_orders",
             'SELECT COUNT(*) FROM order_payments p LEFT JOIN orders o ON p.order_id=o.order_id WHERE o.order_id IS NULL'),
        ]
        with self.engine.connect() as conn:
            for name, sql in checks:
                count = conn.execute(text(sql)).scalar()
                status = "PASS" if count == 0 else "FAIL"
                self._check(
                    name, "referential_integrity", status, 0, count,
                    "No orphaned rows." if count == 0 else f"{count} orphaned rows found.",
                )

    def check_domain_ranges(self) -> None:
        """
        Value-range checks. Verified against the live DB: review_score
        is already 1-5, prices/freight are already valid, and both
        order_status and payment_type only use recognized values. The
        payment_installments check is the one real WARNING this project
        currently has - 2 credit_card payments recorded with 0
        installments, which is unusual but not necessarily wrong (could
        be a data entry quirk from Olist itself), so it's flagged, not
        auto-corrected.
        """
        with self.engine.connect() as conn:
            bad_scores = conn.execute(text(
                "SELECT COUNT(*) FROM order_reviews WHERE review_score < 1 OR review_score > 5"
            )).scalar()
            self._check(
                "review_score_range", "domain", "PASS" if bad_scores == 0 else "FAIL",
                "1-5", bad_scores,
                "All review scores within 1-5." if bad_scores == 0
                else f"{bad_scores} reviews outside the 1-5 range.",
            )

            bad_price = conn.execute(text(
                "SELECT COUNT(*) FROM order_items WHERE price <= 0 OR freight_value < 0"
            )).scalar()
            self._check(
                "price_freight_positive", "domain", "PASS" if bad_price == 0 else "FAIL",
                "price > 0, freight >= 0", bad_price,
                "All prices/freight values valid." if bad_price == 0
                else f"{bad_price} order_items with invalid price or freight.",
            )

            statuses = {r[0] for r in conn.execute(text("SELECT DISTINCT order_status FROM orders"))}
            unknown_statuses = statuses - self.VALID_ORDER_STATUSES
            self._check(
                "order_status_domain", "domain", "PASS" if not unknown_statuses else "FAIL",
                sorted(self.VALID_ORDER_STATUSES), sorted(statuses),
                "All order statuses recognized." if not unknown_statuses
                else f"Unexpected statuses: {sorted(unknown_statuses)}",
            )

            ptypes = {r[0] for r in conn.execute(text("SELECT DISTINCT payment_type FROM order_payments"))}
            unknown_ptypes = ptypes - self.VALID_PAYMENT_TYPES
            self._check(
                "payment_type_domain", "domain", "PASS" if not unknown_ptypes else "FAIL",
                sorted(self.VALID_PAYMENT_TYPES), sorted(ptypes),
                "All payment types recognized." if not unknown_ptypes
                else f"Unexpected payment types: {sorted(unknown_ptypes)}",
            )

            zero_installments = conn.execute(text("""
                SELECT COUNT(*) FROM order_payments
                WHERE payment_installments <= 0 AND payment_type NOT IN ('voucher', 'not_defined')
            """)).scalar()
            status = "PASS" if zero_installments == 0 else "WARN"
            self._check(
                "payment_installments_positive", "domain", status,
                ">= 1 for card/boleto payments", zero_installments,
                "OK." if zero_installments == 0
                else f"{zero_installments} card/boleto payments recorded with 0 installments.",
            )

    def check_date_logic(self) -> None:
        """Timestamps must be internally consistent (verified: 0 violations currently)."""
        with self.engine.connect() as conn:
            bad_approval = conn.execute(text("""
                SELECT COUNT(*) FROM orders
                WHERE order_approved_at IS NOT NULL AND order_approved_at < order_purchase_timestamp
            """)).scalar()
            self._check(
                "approval_after_purchase", "date_logic", "PASS" if bad_approval == 0 else "FAIL",
                0, bad_approval,
                "All approvals occur at/after purchase." if bad_approval == 0
                else f"{bad_approval} orders approved before they were purchased.",
            )

            bad_delivery = conn.execute(text("""
                SELECT COUNT(*) FROM orders
                WHERE order_delivered_customer_date IS NOT NULL
                  AND order_delivered_customer_date < order_purchase_timestamp
            """)).scalar()
            self._check(
                "delivery_after_purchase", "date_logic", "PASS" if bad_delivery == 0 else "FAIL",
                0, bad_delivery,
                "All deliveries occur at/after purchase." if bad_delivery == 0
                else f"{bad_delivery} orders delivered before they were purchased.",
            )

    def check_business_consistency(self) -> None:
        """
        Cross-table business logic, not enforceable by a foreign key.
        Verified against the live DB: 775 orders have no order_items,
        and 767 of those are 'unavailable' or 'canceled' (expected -
        those orders never shipped anything). The remaining ~8 are a
        genuine WARNING. Similarly, exactly 1 delivered order has no
        payment record at all, which is a real anomaly worth surfacing
        even though it can't be auto-fixed.
        """
        with self.engine.connect() as conn:
            allowed = ", ".join(f"'{s}'" for s in self.STATUSES_ALLOWED_WITHOUT_ITEMS)
            unexpected_no_items = conn.execute(text(f"""
                SELECT COUNT(*) FROM orders o
                WHERE o.order_status NOT IN ({allowed})
                  AND NOT EXISTS (SELECT 1 FROM order_items oi WHERE oi.order_id = o.order_id)
            """)).scalar()
            status = "PASS" if unexpected_no_items == 0 else "WARN"
            self._check(
                "orders_without_items", "business_consistency", status, 0, unexpected_no_items,
                "OK (only canceled/unavailable orders lack items)." if unexpected_no_items == 0
                else f"{unexpected_no_items} orders with an active status have no items recorded.",
            )

            no_payment = conn.execute(text("""
                SELECT COUNT(*) FROM orders o
                WHERE NOT EXISTS (SELECT 1 FROM order_payments op WHERE op.order_id = o.order_id)
            """)).scalar()
            status = "PASS" if no_payment == 0 else "WARN"
            self._check(
                "orders_without_payment", "business_consistency", status, 0, no_payment,
                "OK." if no_payment == 0 else f"{no_payment} orders have no payment record at all.",
            )

    def run_all(self) -> List[ValidationResult]:
        """Runs every check, in order, and persists all results under one run_id."""
        self.results = []
        try:
            self.check_tables_exist()
            self.check_row_counts()
            self.check_no_null_categories()
            self.check_primary_key_uniqueness()
            self.check_referential_integrity()
            self.check_domain_ranges()
            self.check_date_logic()
            self.check_business_consistency()
            self._persist_results()
        except SQLAlchemyError as exc:
            logger.error("Data validation failed: %s", exc)
            raise
        return self.results

    def _persist_results(self) -> None:
        run_id = str(uuid.uuid4())
        with self.engine.begin() as conn:
            for r in self.results:
                conn.execute(ValidationLog.__table__.insert(), {
                    "run_id": run_id,
                    "check_name": r.check_name,
                    "category": r.category,
                    "status": r.status,
                    "expected": r.expected,
                    "actual": r.actual,
                    "message": r.message,
                })
        logger.info("Persisted %d validation results under run_id=%s", len(self.results), run_id)

    def summary(self) -> dict:
        return {
            "total": len(self.results),
            "passed": sum(1 for r in self.results if r.status == "PASS"),
            "warned": sum(1 for r in self.results if r.status == "WARN"),
            "failed": sum(1 for r in self.results if r.status == "FAIL"),
        }


def main() -> None:
    """CLI entry point: `python services/data_validation.py`."""
    if not db.test_connection():
        print("Cannot validate - database connection failed. Run tests/test_connection.py first.")
        sys.exit(1)

    validator = DataValidator()
    results = validator.run_all()
    summary = validator.summary()

    print("\n=== Data Validation Report ===")
    for r in results:
        print(f"  [{r.status}] {r.check_name}: {r.message}")

    print(
        f"\nSummary: {summary['passed']} passed, {summary['warned']} warnings, "
        f"{summary['failed']} failed (of {summary['total']} checks)"
    )
    if summary["failed"] > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
