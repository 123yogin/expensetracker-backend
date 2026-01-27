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
    Initialize the database by running all pending migrations.
    This is IDEMPOTENT - safe to run multiple times.
    
    Tracks applied migrations in a 'schema_migrations' table.
    """
    conn = None
    try:
        conn = psycopg2.connect(get_database_url())
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            # 1. Create migrations tracker table if it doesn't exist
            cur.execute("""
                CREATE TABLE IF NOT EXISTS schema_migrations (
                    id SERIAL PRIMARY KEY,
                    filename TEXT UNIQUE NOT NULL,
                    applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)
            
            # 2. Get list of already applied migrations
            cur.execute("SELECT filename FROM schema_migrations")
            rows = cur.fetchall()
            
            # Handle both tuple and dict responses
            applied_migrations = set()
            for row in rows:
                if isinstance(row, dict):
                    applied_migrations.add(row['filename'])
                elif isinstance(row, (tuple, list)) and len(row) > 0:
                    applied_migrations.add(row[0])
            
            # 3. Read migration files from folder
            migrations_dir = os.path.join(os.path.dirname(__file__), 'migrations')
            if not os.path.exists(migrations_dir):
                print(f"⚠️ Migrations directory not found: {migrations_dir}")
                return

            migration_files = sorted([f for f in os.listdir(migrations_dir) if f.endswith('.sql')])
            
            # 4. Apply pending migrations
            applied_count = 0
            for filename in migration_files:
                if filename not in applied_migrations:
                    print(f"🚀 Applying migration: {filename}...")
                    with open(os.path.join(migrations_dir, filename), 'r') as f:
                        sql = f.read()
                        if sql.strip():
                            cur.execute(sql)
                    
                    cur.execute(
                        "INSERT INTO schema_migrations (filename) VALUES (%s)",
                        (filename,)
                    )
                    applied_count += 1
            
            conn.commit()
            if applied_count > 0:
                print(f"✅ Successfully applied {applied_count} new migrations.")
            else:
                print("✅ Database is up to date. No new migrations applied.")
                
    except psycopg2.OperationalError as e:
        print(f"❌ Database connection error: {e}")
        print("💡 Make sure PostgreSQL is running and the database exists.")
        print("💡 Check your DATABASE_URL in the .env file.")
        raise
    except Exception as e:
        if conn:
            conn.rollback()
        print(f"❌ Error during database migration: {e}")
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
