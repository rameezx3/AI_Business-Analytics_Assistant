"""
services/data_cleaning.py

WHY THIS FILE EXISTS:
    Module 4: automatically detects and fixes real data quality issues
    in the data loaded by Module 3. Every rule below was derived by
    querying the LIVE database first (see each method's docstring for
    the actual counts found) - nothing here is generic boilerplate
    copied from a tutorial.

    Design principle: never silently delete or guess.
        - If a fix is well-justified (e.g. filling a missing category
          with a real 'unknown' placeholder, imputing 2 missing product
          weights with the dataset median), it's applied AND logged.
        - If a fix can't be honestly justified (e.g. we cannot know the
          true delivery date for an order that's missing one), the
          issue is FLAGGED in data_quality_log and left alone.
    Every action either way is auditable in the data_quality_log table.

WHERE THIS FILE BELONGS:
    AI_Business_Analytics_Assistant/services/data_cleaning.py

USAGE:
    python services/data_cleaning.py
"""

import sys
from pathlib import Path
from typing import Dict

sys.path.append(str(Path(__file__).resolve().parent.parent))

from sqlalchemy import text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import SQLAlchemyError

from database.connection import db
from database.models import DataQualityLog
from utils.logger import get_logger

logger = get_logger(__name__)


class DataCleaner:
    """
    Runs a fixed sequence of cleaning operations against the tables
    loaded by Module 3. Each method documents the exact issue count
    found when this dataset was inspected, so future readers know
    these rules are evidence-based, not assumed.
    """

    # Brazil's approximate bounding box - used to catch geolocation rows
    # with clearly wrong GPS coordinates (verified: 31 such rows exist,
    # e.g. lat=28.0/lng=-15.5, which is off the coast of West Africa).
    BRAZIL_LAT_MIN, BRAZIL_LAT_MAX = -34.0, 6.0
    BRAZIL_LNG_MIN, BRAZIL_LNG_MAX = -75.0, -32.0

    VALID_BRAZIL_STATES = {
        "AC", "AL", "AP", "AM", "BA", "CE", "DF", "ES", "GO", "MA", "MT",
        "MS", "MG", "PA", "PB", "PR", "PE", "PI", "RJ", "RN", "RS", "RO",
        "RR", "SC", "SP", "SE", "TO",
    }

    def __init__(self) -> None:
        self.engine = db.engine

    def _log_issue(
        self, conn, table_name: str, issue_type: str, record_id: str,
        description: str, action_taken: str,
    ) -> None:
        """
        Writes one audit row. Uses ON CONFLICT DO NOTHING against the
        (table_name, issue_type, record_identifier) unique constraint
        so re-running the cleaner never creates duplicate log entries
        for an issue that's still present (e.g. the 8 flagged orders).
        """
        stmt = pg_insert(DataQualityLog.__table__).values(
            table_name=table_name,
            issue_type=issue_type,
            record_identifier=str(record_id),
            description=description,
            action_taken=action_taken,
        ).on_conflict_do_nothing(
            index_elements=["table_name", "issue_type", "record_identifier"]
        )
        conn.execute(stmt)

    def clean_products(self) -> Dict[str, int]:
        """
        Found by querying the live DB:
          - 610 products have NULL product_category_name, and the SAME
            610 rows also have NULL product_photos_qty.
          - 2 products have NULL weight/length/height/width. One of
            those is the "fully blank" row above; the other has a real
            category ('bebes') but no recorded physical dimensions.

        Fixes applied:
          - Missing category -> 'unknown' (a real row is inserted into
            category_translation first, so the foreign key stays valid
            instead of being relaxed to allow NULL forever).
          - Missing photos_qty -> 0 (distinct from "has 1 photo").
          - Missing weight/length/height/width -> filled with that
            column's own MEDIAN across all products. Median (not mean)
            because product size/weight is heavily right-skewed by a
            handful of large/heavy items - the mean would overstate a
            "typical" product's size.
        """
        stats = {"category_filled": 0, "photos_qty_filled": 0, "dimensions_filled": 0}
        with self.engine.begin() as conn:
            conn.execute(text("""
                INSERT INTO category_translation
                    (product_category_name, product_category_name_english)
                VALUES ('unknown', 'unknown')
                ON CONFLICT (product_category_name) DO NOTHING
            """))

            missing_category = conn.execute(text("""
                SELECT product_id FROM products WHERE product_category_name IS NULL
            """)).fetchall()
            for row in missing_category:
                self._log_issue(
                    conn, "products", "missing_category", row.product_id,
                    "product_category_name was NULL.",
                    "Set to 'unknown' (a matching row was added to category_translation).",
                )
            result = conn.execute(text("""
                UPDATE products SET product_category_name = 'unknown'
                WHERE product_category_name IS NULL
            """))
            stats["category_filled"] = result.rowcount

            result = conn.execute(text("""
                UPDATE products SET product_photos_qty = 0
                WHERE product_photos_qty IS NULL
            """))
            stats["photos_qty_filled"] = result.rowcount

            medians = conn.execute(text("""
                SELECT
                    PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY product_weight_g) AS w,
                    PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY product_length_cm) AS l,
                    PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY product_height_cm) AS h,
                    PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY product_width_cm) AS wd
                FROM products
            """)).fetchone()

            if medians is None or medians.w is None:
                # PERCENTILE_CONT returns NULL only if the products table
                # has no rows with a non-NULL value to compute a median
                # from - i.e. the table is empty or entirely blank. That
                # is a much bigger problem than "2 rows need imputing",
                # so fail loudly here instead of crashing later with a
                # confusing TypeError from round(None).
                raise RuntimeError(
                    "Cannot compute median product dimensions - the products "
                    "table appears to be empty or has no valid weight data. "
                    "Re-run database/import_csv.py before cleaning."
                )

            missing_dims = conn.execute(text("""
                SELECT product_id FROM products
                WHERE product_weight_g IS NULL OR product_length_cm IS NULL
                   OR product_height_cm IS NULL OR product_width_cm IS NULL
            """)).fetchall()
            for row in missing_dims:
                self._log_issue(
                    conn, "products", "missing_dimensions", row.product_id,
                    "One or more of weight/length/height/width was NULL.",
                    f"Imputed with dataset medians "
                    f"(weight={round(medians.w)}g, length={round(medians.l)}cm, "
                    f"height={round(medians.h)}cm, width={round(medians.wd)}cm).",
                )
            result = conn.execute(text("""
                UPDATE products SET
                    product_weight_g = COALESCE(product_weight_g, :w),
                    product_length_cm = COALESCE(product_length_cm, :l),
                    product_height_cm = COALESCE(product_height_cm, :h),
                    product_width_cm = COALESCE(product_width_cm, :wd)
                WHERE product_weight_g IS NULL OR product_length_cm IS NULL
                   OR product_height_cm IS NULL OR product_width_cm IS NULL
            """), {
                # PERCENTILE_CONT always returns a float (e.g. 700.0),
                # but these are INTEGER columns - cast to int in Python
                # rather than relying on Postgres/pg8000 to coerce it
                # (same class of bug as Module 3's CSV import: pg8000
                # correctly refuses "700.0" for an INTEGER column).
                "w": round(medians.w), "l": round(medians.l),
                "h": round(medians.h), "wd": round(medians.wd),
            })
            stats["dimensions_filled"] = result.rowcount

        logger.info("clean_products(): %s", stats)
        return stats

    def flag_delivery_anomalies(self) -> int:
        """
        Found by querying the live DB: 8 orders have order_status =
        'delivered' but no order_delivered_customer_date. There is no
        reliable way to reconstruct the true delivery date, so these
        are FLAGGED only - downstream modules (Sales Analytics,
        Forecasting) should know these 8 rows exist, not have a guessed
        date silently baked in.
        """
        with self.engine.begin() as conn:
            rows = conn.execute(text("""
                SELECT order_id FROM orders
                WHERE order_status = 'delivered' AND order_delivered_customer_date IS NULL
            """)).fetchall()
            for row in rows:
                self._log_issue(
                    conn, "orders", "delivered_missing_date", row.order_id,
                    "order_status='delivered' but order_delivered_customer_date is NULL.",
                    "Flagged only - true delivery date cannot be reconstructed.",
                )
        logger.info("flag_delivery_anomalies(): %d orders flagged", len(rows))
        return len(rows)

    def clean_geolocation(self) -> Dict[str, int]:
        """
        Found by querying the live DB:
          - 261,831 exact duplicate rows (same zip+lat+lng+city+state
            repeated) out of 1,000,163 total - pure redundancy, safe
            to remove without losing any distinct information.
          - 31 rows with lat/lng clearly outside Brazil's bounding box
            (e.g. lat=28.0, lng=-15.5 - off the coast of West Africa,
            not Brazil). Logged before removal, since plotting them
            would visibly break any map-based view.
        """
        stats = {"duplicates_removed": 0, "out_of_bounds_removed": 0}
        with self.engine.begin() as conn:
            before = conn.execute(text("SELECT COUNT(*) FROM geolocation")).scalar()

            out_of_bounds = conn.execute(text("""
                SELECT id, geolocation_lat, geolocation_lng FROM geolocation
                WHERE geolocation_lat > :lat_max OR geolocation_lat < :lat_min
                   OR geolocation_lng > :lng_max OR geolocation_lng < :lng_min
            """), {
                "lat_max": self.BRAZIL_LAT_MAX, "lat_min": self.BRAZIL_LAT_MIN,
                "lng_max": self.BRAZIL_LNG_MAX, "lng_min": self.BRAZIL_LNG_MIN,
            }).fetchall()
            for row in out_of_bounds:
                self._log_issue(
                    conn, "geolocation", "coordinates_outside_brazil", row.id,
                    f"lat={row.geolocation_lat}, lng={row.geolocation_lng} "
                    "falls outside Brazil's bounding box.",
                    "Row removed - not usable for Brazil-only geographic analytics.",
                )
            result = conn.execute(text("""
                DELETE FROM geolocation
                WHERE geolocation_lat > :lat_max OR geolocation_lat < :lat_min
                   OR geolocation_lng > :lng_max OR geolocation_lng < :lng_min
            """), {
                "lat_max": self.BRAZIL_LAT_MAX, "lat_min": self.BRAZIL_LAT_MIN,
                "lng_max": self.BRAZIL_LNG_MAX, "lng_min": self.BRAZIL_LNG_MIN,
            })
            stats["out_of_bounds_removed"] = result.rowcount

            # Efficient Postgres dedup idiom: rank rows within each
            # duplicate group by id by, then delete everything but rank 1.
            # (An earlier "ctid NOT IN (subquery)" version was tested and
            # is dramatically slower on a 1M-row table - this window
            # function version was benchmarked at ~5.6s vs. a timeout.)
            result = conn.execute(text("""
                DELETE FROM geolocation g
                USING (
                    SELECT id, ROW_NUMBER() OVER (
                        PARTITION BY geolocation_zip_code_prefix, geolocation_lat,
                                     geolocation_lng, geolocation_city, geolocation_state
                        ORDER BY id
                    ) AS rn
                    FROM geolocation
                ) ranked
                WHERE g.id = ranked.id AND ranked.rn > 1
            """))
            stats["duplicates_removed"] = result.rowcount

            after = conn.execute(text("SELECT COUNT(*) FROM geolocation")).scalar()
            self._log_issue(
                conn, "geolocation", "bulk_dedup_summary", "geolocation_table",
                f"{stats['duplicates_removed']} exact-duplicate rows found "
                f"out of {before} total.",
                f"Removed. Row count: {before} -> {after}.",
            )

        logger.info("clean_geolocation(): %s", stats)
        return stats

    def validate_state_codes(self) -> int:
        """
        Defensive check - 0 issues found when this dataset was tested,
        but kept as a REAL, executing check (not just a comment) so a
        future data refresh with bad state codes gets caught
        automatically instead of silently passing through.
        """
        total_issues = 0
        with self.engine.begin() as conn:
            state_list = ", ".join(f"'{s}'" for s in self.VALID_BRAZIL_STATES)
            for table, state_col, id_col in [
                ("customers", "customer_state", "customer_id"),
                ("sellers", "seller_state", "seller_id"),
            ]:
                rows = conn.execute(text(f"""
                    SELECT {id_col} AS record_id FROM {table}
                    WHERE {state_col} NOT IN ({state_list})
                """)).fetchall()
                for row in rows:
                    self._log_issue(
                        conn, table, "invalid_state_code", row.record_id,
                        f"{state_col} is not a recognized Brazilian state code.",
                        "Flagged only - no fix applied.",
                    )
                total_issues += len(rows)
        logger.info("validate_state_codes(): %d issues found", total_issues)
        return total_issues

    def check_price_integrity(self) -> int:
        """
        Defensive check - 0 issues found on this dataset, kept as a
        real running check for the same reason as validate_state_codes.
        """
        with self.engine.begin() as conn:
            rows = conn.execute(text("""
                SELECT order_id, order_item_id FROM order_items
                WHERE price <= 0 OR freight_value < 0
            """)).fetchall()
            for row in rows:
                self._log_issue(
                    conn, "order_items", "invalid_price_or_freight",
                    f"{row.order_id}:{row.order_item_id}",
                    "price <= 0 or freight_value < 0.",
                    "Flagged only - no fix applied.",
                )
        logger.info("check_price_integrity(): %d issues found", len(rows))
        return len(rows)

    def run_all(self) -> Dict[str, object]:
        """Runs every cleaning step in sequence. Safe to re-run at any time."""
        try:
            return {
                "products": self.clean_products(),
                "delivery_anomalies_flagged": self.flag_delivery_anomalies(),
                "geolocation": self.clean_geolocation(),
                "invalid_state_codes": self.validate_state_codes(),
                "price_integrity_issues": self.check_price_integrity(),
            }
        except SQLAlchemyError as exc:
            logger.error("Data cleaning failed: %s", exc)
            raise


def main() -> None:
    """CLI entry point: `python services/data_cleaning.py`."""
    if not db.test_connection():
        print("Cannot clean data - database connection failed. Run tests/test_connection.py first.")
        sys.exit(1)

    cleaner = DataCleaner()
    report = cleaner.run_all()

    print("\n=== Data Cleaning Report ===")
    for key, value in report.items():
        print(f"  {key}: {value}")
    print("\nFull audit trail available in the data_quality_log table.")


if __name__ == "__main__":
    main()
