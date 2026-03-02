"""
Database Module - Production-Ready Connection Pooling
=====================================================
Uses psycopg2 ThreadedConnectionPool for efficient connection reuse.
Connections are acquired from pool per-request and returned automatically.
"""

import logging
import psycopg2
import psycopg2.pool
from psycopg2.extras import RealDictCursor
from flask import g

from config import get_config

logger = logging.getLogger(__name__)

# Module-level connection pool (initialized once)
_pool: psycopg2.pool.ThreadedConnectionPool | None = None


def init_pool(app=None):
    """Initialize the connection pool. Call once at application startup."""
    global _pool
    cfg = get_config()

    if _pool is not None:
        logger.warning("Connection pool already initialized, skipping.")
        return

    try:
        _pool = psycopg2.pool.ThreadedConnectionPool(
            minconn=cfg.DB_POOL_MIN_CONN,
            maxconn=cfg.DB_POOL_MAX_CONN,
            dsn=cfg.DATABASE_URL,
            cursor_factory=RealDictCursor,
        )
        logger.info(
            "Database connection pool created (min=%d, max=%d)",
            cfg.DB_POOL_MIN_CONN,
            cfg.DB_POOL_MAX_CONN,
        )
    except psycopg2.Error as e:
        logger.critical("Failed to create database connection pool: %s", e)
        raise


def get_db():
    """
    Get a database connection from the pool.
    Connection is stored in Flask's `g` object and automatically
    returned to the pool at the end of the request.
    """
    if "db" not in g:
        if _pool is None:
            raise RuntimeError(
                "Database pool not initialized. Call init_pool() at app startup."
            )
        g.db = _pool.getconn()
    return g.db


def close_db(exception=None):
    """
    Return the connection to the pool at end of request.
    If an exception occurred, rollback first.
    """
    db = g.pop("db", None)
    if db is not None:
        if exception:
            try:
                db.rollback()
            except Exception:
                pass
        try:
            _pool.putconn(db)
        except Exception:
            pass


def shutdown_pool():
    """Close all connections in the pool. Call at application shutdown."""
    global _pool
    if _pool is not None:
        _pool.closeall()
        _pool = None
        logger.info("Database connection pool closed.")


def run_migrations():
    """
    Run SQL migration files in order.
    Each migration is idempotent (uses IF NOT EXISTS, etc.).
    """
    import os

    cfg = get_config()
    migrations_dir = os.path.join(os.path.dirname(__file__), "migrations")

    if not os.path.exists(migrations_dir):
        logger.warning("Migrations directory not found: %s", migrations_dir)
        return

    migration_files = sorted([
        f for f in os.listdir(migrations_dir)
        if f.endswith(".sql")
    ])

    if not migration_files:
        logger.info("No migration files found.")
        return

    conn = None
    try:
        conn = psycopg2.connect(cfg.DATABASE_URL)
        conn.autocommit = False

        with conn.cursor() as cursor:
            # Create migrations tracking table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS _migrations (
                    id SERIAL PRIMARY KEY,
                    filename TEXT UNIQUE NOT NULL,
                    applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            for filename in migration_files:
                # Check if already applied
                cursor.execute(
                    "SELECT 1 FROM _migrations WHERE filename = %s",
                    (filename,)
                )
                if cursor.fetchone():
                    continue

                filepath = os.path.join(migrations_dir, filename)
                logger.info("Applying migration: %s", filename)

                with open(filepath, "r") as f:
                    sql = f.read()

                cursor.execute(sql)
                cursor.execute(
                    "INSERT INTO _migrations (filename) VALUES (%s)",
                    (filename,)
                )
                logger.info("Migration applied: %s", filename)

        conn.commit()
        logger.info("All migrations completed successfully.")

    except Exception as e:
        if conn:
            conn.rollback()
        logger.error("Migration failed: %s", e)
        raise
    finally:
        if conn:
            conn.close()
