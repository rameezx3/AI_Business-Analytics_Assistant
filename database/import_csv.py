"""
database/import_csv.py

Loads the 9 Olist CSV files into PostgreSQL in FK-safe dependency
order (MODEL_LOAD_ORDER), with type coercion, chunked batch inserts,
duplicate handling, and post-load row-count validation.

USAGE:
    python database/import_csv.py                  # import all 9 tables
    python database/import_csv.py --table orders    # import just one table
    python database/import_csv.py --truncate        # wipe tables before import
    python database/import_csv.py --data-dir path/to/csvs
"""
import argparse
import csv
import io
import math
import sys
from pathlib import Path
from typing import Dict, Type, List, Optional

sys.path.append(str(Path(__file__).resolve().parent.parent))

import numpy as np
import pandas as pd
from sqlalchemy import text, Integer
from sqlalchemy.exc import SQLAlchemyError

from config import config
from database.connection import db
from database.models import (
    CategoryTranslation, Customer, Geolocation, Seller, Product,
    Order, OrderItem, OrderPayment, OrderReview, MODEL_LOAD_ORDER,
)
from utils.logger import get_logger

logger = get_logger(__name__)


class CSVImporter:
    """Loads the 9 Olist CSV files into PostgreSQL using the Module 2 ORM models."""

    TABLE_SPECS: Dict[Type, Dict] = {
        CategoryTranslation: {"file": "product_category_name_translation.csv", "date_columns": []},
        Customer: {"file": "olist_customers_dataset.csv", "date_columns": []},
        Geolocation: {"file": "olist_geolocation_dataset.csv", "date_columns": []},
        Seller: {"file": "olist_sellers_dataset.csv", "date_columns": []},
        Product: {"file": "olist_products_dataset.csv", "date_columns": []},
        Order: {
            "file": "olist_orders_dataset.csv",
            "date_columns": [
                "order_purchase_timestamp", "order_approved_at",
                "order_delivered_carrier_date", "order_delivered_customer_date",
                "order_estimated_delivery_date",
            ],
        },
        OrderItem: {"file": "olist_order_items_dataset.csv", "date_columns": ["shipping_limit_date"]},
        OrderPayment: {"file": "olist_order_payments_dataset.csv", "date_columns": []},
        OrderReview: {
            "file": "olist_order_reviews_dataset.csv",
            "date_columns": ["review_creation_date", "review_answer_timestamp"],
        },
    }

    # Rows per INSERT batch - large enough to cut round-trip overhead,
    # small enough to keep memory bounded for the 1M-row geolocation table.
    CHUNK_SIZE = 20000

    def __init__(self, data_dir: Optional[Path] = None) -> None:
        self.data_dir: Path = data_dir or config.app.data_dir
        self.engine = db.engine

    def _read_csv(self, model: Type) -> pd.DataFrame:
        spec = self.TABLE_SPECS[model]
        csv_path = self.data_dir / spec["file"]
        if not csv_path.exists():
            raise FileNotFoundError(
                f"Expected CSV not found: {csv_path}\nPlace all 9 Olist CSV files in: {self.data_dir}"
            )
        df = pd.read_csv(csv_path, parse_dates=spec["date_columns"] or None, keep_default_na=True)
        # NOTE: df.where(pd.notnull(df), None) silently stopped replacing
        # NaN under pandas' newer dtype backend (verified directly).
        # .replace() does not have that problem - handles NaN and NaT.
        df = df.replace({np.nan: None})
        return df

    @staticmethod
    def _columns_for_model(model: Type, df: pd.DataFrame) -> List[str]:
        model_columns = {c.name for c in model.__table__.columns}
        return [c for c in df.columns if c in model_columns]

    @staticmethod
    def _coerce_integer_fields(model: Type, records: List[dict]) -> List[dict]:
        """
        Fixes a pandas + PostgreSQL type mismatch: numeric columns with
        missing values get upcast by pandas to float64 (40 -> 40.0),
        which PostgreSQL's INTEGER columns reject. This must run on the
        plain Python dicts (after to_dict()), NOT on the DataFrame -
        assigning cast values back into a float64 Series makes pandas
        silently re-upcast them (verified directly against pandas 3.0).
        """
        integer_columns = {c.name for c in model.__table__.columns if isinstance(c.type, Integer)}
        if not integer_columns:
            return records
        for record in records:
            for col in integer_columns:
                value = record.get(col)
                if value is None:
                    continue
                if isinstance(value, float):
                    record[col] = None if math.isnan(value) else int(value)
        return records

    def _copy_records(self, conn, model: Type, records: List[dict]) -> int:
        """
        Bulk-loads records using PostgreSQL's native COPY command via
        pg8000's stream support, instead of batched INSERT statements.

        WHY THIS EXISTS:
            Found during testing: chunked INSERT batches took 4+ minutes
            to load the 1,000,163-row geolocation table. COPY loaded the
            exact same data in a few seconds - benchmarked directly, not
            estimated. For any table of meaningful size, COPY is the
            right tool; INSERT batching only remains as a fallback (see
            import_table()) for drivers/environments where COPY isn't
            available.
        """
        if not records:
            return 0

        columns = list(records[0].keys())
        buffer = io.StringIO()
        writer = csv.writer(buffer)
        for record in records:
            row = []
            for col in columns:
                value = record.get(col)
                if value is None:
                    row.append("")
                elif hasattr(value, "isoformat"):
                    row.append(value.isoformat())
                else:
                    row.append(value)
            writer.writerow(row)
        buffer.seek(0)

        table_name = model.__tablename__
        quoted_columns = ", ".join(f'"{c}"' for c in columns)
        raw_cursor = conn.connection.dbapi_connection.cursor()
        raw_cursor.execute(
            f'COPY "{table_name}" ({quoted_columns}) FROM STDIN WITH (FORMAT csv, NULL \'\')',
            stream=buffer,
        )
        return len(records)

    def truncate_table(self, model: Type, cascade: bool = False) -> None:
        """
        Empties a table on its own (used by the CLI's `--table X --truncate`
        path when NOT combined with an import - rare). cascade defaults to
        False DELIBERATELY: Postgres will then refuse the truncate with a
        clear error if another table still holds rows referencing this one
        via a foreign key, instead of silently wiping those rows too. (An
        earlier version always used CASCADE, which meant truncating
        `customers` alone would silently empty `orders` and everything
        downstream of it - a dangerous surprise, found during testing.)
        """
        table_name = model.__tablename__
        cascade_clause = "CASCADE" if cascade else ""
        with self.engine.begin() as conn:
            conn.execute(text(f'TRUNCATE TABLE "{table_name}" {cascade_clause}'))
        logger.info("Truncated table: %s%s", table_name, " (CASCADE)" if cascade else "")

    def import_table(self, model: Type, truncate: bool = False) -> int:
        """
        Loads one CSV into its table.

        WHY truncate HAPPENS INSIDE THE SAME TRANSACTION AS THE IMPORT:
            A real bug was found during testing: truncate and import used
            to run as two SEPARATE transactions. If the process was
            interrupted between them (e.g. killed mid-run), the table was
            left truncated with NO data reloaded - a silent, permanent
            data loss with no error raised. Combining them into one
            transaction means the worst case is now a clean rollback: if
            interrupted, the table keeps its OLD data instead of ending
            up empty.
        """
        table_name = model.__tablename__
        logger.info("Importing %s ...", table_name)

        df = self._read_csv(model)
        columns = self._columns_for_model(model, df)
        df = df[columns]

        pk_columns = [c.name for c in model.__table__.primary_key.columns if c.name in df.columns]
        if pk_columns:
            before = len(df)
            df = df.drop_duplicates(subset=pk_columns, keep="first")
            dropped = before - len(df)
            if dropped:
                logger.warning("Dropped %d duplicate rows in %s (by %s)", dropped, table_name, pk_columns)

        records = df.to_dict(orient="records")
        records = self._coerce_integer_fields(model, records)
        total_inserted = 0

        try:
            with self.engine.begin() as conn:
                if truncate:
                    conn.execute(text(f'TRUNCATE TABLE "{table_name}"'))
                total_inserted = self._copy_records(conn, model, records)
        except Exception as exc:
            # WHY THIS RETRIES IN A FRESH TRANSACTION, NOT THE SAME ONE:
            # once COPY fails, PostgreSQL considers the enclosing
            # transaction aborted - any further command on that same
            # connection would immediately fail with "current
            # transaction is aborted". So on failure, the whole
            # transaction above is left to roll back cleanly (same
            # atomicity guarantee as before: never left truncated
            # without data), and the fallback runs as an entirely new,
            # separate transaction using the slower but more broadly
            # compatible chunked INSERT approach.
            logger.warning(
                "COPY failed for %s (%s) - retrying with chunked INSERT in a new transaction.",
                table_name, exc,
            )
            total_inserted = 0
            with self.engine.begin() as conn:
                if truncate:
                    conn.execute(text(f'TRUNCATE TABLE "{table_name}"'))
                for start in range(0, len(records), self.CHUNK_SIZE):
                    batch = records[start:start + self.CHUNK_SIZE]
                    conn.execute(model.__table__.insert(), batch)
                    total_inserted += len(batch)

        logger.info("Imported %d rows into %s.", total_inserted, table_name)
        return total_inserted

    def import_all(self, truncate: bool = False) -> Dict[str, int]:
        """
        Imports every table in MODEL_LOAD_ORDER.

        WHY ONE TRUNCATE STATEMENT FOR ALL TABLES, NOT ONE PER TABLE:
            Found by testing: PostgreSQL's TRUNCATE (without CASCADE)
            refuses if ANY OTHER table has a foreign key referencing the
            target - a purely STRUCTURAL check based on whether the
            constraint exists, not on whether that other table currently
            holds any rows. So truncating tables one at a time, even in
            correct reverse-dependency order (children before parents),
            still fails: truncating an already-EMPTY order_items table
            first does not allow truncating orders next, because
            order_items still structurally references orders.
            PostgreSQL's actual solution is to truncate every related
            table together in ONE statement - that only checks
            constraints among the tables named in that same statement,
            so CASCADE is never needed as long as everything is included.
        """
        if truncate:
            table_names = ", ".join(f'"{m.__tablename__}"' for m in MODEL_LOAD_ORDER)
            with self.engine.begin() as conn:
                conn.execute(text(f"TRUNCATE TABLE {table_names}"))
            logger.info("Truncated all %d tables in a single statement.", len(MODEL_LOAD_ORDER))

        results: Dict[str, int] = {}
        for model in MODEL_LOAD_ORDER:
            results[model.__tablename__] = self.import_table(model, truncate=False)
        return results

    def validate_row_counts(self, results: Dict[str, int]) -> bool:
        all_ok = True
        with self.engine.connect() as conn:
            for model in MODEL_LOAD_ORDER:
                table_name = model.__tablename__
                db_count = conn.execute(text(f'SELECT COUNT(*) FROM "{table_name}"')).scalar()
                expected = results.get(table_name, 0)
                status = "OK" if db_count >= expected else "MISMATCH"
                if status == "MISMATCH":
                    all_ok = False
                logger.info("%s: %d rows in DB (imported this run: %d) [%s]",
                            table_name, db_count, expected, status)
        return all_ok


