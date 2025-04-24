import sqlite3
import os

# Connect to the database
db_path = 'database.db'
if not os.path.exists(db_path):
    print(f"Database file not found at {db_path}")
    exit(1)

conn = sqlite3.connect(db_path)
cursor = conn.cursor()

try:
    # Add method column to recipe table
    cursor.execute("ALTER TABLE recipe ADD COLUMN method TEXT")
    conn.commit()
    print("Successfully added method column to recipe table")
except sqlite3.OperationalError as e:
    if "duplicate column name" in str(e):
        print("Method column already exists")
    else:
        print(f"Error: {e}")
        conn.rollback()
finally:
    conn.close() 