"""
database/init_db.py

SchemaManager: create/drop/verify the PostgreSQL schema for every model.
USAGE:
    python database/init_db.py            # create all tables
    python database/init_db.py --drop     # drop then recreate all tables
"""
import argparse
import sys
from pathlib import Path
from typing import List

sys.path.append(str(Path(__file__).resolve().parent.parent))

from sqlalchemy import inspect, text
from sqlalchemy.exc import SQLAlchemyError

from database.connection import db
from database.models import Base, MODEL_LOAD_ORDER
from utils.logger import get_logger

logger = get_logger(__name__)


class SchemaManager:
    def __init__(self) -> None:
        self.engine = db.engine

    def create_all(self) -> None:
        try:
            Base.metadata.create_all(self.engine)
            # The project's original geolocation import predates its
            # synthetic primary key. create_all() does not alter an
            # existing table, so migrate that one known legacy shape.
            with self.engine.begin() as conn:
                conn.execute(
                    text("ALTER TABLE geolocation ADD COLUMN IF NOT EXISTS id SERIAL")
                )
                conn.execute(text("""
                    DO $$
                    BEGIN
                        IF NOT EXISTS (
                            SELECT 1 FROM pg_constraint
                            WHERE conrelid = 'geolocation'::regclass AND contype = 'p'
                        ) THEN
                            ALTER TABLE geolocation ADD CONSTRAINT geolocation_pkey PRIMARY KEY (id);
                        END IF;
                    END $$;
                """))
            # SQLAlchemy skips existing tables (and therefore their indexes)
            # when create_all() runs. Ensure declared indexes are also
            # reconciled for databases created by earlier project versions.
            for table in Base.metadata.sorted_tables:
                for index in table.indexes:
                    index.create(self.engine, checkfirst=True)
            logger.info("Schema created successfully (%d tables).", len(MODEL_LOAD_ORDER))
        except SQLAlchemyError as exc:
            logger.error("Failed to create schema: %s", exc)
            raise

    def drop_all(self) -> None:
        try:
            Base.metadata.drop_all(self.engine)
            logger.warning("All tables dropped.")
        except SQLAlchemyError as exc:
            logger.error("Failed to drop schema: %s", exc)
            raise

    def reset(self) -> None:
        self.drop_all()
        self.create_all()

    def list_tables(self) -> List[str]:
        inspector = inspect(self.engine)
        return inspector.get_table_names()

    def verify_schema(self) -> bool:
        existing = set(self.list_tables())
        expected = {model.__tablename__ for model in MODEL_LOAD_ORDER}
        missing = expected - existing
        if missing:
            logger.error("Missing tables in database: %s", missing)
            return False
        logger.info("Schema verified - all %d expected tables exist.", len(expected))
        return True


def main() -> None:
    parser = argparse.ArgumentParser(description="Manage the project's PostgreSQL schema.")
    parser.add_argument("--drop", action="store_true",
                         help="Drop all tables before recreating them (DESTROYS existing data).")
    args = parser.parse_args()

    if not db.test_connection():
        print("Cannot create schema - database connection failed. "
              "Run tests/test_connection.py first to diagnose.")
        sys.exit(1)

    manager = SchemaManager()
    if args.drop:
        confirm = input("This will DROP ALL TABLES and their data. Type 'yes' to continue: ")
        if confirm.strip().lower() != "yes":
            print("Aborted.")
            sys.exit(0)
        manager.reset()
    else:
        manager.create_all()

    if manager.verify_schema():
        print(f"Schema ready. Tables: {sorted(manager.list_tables())}")
    else:
        print("Schema verification failed - see logs/app.log")
        sys.exit(1)


if __name__ == "__main__":
    main()
