from app import app, db
from app.models import Recipe, Ingredient, Aisle, RecipeIngredient, User, Account
from datetime import datetime, timezone

def add_recipe(recipe_data, user_email="charlie12pearson@gmail.com", account_name="charlies"):
    """
    Generic function to add a recipe to the database.
    
    Args:
        recipe_data (dict): Dictionary containing recipe information with the following structure:
            {
                'name': str,                 # Recipe name
                'servings': int,             # Number of servings
                'is_breakfast': bool,        # Is it a breakfast recipe?
                'is_lunch': bool,            # Is it a lunch recipe?
                'is_dinner': bool,           # Is it a dinner recipe?
                'source_link': str,          # URL to the recipe source
                'method': str,               # Cooking instructions
                'ingredients': [             # List of ingredient dictionaries
                    {
                        'name': str,         # Ingredient name
                        'quantity': str,     # Quantity (as string to support fractions)
                        'unit': str,         # Unit of measurement
                        'notes': str,        # Any additional notes
                        'aisle': str         # Aisle/category
                    },
                    ...
                ]
            }
        user_email (str): Email of the user adding the recipe
        account_name (str): Name of the account to associate with the recipe
    """
    with app.app_context():
        # Check if recipe already exists
        if Recipe.query.filter_by(name=recipe_data['name']).first():
            print(f"Recipe '{recipe_data['name']}' already exists in the database.")
            return False
            
        try:
            # Get or create user and account
            user = User.query.filter_by(email=user_email).first()
            if not user:
                print(f"User with email {user_email} not found.")
                return False
                
            account = Account.query.filter_by(name=account_name).first()
            if not account:
                print(f"Account '{account_name}' not found.")
                return False
            
            # Create recipe
            recipe = Recipe(
                name=recipe_data['name'],
                servings=recipe_data['servings'],
                is_breakfast=recipe_data.get('is_breakfast', False),
                is_lunch=recipe_data.get('is_lunch', True),
                is_dinner=recipe_data.get('is_dinner', True),
                source_link=recipe_data.get('source_link', ''),
                method=recipe_data['method'],
                account_id=account.id,
                created_by=user.id
            )
            db.session.add(recipe)
            db.session.flush()  # Get the recipe ID
            
            # Process ingredients
            for item in recipe_data['ingredients']:
                # Get or create aisle
                aisle_name = item.get('aisle', 'Miscellaneous')
                aisle = Aisle.query.filter_by(name=aisle_name).first()
                if not aisle:
                    aisle = Aisle(name=aisle_name)
                    db.session.add(aisle)
                    db.session.flush()
                
                # Get or create ingredient
                ingredient = Ingredient.query.filter(
                    db.func.lower(Ingredient.name) == item['name'].lower()
                ).first()
                
                if not ingredient:
                    ingredient = Ingredient(
                        name=item['name'].lower(),
                        unit=item.get('unit', ''),
                        aisle_id=aisle.id
                    )
                    db.session.add(ingredient)
                    db.session.flush()
                
                # Create recipe ingredient association
                recipe_ingredient = RecipeIngredient(
                    recipe_id=recipe.id,
                    ingredient_id=ingredient.id,
                    quantity=str(item['quantity']),
                    unit=item.get('unit', ''),
                    notes=item.get('notes', '')
                )
                db.session.add(recipe_ingredient)
            
            db.session.commit()
            print(f"✅ Successfully added recipe: {recipe_data['name']} (ID: {recipe.id})")
            return True
            
        except Exception as e:
            db.session.rollback()
            print(f"❌ Error adding recipe: {str(e)}")
            import traceback
            traceback.print_exc()
            return False

def add_saag_aloo():
    """Add Saag Aloo recipe to the database"""
    saag_aloo = {
        'name': 'Saag Aloo',
        'servings': 4,
        'is_breakfast': False,
        'is_lunch': True,
        'is_dinner': True,
        'source_link': 'https://rainbowplantlife.com/saag-aloo/',
        'method': """1. Heat oil in a large pan over medium heat. Add cumin seeds and let them sizzle for 30 seconds.
2. Add onion and cook until golden brown, about 5 minutes.
3. Add garlic, ginger, and green chili. Cook for 1 minute until fragrant.
4. Stir in turmeric, coriander, garam masala, and chili powder. Cook for 30 seconds.
5. Add potatoes and stir to coat with spices. Cook for 2 minutes.
6. Cover and simmer for 15 minutes or until potatoes are tender, adding a splash of water if needed.
7. Stir in spinach and cook until wilted, about 3 minutes.
8. Garnish with fresh coriander before serving.""",
        'ingredients': [
            {'name': 'cumin seed', 'quantity': '1', 'unit': 'tsp', 'aisle': 'Spices'},
            {'name': 'onion', 'quantity': '1', 'unit': 'large', 'aisle': 'Produce', 'notes': 'finely chopped'},
            {'name': 'garlic clove', 'quantity': '3', 'unit': '', 'aisle': 'Produce', 'notes': 'minced'},
            {'name': 'ginger', 'quantity': '1', 'unit': 'tbsp', 'aisle': 'Produce', 'notes': 'grated'},
            {'name': 'green chili', 'quantity': '1', 'unit': '', 'aisle': 'Produce', 'notes': 'finely chopped'},
            {'name': 'turmeric', 'quantity': '1', 'unit': 'tsp', 'aisle': 'Spices'},
            {'name': 'coriander', 'quantity': '1', 'unit': 'tsp', 'aisle': 'Spices', 'notes': 'ground'},
            {'name': 'garam masala', 'quantity': '1', 'unit': 'tsp', 'aisle': 'Spices'},
            {'name': 'chili powder', 'quantity': '0.5', 'unit': 'tsp', 'aisle': 'Spices'},
            {'name': 'potato', 'quantity': '500', 'unit': 'g', 'aisle': 'Produce', 'notes': 'peeled and cubed'},
            {'name': 'spinach', 'quantity': '250', 'unit': 'g', 'aisle': 'Produce', 'notes': 'fresh, chopped'},
            {'name': 'coriander', 'quantity': '2', 'unit': 'tbsp', 'aisle': 'Produce', 'notes': 'fresh, chopped'}
        ]
    }
    
    return add_recipe(saag_aloo)

if __name__ == "__main__":
    # Example usage:
    # 1. Add Saag Aloo
    add_saag_aloo()
    
    # 2. Example of how to add another recipe:
    """
    my_recipe = {
        'name': 'My Recipe',
        'servings': 4,
        'is_breakfast': False,
        'is_lunch': True,
        'is_dinner': True,
        'source_link': 'https://example.com/recipe',
        'method': 'Instructions go here...',
        'ingredients': [
            {'name': 'ingredient1', 'quantity': '1', 'unit': 'cup', 'aisle': 'Baking', 'notes': 'optional'},
            # ... more ingredients
        ]
    }
    add_recipe(my_recipe)
    """