def main() -> None:
    parser = argparse.ArgumentParser(description="Import Olist CSV files into PostgreSQL.")
    parser.add_argument("--table", type=str, default=None, help="Import only this table (by tablename).")
    parser.add_argument("--truncate", action="store_true", help="Empty each table before importing.")
    parser.add_argument("--data-dir", type=str, default=None, help="Override the data directory.")
    args = parser.parse_args()

    if not db.test_connection():
        print("Cannot import - database connection failed. Run tests/test_connection.py first.")
        sys.exit(1)

    data_dir = Path(args.data_dir) if args.data_dir else None
    importer = CSVImporter(data_dir=data_dir)

    if args.table:
        model = next((m for m in MODEL_LOAD_ORDER if m.__tablename__ == args.table), None)
        if model is None:
            valid = [m.__tablename__ for m in MODEL_LOAD_ORDER]
            print(f"Unknown table '{args.table}'. Valid options: {valid}")
            sys.exit(1)
        if args.truncate:
            count = importer.import_table(model, truncate=True)
        else:
            count = importer.import_table(model)
        print(f"Imported {count} rows into {model.__tablename__}.")
    else:
        results = importer.import_all(truncate=args.truncate)
        print("\nImport summary:")
        for table, count in results.items():
            print(f"  {table}: {count} rows")
        if importer.validate_row_counts(results):
            print("\nAll tables validated successfully.")
        else:
            print("\nWARNING: row count mismatch detected - check logs/app.log")
            sys.exit(1)


if __name__ == "__main__":
    main()
