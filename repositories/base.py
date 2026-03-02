"""
Base Repository
================
Provides common database operations all repositories inherit.
Handles connection management, error wrapping, and pagination.
"""

import logging
from contextlib import contextmanager

from database import get_db

logger = logging.getLogger(__name__)


class BaseRepository:
    """
    Base class for all data repositories.
    Encapsulates raw SQL and connection handling.
    """

    @staticmethod
    def _get_cursor():
        """Get a cursor from the current request's connection."""
        db = get_db()
        return db.cursor()

    @staticmethod
    def _commit():
        """Commit the current request's transaction."""
        get_db().commit()

    @staticmethod
    def _rollback():
        """Rollback the current request's transaction."""
        try:
            get_db().rollback()
        except Exception:
            pass

    @contextmanager
    def transaction(self):
        """
        Context manager for transactional operations.
        Commits on success, rolls back on exception.
        """
        try:
            yield
            self._commit()
        except Exception:
            self._rollback()
            raise

    def _execute_one(self, query: str, params: tuple = ()) -> dict | None:
        """Execute a query and return a single row as dict, or None."""
        with self._get_cursor() as cursor:
            cursor.execute(query, params)
            return cursor.fetchone()

    def _execute_all(self, query: str, params: tuple = ()) -> list[dict]:
        """Execute a query and return all rows as list of dicts."""
        with self._get_cursor() as cursor:
            cursor.execute(query, params)
            return cursor.fetchall()

    def _execute_count(self, query: str, params: tuple = ()) -> int:
        """Execute a COUNT query and return the integer count."""
        with self._get_cursor() as cursor:
            cursor.execute(query, params)
            row = cursor.fetchone()
            if row is None:
                return 0
            # RealDictCursor returns dict
            if isinstance(row, dict):
                return list(row.values())[0] or 0
            return row[0] or 0

    def _execute_modify(self, query: str, params: tuple = ()) -> int:
        """Execute an INSERT/UPDATE/DELETE and return affected row count."""
        with self._get_cursor() as cursor:
            cursor.execute(query, params)
            return cursor.rowcount

    def _execute_insert_returning(self, query: str, params: tuple = ()) -> dict | None:
        """Execute an INSERT ... RETURNING and return the inserted row."""
        with self._get_cursor() as cursor:
            cursor.execute(query, params)
            return cursor.fetchone()
