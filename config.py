"""
config.py

WHY THIS FILE EXISTS:
    Every module in this project (database, dashboard, ai, ml, reports)
    needs access to the same settings - DB credentials, API keys, file
    paths, etc. Instead of scattering os.getenv() calls throughout the
    codebase, all configuration is loaded ONCE here and exposed through
    a single Config class.

WHERE THIS FILE BELONGS:
    Project root: AI_Business_Analytics_Assistant/config.py
"""

import os
import logging
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote_plus

from dotenv import load_dotenv

load_dotenv()

BASE_DIR: Path = Path(__file__).resolve().parent


@dataclass(frozen=True)
class DatabaseConfig:
    """Holds all PostgreSQL connection settings."""

    host: str = os.getenv("DB_HOST", "localhost").strip()
    port: int = int(os.getenv("DB_PORT", "5432"))
    name: str = os.getenv("DB_NAME", "bi_assistant_db").strip()
    user: str = os.getenv("DB_USER", "postgres").strip()
    password: str = os.getenv("DB_PASSWORD", "")

    pool_size: int = int(os.getenv("DB_POOL_SIZE", "5"))
    max_overflow: int = int(os.getenv("DB_MAX_OVERFLOW", "10"))
    pool_timeout: int = int(os.getenv("DB_POOL_TIMEOUT", "30"))
    echo: bool = os.getenv("DB_ECHO", "False").lower() == "true"

    @property
    def connection_url(self) -> str:
        """
        Builds the SQLAlchemy connection URL via pg8000 (pure-Python
        driver - no C++ compiler needed, safe on Windows). user/password
        are URL-encoded with quote_plus() so special characters (@, :, /)
        in a password can never corrupt the URL's host/port parsing.
        """
        safe_user = quote_plus(self.user)
        safe_password = quote_plus(self.password)
        return (
            f"postgresql+pg8000://{safe_user}:{safe_password}"
            f"@{self.host}:{self.port}/{self.name}"
        )


@dataclass(frozen=True)
class AppConfig:
    """General application-level settings shared across every module."""

    app_name: str = "AI Business Analytics Assistant"
    environment: str = os.getenv("APP_ENV", "development")
    debug: bool = os.getenv("APP_DEBUG", "True").lower() == "true"
    log_level: str = os.getenv("LOG_LEVEL", "INFO")

    data_dir: Path = BASE_DIR / "data"
    logs_dir: Path = BASE_DIR / "logs"
    reports_dir: Path = BASE_DIR / "reports" / "generated"
    charts_dir: Path = BASE_DIR / "charts" / "generated"


class Config:
    """Single entry point for all configuration in the project."""

    def __init__(self) -> None:
        self.database: DatabaseConfig = DatabaseConfig()
        self.app: AppConfig = AppConfig()
        self._ensure_directories()
        self._validate()

    def _ensure_directories(self) -> None:
        for directory in (
            self.app.data_dir, self.app.logs_dir,
            self.app.reports_dir, self.app.charts_dir,
        ):
            directory.mkdir(parents=True, exist_ok=True)

    def _validate(self) -> None:
        if not self.database.password:
            logging.getLogger(__name__).warning(
                "DB_PASSWORD is not set in .env - the database connection "
                "will likely fail until you set it."
            )
        if self.database.port <= 0:
            raise ValueError(f"Invalid DB_PORT: {self.database.port}")
        if "@" in self.database.host:
            raise ValueError(
                f"DB_HOST looks malformed: '{self.database.host}'. "
                "DB_HOST should be just the hostname (e.g. 'localhost'), "
                "not 'username@hostname'. Put the username in DB_USER "
                "instead - check your .env file."
            )


config = Config()
