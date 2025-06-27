import os
from datetime import datetime, timezone
from app import app, db
from app import (
    User, Account, AccountUser, Invitation, Recipe, Ingredient, 
    RecipeIngredient, PantryItem, Aisle, LockedMeal, AccountSettings, 
    ShoppingListItem
)


NEW_DB_FILENAME = "database.db"  # or dynamically name it like f"db_{datetime.now().strftime('%Y%m%d')}.db"

def create_new_database(drop_existing=True, create_sample_data=True):
    # Set new database URI
    db_path = os.path.abspath(NEW_DB_FILENAME)
    app.config['SQLALCHEMY_DATABASE_URI'] = f"sqlite:///{db_path}"
    
    # Re-initialize the SQLAlchemy object with new config
    db.engine.dispose()
    db.session.remove()
    db.reflect()
    
    with app.app_context():
        # Delete old file if it exists
        if os.path.exists(db_path):
            os.remove(db_path)
            print(f"Old database file '{NEW_DB_FILENAME}' removed.")
        
        # Create all tables
        print("Creating new tables...")
        db.create_all()
        
        if create_sample_data:
            print("Creating sample data...")
            account = Account(name="Default Account")
            db.session.add(account)
            
            admin = User(
                email="admin@example.com",
                name="Admin User"
            )
            admin.set_password("admin123")
            db.session.add(admin)
            
            account_user = AccountUser(
                account=account,
                user=admin,
                role='admin'
            )
            db.session.add(account_user)
            
            settings = AccountSettings(
                account=account,
                num_people=4,
                meal_plan_start_day="Monday",
                meal_plan_duration=7
            )
            db.session.add(settings)
            
            aisles = [
                Aisle(name="Produce"),
                Aisle(name="Dairy"),
                Aisle(name="Meat"),
                Aisle(name="Bakery"),
                Aisle(name="Pantry")
            ]
            db.session.add_all(aisles)
            
            ingredients = [
                Ingredient(name="Chicken breast", unit="g", aisle=aisles[2]),
                Ingredient(name="Rice", unit="g", aisle=aisles[4]),
                Ingredient(name="Tomato", unit="each", aisle=aisles[0]),
                Ingredient(name="Onion", unit="each", aisle=aisles[0]),
                Ingredient(name="Milk", unit="ml", aisle=aisles[1])
            ]
            db.session.add_all(ingredients)
            
            recipe = Recipe(
                name="Chicken and Rice",
                method="1. Cook chicken\n2. Cook rice\n3. Mix together",
                servings=4,
                is_dinner=True,
                account_id=account.id,
                created_by=admin.id
            )
            db.session.add(recipe)
            
            recipe_ingredients = [
                RecipeIngredient(recipe=recipe, ingredient=ingredients[0], quantity="500"),
                RecipeIngredient(recipe=recipe, ingredient=ingredients[1], quantity="300")
            ]
            db.session.add_all(recipe_ingredients)
            
            db.session.commit()
            print("Sample data created successfully!")
        
        print(f"Database setup complete at '{NEW_DB_FILENAME}'!")

if __name__ == '__main__':
    confirm = input(f"WARNING: This will create a new database '{NEW_DB_FILENAME}' and overwrite any existing one. Continue? (y/n): ")
    if confirm.lower() == 'y':
        create_new_database()
    else:
        print("Operation cancelled.")
