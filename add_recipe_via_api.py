from app import create_app, db
from app.models import User, Recipe, Ingredient, RecipeIngredient
import json

def add_saag_aloo():
    app = create_app()
    
    with app.app_context():
        # Create a test user if needed
        user = User.query.filter_by(email='charlie12pearson@gmail.com').first()
        if not user:
            print("User not found. Please log in first.")
            return
        
        # Check if recipe already exists
        if Recipe.query.filter_by(name='Saag Aloo').first():
            print("Recipe 'Saag Aloo' already exists in the database.")
            return
        
        # Define the recipe data
        recipe_data = {
            'name': 'Saag Aloo',
            'servings': 4,
            'is_breakfast': False,
            'is_lunch': True,
            'is_dinner': True,
            'method': """1. Heat oil in a large pan over medium heat. Add cumin seeds and let them sizzle for 30 seconds.
2. Add onion and cook until golden brown, about 5 minutes.
3. Add garlic, ginger, and green chili. Cook for 1 minute until fragrant.
4. Stir in turmeric, coriander, garam masala, and chili powder. Cook for 30 seconds.
5. Add potatoes and stir to coat with spices. Cook for 2 minutes.
6. Cover and simmer for 15 minutes or until potatoes are tender, adding a splash of water if needed.
7. Stir in spinach and cook until wilted, about 3 minutes.
8. Garnish with fresh coriander before serving.""",
            'source_link': 'https://rainbowplantlife.com/saag-aloo/',
            'ingredients': [
                {'name': 'cumin seed', 'quantity': 1, 'unit': 'tsp', 'notes': ''},
                {'name': 'onion', 'quantity': 1, 'unit': 'large', 'notes': 'finely chopped'},
                {'name': 'garlic clove', 'quantity': 3, 'unit': '', 'notes': 'minced'},
                {'name': 'ginger', 'quantity': 1, 'unit': 'tbsp', 'notes': 'grated'},
                {'name': 'green chili', 'quantity': 1, 'unit': '', 'notes': 'finely chopped'},
                {'name': 'turmeric', 'quantity': 1, 'unit': 'tsp', 'notes': 'ground'},
                {'name': 'coriander', 'quantity': 1, 'unit': 'tsp', 'notes': 'ground'},
                {'name': 'garam masala', 'quantity': 1, 'unit': 'tsp', 'notes': ''},
                {'name': 'chili powder', 'quantity': 0.5, 'unit': 'tsp', 'notes': ''},
                {'name': 'potato', 'quantity': 500, 'unit': 'g', 'notes': 'peeled and cubed'},
                {'name': 'spinach', 'quantity': 250, 'unit': 'g', 'notes': 'fresh, chopped'},
                {'name': 'coriander', 'quantity': 2, 'unit': 'tbsp', 'notes': 'fresh, chopped'}
            ]
        }
        
        try:
            # Create the recipe
            recipe = Recipe(
                name=recipe_data['name'],
                method=recipe_data['method'],
                servings=recipe_data['servings'],
                is_breakfast=recipe_data['is_breakfast'],
                is_lunch=recipe_data['is_lunch'],
                is_dinner=recipe_data['is_dinner'],
                source_link=recipe_data['source_link'],
                account_id=user.account_id
            )
            db.session.add(recipe)
            db.session.flush()  # Get the recipe ID
            
            # Add ingredients
            for ing_data in recipe_data['ingredients']:
                # Get or create ingredient
                ingredient = Ingredient.query.filter_by(name=ing_data['name'].lower()).first()
                if not ingredient:
                    ingredient = Ingredient(name=ing_data['name'].lower())
                    db.session.add(ingredient)
                    db.session.flush()
                
                # Create recipe ingredient association
                recipe_ingredient = RecipeIngredient(
                    recipe_id=recipe.id,
                    ingredient_id=ingredient.id,
                    quantity=ing_data['quantity'],
                    unit=ing_data['unit'],
                    notes=ing_data.get('notes', '')
                )
                db.session.add(recipe_ingredient)
            
            db.session.commit()
            print(f"Successfully added recipe: {recipe.name}")
            
        except Exception as e:
            db.session.rollback()
            print(f"Error adding recipe: {str(e)}")

if __name__ == "__main__":
    add_saag_aloo()
