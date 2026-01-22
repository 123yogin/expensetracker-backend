"""
Database connection and initialization module.
Handles SQLite connection with foreign key support.

Production-hardened version:
- Uses Flask g context for per-request connections
- Ensures PRAGMA foreign_keys = ON on every connection
- Proper connection cleanup with teardown_appcontext
"""

import sqlite3
import os
from flask import g, current_app


DATABASE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'expense_tracker.db')


def get_db():
    """
    Get a database connection from Flask g context.
    Creates a new connection if one doesn't exist for this request.
    
    IMPORTANT: This ensures a single connection per request,
    and foreign keys are enabled on every new connection.
    """
    if 'db' not in g:
        g.db = sqlite3.connect(DATABASE_PATH)
        g.db.row_factory = sqlite3.Row  # Return rows as dictionaries
        # CRITICAL: Enable foreign key constraints on EVERY connection
        g.db.execute("PRAGMA foreign_keys = ON")
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
    Initialize the database by executing the schema.sql file.
    Creates tables and indexes if they don't exist.
    
    NOTE: This runs outside of request context, so we create
    a standalone connection here.
    """
    schema_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'schema.sql')
    
    conn = sqlite3.connect(DATABASE_PATH)
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        with open(schema_path, 'r') as f:
            schema = f.read()
        conn.executescript(schema)
        conn.commit()
        print("Database initialized successfully.")
    except Exception as e:
        print(f"Error initializing database: {e}")
        raise
    finally:
        conn.close()


def init_app(app):
    """
    Register database teardown with Flask app.
    Called from create_app() in app.py.
    """
    app.teardown_appcontext(close_db)
