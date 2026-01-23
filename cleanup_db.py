import sqlite3
import os

DB_PATH = "backend/kakuro.db"

# Check if db exists in current dir if not found in backend/
if not os.path.exists(DB_PATH):
    if os.path.exists("kakuro.db"):
        DB_PATH = "kakuro.db"
    else:
        print("Could not find kakuro.db")
        exit(1)

print(f"Connecting to {DB_PATH}...")

try:
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Check if the temp table exists
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='_alembic_tmp_puzzle_interactions'")
    if cursor.fetchone():
        print("Found stuck table '_alembic_tmp_puzzle_interactions'. Dropping it...")
        cursor.execute("DROP TABLE _alembic_tmp_puzzle_interactions")
        conn.commit()
        print("✅ Cleanup successful.")
    else:
        print("Temporary table not found. Database looks okay.")

except Exception as e:
    print(f"❌ Error: {e}")
finally:
    if 'conn' in locals():
        conn.close()