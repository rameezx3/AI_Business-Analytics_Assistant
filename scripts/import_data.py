
import os
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv
from sqlalchemy import create_engine, URL, text

# Project paths and environment variables
BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
load_dotenv(BASE_DIR / ".env")

# PostgreSQL connection using the project's .env settings
db_url = URL.create(
    drivername="postgresql+pg8000",
    username=os.getenv("DB_USER", "postgres"),
    password=os.getenv("DB_PASSWORD"),
    host=os.getenv("DB_HOST", "localhost"),
    port=int(os.getenv("DB_PORT", "5432")),
    database=os.getenv("DB_NAME", "bi_assistant_db"),
)

engine = create_engine(db_url, pool_pre_ping=True)

# CSV filenames mapped to the table names used by the application
FILES = {
    "olist_customers_dataset.csv": "customers",
    "olist_geolocation_dataset.csv": "geolocation",
    "olist_orders_dataset.csv": "orders",
    "olist_order_items_dataset.csv": "order_items",
    "olist_order_payments_dataset.csv": "order_payments",
    "olist_order_reviews_dataset.csv": "order_reviews",
    "olist_products_dataset.csv": "products",
    "olist_sellers_dataset.csv": "sellers",
    "product_category_name_translation.csv": "product_category_translation",
}


def main():
    try:
        # Confirm the database connection before importing
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        print("PostgreSQL connection successful.")

        for filename, table_name in FILES.items():
            csv_path = DATA_DIR / filename

            if not csv_path.exists():
                raise FileNotFoundError(f"CSV file not found: {csv_path}")

            print(f"\nImporting {filename} into table '{table_name}'...")

            # Load one CSV at a time to keep memory usage manageable.
            # PostgreSQL column types are inferred from the CSV data.
            dataframe = pd.read_csv(csv_path, low_memory=False)

            dataframe.to_sql(
                name=table_name,
                con=engine,
                if_exists="replace",
                index=False,
                chunksize=5000,
                method=None,
            )

            print(f"Imported {len(dataframe):,} rows into '{table_name}'.")

            del dataframe

        print("\nAll nine CSV files were imported successfully.")

        with engine.connect() as connection:
            for table_name in FILES.values():
                count = connection.execute(
                    text(f'SELECT COUNT(*) FROM "{table_name}"')
                ).scalar_one()
                print(f"{table_name}: {count:,} rows")

        print("\nDatabase initialization complete.")

    except Exception as error:
        print(f"\nIMPORT FAILED: {error}")
        raise
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
