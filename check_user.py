import sqlite3

def check_user():
    # Connect to the SQLite database
    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()
    
    # Check the user
    cursor.execute("""
        SELECT u.id, u.email, u.is_admin, a.name as account_name, au.role
        FROM user u
        LEFT JOIN account_user au ON u.id = au.user_id
        LEFT JOIN account a ON au.account_id = a.id
        WHERE u.email = 'charlie12pearson@gmail.com'
    """)
    
    user = cursor.fetchone()
    
    if user:
        print(f"\nUser found:")
        print(f"ID: {user[0]}")
        print(f"Email: {user[1]}")
        print(f"Is Admin: {bool(user[2])}")
        print(f"Account: {user[3] if user[3] else 'None'}")
        print(f"Role: {user[4] if user[4] else 'None'}")
    else:
        print("User not found with email: charlie12pearson@gmail.com")
    
    # Check all accounts
    print("\nAll accounts:")
    cursor.execute("SELECT id, name FROM account")
    for account in cursor.fetchall():
        print(f"ID: {account[0]}, Name: {account[1]}")
    
    conn.close()

if __name__ == '__main__':
    check_user()
