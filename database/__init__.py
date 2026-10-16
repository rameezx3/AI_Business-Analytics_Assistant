"""
database package

Everything related to talking to PostgreSQL lives here:
    - connection.py  -> engine/session management (Module 1)
    - models/         -> SQLAlchemy ORM models / schema (Module 2)
    - import_csv.py   -> CSV -> PostgreSQL loader (Module 3)

Other packages should only ever import `db` from database.connection -
they should never create their own engine.
"""
