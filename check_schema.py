import sqlite3
import os

# Connect to the database
db_path = 'database.db'
if not os.path.exists(db_path):
    print(f"Database file not found at {db_path}")
    exit(1)

conn = sqlite3.connect(db_path)
cursor = conn.cursor()

# Get table info
cursor.execute("PRAGMA table_info(recipe)")
columns = cursor.fetchall()

print("Recipe table schema:")
for col in columns:
    print(f"Column: {col[1]}, Type: {col[2]}, NotNull: {col[3]}, DefaultValue: {col[4]}, PK: {col[5]}")

conn.close() 