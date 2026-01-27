import psycopg2
import os
from dotenv import load_dotenv

load_dotenv()

def migrate():
    db_url = os.getenv('DATABASE_URL')
    if not db_url:
        print("DATABASE_URL not found in .env")
        return

    try:
        conn = psycopg2.connect(db_url)
        conn.autocommit = True
        with conn.cursor() as cursor:
            print("Adding is_split column...")
            cursor.execute("ALTER TABLE expenses ADD COLUMN IF NOT EXISTS is_split BOOLEAN DEFAULT FALSE;")
            print("Adding split_amount column...")
            cursor.execute("ALTER TABLE expenses ADD COLUMN IF NOT EXISTS split_amount DECIMAL(10,2) DEFAULT 0.00;")
            print("Adding split_with column...")
            cursor.execute("ALTER TABLE expenses ADD COLUMN IF NOT EXISTS split_with TEXT;")
            print("Migration successful!")
        conn.close()
    except Exception as e:
        print(f"Migration failed: {e}")

if __name__ == "__main__":
    migrate()
