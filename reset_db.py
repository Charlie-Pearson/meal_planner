import os
import shutil
from app import app, db

def reset_database():
    # Backup the existing database
    if os.path.exists('database.db'):
        backup_path = 'database_backup_before_reset.db'
        if os.path.exists(backup_path):
            os.remove(backup_path)
        shutil.copy2('database.db', backup_path)
        print(f"Backed up existing database to {backup_path}")
    
    # Remove the existing database file
    if os.path.exists('database.db'):
        os.remove('database.db')
    
    # Create all database tables
    with app.app_context():
        # Drop all tables
        db.drop_all()
        
        # Create all tables with the updated schema
        db.create_all()
        
        print("Created new database with updated schema")

if __name__ == '__main__':
    reset_database()
