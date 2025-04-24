import sqlite3
import os

# Connect to the database
db_path = 'database.db'
if not os.path.exists(db_path):
    print(f"Database file not found at {db_path}")
    exit(1)

conn = sqlite3.connect(db_path)
cursor = conn.cursor()

# List of columns to add with their types
columns = [
    ("servings", "INTEGER"),
    ("is_breakfast", "BOOLEAN DEFAULT 0"),
    ("is_lunch", "BOOLEAN DEFAULT 0"),
    ("is_dinner", "BOOLEAN DEFAULT 0"),
    ("account_id", "INTEGER"),
    ("is_public", "BOOLEAN DEFAULT 0"),
    ("created_by", "INTEGER"),
    ("updated_at", "DATETIME")
]

for column_name, column_type in columns:
    try:
        cursor.execute(f"ALTER TABLE recipe ADD COLUMN {column_name} {column_type}")
        print(f"Successfully added {column_name} column")
    except sqlite3.OperationalError as e:
        if "duplicate column name" in str(e):
            print(f"Column {column_name} already exists")
        else:
            print(f"Error adding {column_name}: {e}")
            conn.rollback()

try:
    # Add foreign key constraints
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS recipe_new (
            id INTEGER PRIMARY KEY,
            name VARCHAR(100) NOT NULL,
            source_link VARCHAR(200),
            method TEXT,
            meal_type VARCHAR(20) NOT NULL,
            meal_repeat_interval INTEGER,
            created_at DATETIME NOT NULL,
            servings INTEGER,
            is_breakfast BOOLEAN DEFAULT 0,
            is_lunch BOOLEAN DEFAULT 0,
            is_dinner BOOLEAN DEFAULT 0,
            account_id INTEGER REFERENCES account(id),
            is_public BOOLEAN DEFAULT 0,
            created_by INTEGER REFERENCES user(id),
            updated_at DATETIME
        )
    """)
    
    # Copy data to new table
    cursor.execute("""
        INSERT INTO recipe_new 
        SELECT id, name, source_link, method, meal_type, meal_repeat_interval, created_at,
               servings, is_breakfast, is_lunch, is_dinner, account_id, is_public, 
               created_by, updated_at
        FROM recipe
    """)
    
    # Drop old table and rename new one
    cursor.execute("DROP TABLE recipe")
    cursor.execute("ALTER TABLE recipe_new RENAME TO recipe")
    
    print("Successfully recreated table with proper constraints")
    
except sqlite3.OperationalError as e:
    print(f"Error recreating table: {e}")
    conn.rollback()

conn.commit()
conn.close()
print("Database update completed") 