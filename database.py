"""
Database connection and initialization module.
Handles PostgreSQL connection with connection pooling.

Production-hardened version:
- Uses Flask g context for per-request connections
- Loads credentials from environment variables
- Proper connection cleanup with teardown_appcontext
- Idempotent table creation (safe to run multiple times)
"""

import os
import psycopg2
from psycopg2.extras import RealDictCursor
from flask import g
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()


def get_database_url():
    """
    Get database URL from environment variable.
    Render provides DATABASE_URL automatically for linked databases.
    """
    database_url = os.environ.get('DATABASE_URL')
    
    if not database_url:
        raise RuntimeError("DATABASE_URL environment variable is not set")
    
    # Render uses 'postgres://' but psycopg2 requires 'postgresql://'
    if database_url.startswith('postgres://'):
        database_url = database_url.replace('postgres://', 'postgresql://', 1)
    
    return database_url


def get_db():
    """
    Get a database connection from Flask g context.
    Creates a new connection if one doesn't exist for this request.
    """
    if 'db' not in g:
        g.db = psycopg2.connect(
            get_database_url(),
            cursor_factory=RealDictCursor  # Return rows as dictionaries
        )
    return g.db


def close_db(e=None):
    """
    Close the database connection at the end of request.
    Registered as teardown_appcontext handler.
    """
    db = g.pop('db', None)
    if db is not None:
        db.close()


def init_db():
    """
    Initialize the database by creating tables if they don't exist.
    This is IDEMPOTENT - safe to run multiple times.
    
    Uses 'CREATE TABLE IF NOT EXISTS' and 'CREATE INDEX IF NOT EXISTS'
    to ensure tables are only created if missing.
    """
    # Inline schema for idempotent table creation
    schema = """
    -- Categories Table (idempotent creation)
    CREATE TABLE IF NOT EXISTS categories (
        id UUID PRIMARY KEY,
        name TEXT UNIQUE NOT NULL,
        is_active BOOLEAN DEFAULT TRUE,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );

    -- Expenses Table (idempotent creation)
    CREATE TABLE IF NOT EXISTS expenses (
        id UUID PRIMARY KEY,
        date DATE NOT NULL,
        amount DECIMAL(10,2) NOT NULL,
        category_id UUID NOT NULL REFERENCES categories(id),
        note TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP
    );

    -- Indexes for faster queries (idempotent creation)
    CREATE INDEX IF NOT EXISTS idx_expenses_date ON expenses(date);
    CREATE INDEX IF NOT EXISTS idx_expenses_category_id ON expenses(category_id);

    -- Income Table (idempotent creation)
    CREATE TABLE IF NOT EXISTS income (
        id UUID PRIMARY KEY,
        date DATE NOT NULL,
        amount DECIMAL(10,2) NOT NULL,
        source TEXT NOT NULL,
        description TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP
    );

    CREATE INDEX IF NOT EXISTS idx_income_date ON income(date);

    -- Budgets Table (idempotent creation)
    CREATE TABLE IF NOT EXISTS budgets (
        id UUID PRIMARY KEY,
        category_id UUID UNIQUE NOT NULL REFERENCES categories(id) ON DELETE CASCADE,
        amount DECIMAL(10,2) NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP
    );

    CREATE INDEX IF NOT EXISTS idx_budgets_category_id ON budgets(category_id);

    -- Recurring Expenses Table (idempotent creation)
    CREATE TABLE IF NOT EXISTS recurring_expenses (
        id UUID PRIMARY KEY,
        title TEXT NOT NULL,
        amount DECIMAL(10,2) NOT NULL,
        category_id UUID REFERENCES categories(id) ON DELETE SET NULL,
        frequency TEXT NOT NULL,
        next_date DATE NOT NULL,
        note TEXT,
        is_active BOOLEAN DEFAULT TRUE,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP
    );

    CREATE INDEX IF NOT EXISTS idx_recurring_next_date ON recurring_expenses(next_date);
    """
    
    conn = None
    try:
        conn = psycopg2.connect(get_database_url())
        with conn.cursor() as cur:
            cur.execute(schema)
        conn.commit()
        print("✅ Database tables initialized successfully (idempotent).")
    except psycopg2.OperationalError as e:
        print(f"❌ Database connection error: {e}")
        raise
    except Exception as e:
        if conn:
            conn.rollback()
        print(f"❌ Error initializing database: {e}")
        raise
    finally:
        if conn:
            conn.close()


def init_app(app):
    """
    Register database teardown with Flask app.
    Called from create_app() in app.py.
    """
    app.teardown_appcontext(close_db)
