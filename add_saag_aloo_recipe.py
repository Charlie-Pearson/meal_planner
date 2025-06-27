from app import app, db
from app.models import Recipe, Ingredient, RecipeIngredient, Aisle, User, Account
from datetime import datetime

def add_saag_aloo_recipe():
    with app.app_context():
        try:
            # Check if recipe already exists
            if Recipe.query.filter_by(name='Saag Aloo').first():
                print("Recipe 'Saag Aloo' already exists in the database.")
                return

            # Get the admin user and account
            user = User.query.filter_by(email='charlie12pearson@gmail.com').first()
            if not user:
                print("Admin user not found. Please create the admin user first.")
                return
                
            account = Account.query.filter_by(id=2).first()  # Assuming account ID 2 is 'charlies'
            if not account:
                print("Account 'charlies' not found. Please create the account first.")
                return

            # Create the recipe
            recipe = Recipe(
                name='Saag Aloo',
                method="""1. Heat oil in a large pan over medium heat. Add cumin seeds and let them sizzle for 30 seconds.
2. Add onion and cook until golden brown, about 5 minutes.
3. Add garlic, ginger, and green chili. Cook for 1 minute until fragrant.
4. Stir in turmeric, coriander, garam masala, and chili powder. Cook for 30 seconds.
5. Add potatoes and stir to coat with spices. Cook for 2 minutes.
6. Cover and simmer for 15 minutes or until potatoes are tender, adding a splash of water if needed.
7. Stir in spinach and cook until wilted, about 3 minutes.
8. Garnish with fresh coriander before serving.""",
                servings=4,
                is_breakfast=False,
                is_lunch=True,
                is_dinner=True,
                source_link='https://rainbowplantlife.com/saag-aloo/',
                account_id=account.id,
                created_by=user.id
            )
            db.session.add(recipe)
            db.session.flush()  # Get the recipe ID

            # Define ingredients with their details
            ingredients = [
                {'name': 'cumin seed', 'quantity': 1, 'unit': 'tsp', 'aisle': 'Spices'},
                {'name': 'onion', 'quantity': 1, 'unit': 'large', 'aisle': 'Produce'},
                {'name': 'garlic clove', 'quantity': 3, 'unit': '', 'aisle': 'Produce'},
                {'name': 'ginger', 'quantity': 1, 'unit': 'tbsp', 'notes': 'grated', 'aisle': 'Produce'},
                {'name': 'green chili', 'quantity': 1, 'unit': '', 'aisle': 'Produce'},
                {'name': 'turmeric', 'quantity': 1, 'unit': 'tsp', 'aisle': 'Spices'},
                {'name': 'coriander', 'quantity': 1, 'unit': 'tsp', 'notes': 'ground', 'aisle': 'Spices'},
                {'name': 'garam masala', 'quantity': 1, 'unit': 'tsp', 'aisle': 'Spices'},
                {'name': 'chili powder', 'quantity': 0.5, 'unit': 'tsp', 'aisle': 'Spices'},
                {'name': 'potato', 'quantity': 500, 'unit': 'g', 'notes': 'peeled and cubed', 'aisle': 'Produce'},
                {'name': 'spinach', 'quantity': 250, 'unit': 'g', 'notes': 'fresh, chopped', 'aisle': 'Produce'},
                {'name': 'coriander', 'quantity': 2, 'unit': 'tbsp', 'notes': 'fresh, chopped', 'aisle': 'Produce'}
            ]

            # Add ingredients to the recipe
            for item in ingredients:
                # Get or create ingredient
                ingredient = Ingredient.query.filter(
                    db.func.lower(Ingredient.name) == item['name'].lower()
                ).first()
                
                if not ingredient:
                    # Get or create aisle
                    aisle = Aisle.query.filter(
                        db.func.lower(Aisle.name) == item['aisle'].lower()
                    ).first()
                    
                    if not aisle:
                        aisle = Aisle(name=item['aisle'])
                        db.session.add(aisle)
                        db.session.flush()
                    
                    # Create new ingredient
                    ingredient = Ingredient(
                        name=item['name'].lower(),
                        unit=item.get('unit', ''),
                        aisle_id=aisle.id
                    )
                    db.session.add(ingredient)
                    db.session.flush()
                
                # Create recipe ingredient
                recipe_ingredient = RecipeIngredient(
                    recipe_id=recipe.id,
                    ingredient_id=ingredient.id,
                    quantity=str(item['quantity']),
                    unit=item.get('unit', ''),
                    notes=item.get('notes', '')
                )
                db.session.add(recipe_ingredient)
            
            # Commit all changes
            db.session.commit()
            print(f"Successfully added recipe: Saag Aloo (ID: {recipe.id})")
            
        except Exception as e:
            db.session.rollback()
            print(f"Error adding recipe: {str(e)}")
            raise

if __name__ == "__main__":
    add_saag_aloo_recipe()
