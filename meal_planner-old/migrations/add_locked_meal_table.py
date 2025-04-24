from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
import os
import sys

# Add the parent directory to the path so we can import app
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app import app, db, LockedMeal

def upgrade():
    """Create the LockedMeal table."""
    # Create the table
    LockedMeal.__table__.create(db.engine)
    
    # Get existing session data
    with app.app_context():
        # Get the session data from the database
        # This is a simplified approach - in a real app, you might need to
        # handle this differently depending on how session data is stored
        from flask import session
        locked_meals = session.get('locked_meals', {})
        
        # Convert session locks to database records
        for slot_id, lock_info in locked_meals.items():
            try:
                day, meal_type = slot_id.split('_')
                
                # Create a new LockedMeal record
                new_lock = LockedMeal(
                    day=day,
                    meal_type=meal_type,
                    recipe_id=lock_info.get('recipe_id'),
                    manual_text=lock_info.get('text'),
                    is_manual=lock_info.get('manual', False),
                    is_default=lock_info.get('default', False)
                )
                
                db.session.add(new_lock)
            except Exception as e:
                print(f"Error migrating lock for {slot_id}: {e}")
        
        # Commit the changes
        db.session.commit()

def downgrade():
    """Drop the LockedMeal table."""
    LockedMeal.__table__.drop(db.engine)

if __name__ == '__main__':
    # This allows running the script directly
    with app.app_context():
        upgrade()
        print("Migration completed successfully.") 