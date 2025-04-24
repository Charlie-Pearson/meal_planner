from app import app, db
from datetime import datetime

def migrate_database():
    """Add updated_at columns to tables that need them."""
    with app.app_context():
        # Check if the column exists in ShoppingListItem
        inspector = db.inspect(db.engine)
        shopping_list_columns = [col['name'] for col in inspector.get_columns('shopping_list_item')]
        
        if 'updated_at' not in shopping_list_columns:
            print("Adding updated_at column to shopping_list_item table...")
            # SQLite doesn't allow non-constant defaults, so we add the column without a default
            db.engine.execute('ALTER TABLE shopping_list_item ADD COLUMN updated_at DATETIME')
            
            # Update existing records with current timestamp
            db.engine.execute('UPDATE shopping_list_item SET updated_at = ?', (datetime.utcnow(),))
            print("Updated existing shopping_list_item records with current timestamp.")
        
        # Check if the column exists in Ingredient
        ingredient_columns = [col['name'] for col in inspector.get_columns('ingredient')]
        
        if 'updated_at' not in ingredient_columns:
            print("Adding updated_at column to ingredient table...")
            # SQLite doesn't allow non-constant defaults, so we add the column without a default
            db.engine.execute('ALTER TABLE ingredient ADD COLUMN updated_at DATETIME')
            
            # Update existing records with current timestamp
            db.engine.execute('UPDATE ingredient SET updated_at = ?', (datetime.utcnow(),))
            print("Updated existing ingredient records with current timestamp.")
        
        # Check if the column exists in PantryItem
        pantry_item_columns = [col['name'] for col in inspector.get_columns('pantry_item')]
        
        if 'updated_at' not in pantry_item_columns:
            print("Adding updated_at column to pantry_item table...")
            # SQLite doesn't allow non-constant defaults, so we add the column without a default
            db.engine.execute('ALTER TABLE pantry_item ADD COLUMN updated_at DATETIME')
            
            # Update existing records with current timestamp
            db.engine.execute('UPDATE pantry_item SET updated_at = ?', (datetime.utcnow(),))
            print("Updated existing pantry_item records with current timestamp.")
        
        print("Migration completed successfully!")

if __name__ == "__main__":
    migrate_database() 