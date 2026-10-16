"""
database/connection.py

Provides DatabaseConnection: one shared SQLAlchemy engine/session
factory for the whole app, plus test_connection() for startup checks.
"""

from contextlib import contextmanager
from typing import Generator

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.exc import SQLAlchemyError, OperationalError

from config import config
from utils.logger import get_logger

logger = get_logger(__name__)


class DatabaseConnection:
    def __init__(self) -> None:
        self._engine: Engine = self._create_engine()
        self._session_factory = sessionmaker(
            bind=self._engine, autoflush=False, autocommit=False, expire_on_commit=False,
        )
        logger.info("DatabaseConnection initialized.")

    def _create_engine(self) -> Engine:
        try:
            engine = create_engine(
                config.database.connection_url,
                pool_size=config.database.pool_size,
                max_overflow=config.database.max_overflow,
                pool_timeout=config.database.pool_timeout,
                pool_pre_ping=True,
                echo=config.database.echo,
            )
            logger.info("SQLAlchemy engine created for host=%s db=%s",
                        config.database.host, config.database.name)
            return engine
        except SQLAlchemyError as exc:
            logger.error("Failed to create SQLAlchemy engine: %s", exc)
            raise

    @property
    def engine(self) -> Engine:
        return self._engine

    @contextmanager
    def get_session(self) -> Generator[Session, None, None]:
        session: Session = self._session_factory()
        try:
            yield session
            session.commit()
        except SQLAlchemyError as exc:
            session.rollback()
            logger.error("Session rolled back due to error: %s", exc)
            raise
        finally:
            session.close()

    def test_connection(self) -> bool:
        try:
            with self._engine.connect() as connection:
                connection.execute(text("SELECT 1"))
            logger.info("Database connection test PASSED.")
            return True
        except OperationalError as exc:
            logger.error(
                "Database connection test FAILED - is PostgreSQL running, "
                "and are the credentials in .env correct? Details: %s", exc
            )
            return False
        except SQLAlchemyError as exc:
            logger.error("Unexpected database error during test: %s", exc)
            return False

    def dispose(self) -> None:
        self._engine.dispose()
        logger.info("Database engine disposed - all connections closed.")


db = DatabaseConnection()
