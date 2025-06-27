from app import app, db
from app.models import Recipe, Ingredient, RecipeIngredient, Aisle
import re

def get_or_create_ingredient(name, aisle_name=None):
    """Get an existing ingredient or create a new one if it doesn't exist"""
    # Clean and normalize the ingredient name
    name = name.strip().lower()
    
    # Check if ingredient already exists
    ingredient = Ingredient.query.filter_by(name=name).first()
    
    if not ingredient:
        # Create new ingredient
        ingredient = Ingredient(name=name)
        
        # Set aisle if provided
        if aisle_name:
            aisle = Aisle.query.filter_by(name=aisle_name).first()
            if not aisle:
                aisle = Aisle(name=aisle_name)
                db.session.add(aisle)
            ingredient.aisle = aisle
        
        db.session.add(ingredient)
        db.session.commit()
        
    return ingredient

def add_recipe(name, ingredients_list, method, servings=4, is_breakfast=False, 
              is_lunch=True, is_dinner=True, source_link=None):
    """Add a new recipe to the database"""
    with app.app_context():
        try:
            # Create new recipe
            recipe = Recipe(
                name=name,
                method=method,
                servings=servings,
                is_breakfast=is_breakfast,
                is_lunch=is_lunch,
                is_dinner=is_dinner,
                source_link=source_link
            )
            
            db.session.add(recipe)
            db.session.flush()  # Get the recipe ID
            
            # Add ingredients
            for item in ingredients_list:
                if isinstance(item, dict):
                    ingredient_name = item.get('name')
                    quantity = item.get('quantity', 1)
                    unit = item.get('unit', '')
                    notes = item.get('notes', '')
                    aisle = item.get('aisle')
                else:
                    ingredient_name = item
                    quantity = 1
                    unit = ''
                    notes = ''
                    aisle = None
                
                # Get or create ingredient
                ingredient = get_or_create_ingredient(ingredient_name, aisle)
                
                # Create recipe ingredient association
                recipe_ingredient = RecipeIngredient(
                    recipe_id=recipe.id,
                    ingredient_id=ingredient.id,
                    quantity=quantity,
                    unit=unit,
                    notes=notes
                )
                db.session.add(recipe_ingredient)
            
            db.session.commit()
            print(f"Successfully added recipe: {name}")
            return recipe
            
        except Exception as e:
            db.session.rollback()
            print(f"Error adding recipe: {e}")
            raise

def add_saag_aloo():
    """Add Saag Aloo recipe to the database"""
    name = "Saag Aloo"
    
    ingredients = [
        {"name": "cumin seed", "quantity": 1, "unit": "tsp", "aisle": "Spices"},
        {"name": "onion", "quantity": 1, "unit": "large", "aisle": "Produce"},
        {"name": "garlic clove", "quantity": 3, "unit": "", "aisle": "Produce"},
        {"name": "ginger", "quantity": 1, "unit": "tbsp", "notes": "grated", "aisle": "Produce"},
        {"name": "green chili", "quantity": 1, "unit": "", "aisle": "Produce"},
        {"name": "turmeric", "quantity": 1, "unit": "tsp", "aisle": "Spices"},
        {"name": "coriander", "quantity": 1, "unit": "tsp", "notes": "ground", "aisle": "Spices"},
        {"name": "garam masala", "quantity": 1, "unit": "tsp", "aisle": "Spices"},
        {"name": "chili powder", "quantity": 0.5, "unit": "tsp", "aisle": "Spices"},
        {"name": "potato", "quantity": 500, "unit": "g", "notes": "peeled and cubed", "aisle": "Produce"},
        {"name": "spinach", "quantity": 250, "unit": "g", "notes": "fresh, chopped", "aisle": "Produce"},
        {"name": "coriander", "quantity": 2, "unit": "tbsp", "notes": "fresh, chopped", "aisle": "Produce"}
    ]
    
    method = """1. Heat oil in a large pan over medium heat. Add cumin seeds and let them sizzle for 30 seconds.
2. Add onion and cook until golden brown, about 5 minutes.
3. Add garlic, ginger, and green chili. Cook for 1 minute until fragrant.
4. Stir in turmeric, coriander, garam masala, and chili powder. Cook for 30 seconds.
5. Add potatoes and stir to coat with spices. Cook for 2 minutes.
6. Cover and simmer for 15 minutes or until potatoes are tender, adding a splash of water if needed.
7. Stir in spinach and cook until wilted, about 3 minutes.
8. Garnish with fresh coriander before serving."""
    
    source_link = "https://rainbowplantlife.com/saag-aloo/"
    
    return add_recipe(
        name=name,
        ingredients_list=ingredients,
        method=method,
        servings=4,
        is_lunch=True,
        is_dinner=True,
        source_link=source_link
    )

if __name__ == "__main__":
    with app.app_context():
        add_saag_aloo()
