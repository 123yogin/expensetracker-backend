import os
import psycopg2
import uuid
from dotenv import load_dotenv

load_dotenv()

INDIAN_CATEGORIES = [
    "Groceries (Sabzi Mandi)",
    "Transportation (Auto/Bus)",
    "Food & Dining",
    "Education (Fees/Books)",
    "Medical (Doctor/Medicine)",
    "Utilities (Electricity/Water)",
    "Household (Maid/Maintenance)",
    "Shopping",
    "Entertainment (Movies/OTT)",
    "Festivals/Religious",
    "Mobile/Internet Recharge",
    "Personal Care"
]

def get_database_url():
    database_url = os.environ.get('DATABASE_URL')
    if not database_url:
        raise RuntimeError("DATABASE_URL environment variable is not set")
    if database_url.startswith('postgres://'):
        database_url = database_url.replace('postgres://', 'postgresql://', 1)
    return database_url

def seed_categories():
    try:
        url = get_database_url()
        conn = psycopg2.connect(url)
        cur = conn.cursor()
        
        print("🌱 Seeding Indian Categories...")
        
        added_count = 0
        skipped_count = 0
        
        for name in INDIAN_CATEGORIES:
            # Check if exists
            cur.execute("SELECT id FROM categories WHERE name = %s", (name,))
            if cur.fetchone():
                print(f"  - Skipped '{name}' (already exists)")
                skipped_count += 1
                continue
                
            cat_id = str(uuid.uuid4())
            cur.execute(
                "INSERT INTO categories (id, name, is_active) VALUES (%s, %s, TRUE)",
                (cat_id, name)
            )
            print(f"  + Added '{name}'")
            added_count += 1
            
        conn.commit()
        print(f"\n✅ Done! Added: {added_count}, Skipped: {skipped_count}")
        
    except Exception as e:
        print(f"\n❌ Error: {e}")
        if conn:
            conn.rollback()
    finally:
        if conn:
            conn.close()

if __name__ == "__main__":
    seed_categories()
