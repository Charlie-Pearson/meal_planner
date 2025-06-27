import sqlite3

def update_user():
    # Connect to the database
    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()
    
    try:
        # Update user to be admin
        cursor.execute("""
            UPDATE user 
            SET is_admin = 1 
            WHERE email = 'charlie12pearson@gmail.com'
        """)
        
        # Check if account association exists
        cursor.execute("""
            SELECT id FROM user WHERE email = 'charlie12pearson@gmail.com'
        """)
        user_id = cursor.fetchone()[0]
        
        cursor.execute("""
            SELECT * FROM account_user 
            WHERE user_id = ? AND account_id = 2
        """, (user_id,))
        
        if cursor.fetchone() is None:
            # Add user to account
            cursor.execute("""
                INSERT INTO account_user (user_id, account_id, role)
                VALUES (?, 2, 'admin')
            """, (user_id,))
        else:
            # Update existing association
            cursor.execute("""
                UPDATE account_user 
                SET role = 'admin' 
                WHERE user_id = ? AND account_id = 2
            """, (user_id,))
        
        conn.commit()
        print("User updated successfully!")
        
        # Verify the update
        cursor.execute("""
            SELECT u.email, u.is_admin, a.name, au.role
            FROM user u
            LEFT JOIN account_user au ON u.id = au.user_id
            LEFT JOIN account a ON au.account_id = a.id
            WHERE u.email = 'charlie12pearson@gmail.com'
        """)
        
        result = cursor.fetchone()
        if result:
            print("\nVerification:")
            print(f"Email: {result[0]}")
            print(f"Is Admin: {bool(result[1])}")
            print(f"Account: {result[2] if result[2] else 'None'}")
            print(f"Role: {result[3] if result[3] else 'None'}")
        
    except Exception as e:
        print(f"Error: {e}")
        conn.rollback()
    finally:
        conn.close()

if __name__ == '__main__':
    update_user()
