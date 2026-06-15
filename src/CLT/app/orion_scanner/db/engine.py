"""
Database engine and session factory for Orion Scanner.

Reads the connection URL from the ``DATABASE_URL`` environment variable (or
a ``.env`` file via python-dotenv).

Example ``.env``::

    DATABASE_URL=postgresql+psycopg2://orion:secret@localhost:5432/orion_db
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from orion_scanner.utils.logger import get_logger

logger = get_logger(__name__)

# Load .env from the project root (two levels up from this file)
#_ENV_FILE = Path(__file__).resolve().parents[2] / ".env"
#load_dotenv(_ENV_FILE, override=False)


def get_engine(database_url: str | None = None):
    """
    Create and return a SQLAlchemy :class:`~sqlalchemy.engine.Engine`.

    Args:
        database_url: Explicit connection URL.  Falls back to the
                      ``DATABASE_URL`` environment variable.

    Raises:
        RuntimeError: If no connection URL is available.
    """
    url = database_url or os.environ.get("DATABASE_URL")
    if not url:
        raise RuntimeError(
            "No database URL configured.  "
            "Set DATABASE_URL in your environment or .env file."
        )

    engine = create_engine(
        url,
        pool_pre_ping=True,     # detect stale connections
        pool_size=5,
        max_overflow=10,
        echo=False,
    )
    logger.debug("Database engine created for %s", engine.url.render_as_string(hide_password=True))
    return engine


def get_session_factory(database_url: str | None = None) -> sessionmaker[Session]:
    """
    Return a :class:`~sqlalchemy.orm.sessionmaker` bound to *database_url*.

    Args:
        database_url: Passed through to :func:`get_engine`.

    Returns:
        A :class:`~sqlalchemy.orm.sessionmaker` configured for autocommit=False.
    """
    engine = get_engine(database_url)
    factory = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    return factory


def check_connection(database_url: str | None = None) -> bool:
    """
    Verify that the database is reachable.

    Returns:
        ``True`` if the connection succeeds, ``False`` otherwise.
    """
    try:
        engine = get_engine(database_url)
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception as exc:
        logger.error("Database connection check failed: %s", exc)
        return False
