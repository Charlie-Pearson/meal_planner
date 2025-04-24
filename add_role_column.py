import sqlite3

def add_role_column():
    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()
    
    try:
        # Check if column exists
        cursor.execute("PRAGMA table_info(invitation)")
        columns = cursor.fetchall()
        column_names = [column[1] for column in columns]
        
        if 'role' not in column_names:
            # Create new table with desired schema
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS invitation_new (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    account_id INTEGER NOT NULL,
                    email TEXT NOT NULL,
                    token TEXT NOT NULL,
                    created_by INTEGER NOT NULL,
                    created_at TIMESTAMP NOT NULL,
                    expires_at TIMESTAMP NOT NULL,
                    is_used BOOLEAN NOT NULL DEFAULT 0,
                    role TEXT NOT NULL DEFAULT 'user',
                    FOREIGN KEY (account_id) REFERENCES account (id),
                    FOREIGN KEY (created_by) REFERENCES user (id)
                )
            ''')
            
            # Copy data from old table to new table
            cursor.execute('''
                INSERT INTO invitation_new (
                    id, account_id, email, token, created_by, 
                    created_at, expires_at, is_used
                )
                SELECT id, account_id, email, token, created_by, 
                       created_at, expires_at, is_used
                FROM invitation
            ''')
            
            # Drop old table
            cursor.execute('DROP TABLE invitation')
            
            # Rename new table to original name
            cursor.execute('ALTER TABLE invitation_new RENAME TO invitation')
            
            print("Successfully added role column to invitation table")
        else:
            print("Role column already exists")
            
        conn.commit()
        
    except Exception as e:
        print(f"An error occurred: {str(e)}")
        conn.rollback()
    finally:
        conn.close()

if __name__ == "__main__":
    add_role_column() 