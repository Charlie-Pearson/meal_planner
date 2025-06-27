from app import app, db
from app.models import Recipe, Ingredient, RecipeIngredient, Aisle

def list_recipes():
    with app.app_context():
        # Get all recipes
        recipes = Recipe.query.all()
        
        if not recipes:
            print("No recipes found in the database.")
            return
        
        print("\n=== Recipes in the Database ===")
        for recipe in recipes:
            print(f"\nRecipe: {recipe.name} (ID: {recipe.id})")
            print(f"Servings: {recipe.servings}")
            print(f"Meal Types: {'Breakfast ' if recipe.is_breakfast else ''}{'Lunch ' if recipe.is_lunch else ''}{'Dinner' if recipe.is_dinner else ''}")
            print(f"Source: {recipe.source_link}")
            
            # Get all ingredients for this recipe
            ingredients = db.session.query(
                RecipeIngredient.quantity,
                RecipeIngredient.unit,
                Ingredient.name,
                RecipeIngredient.notes,
                Aisle.name.label('aisle')
            ).join(
                Ingredient, RecipeIngredient.ingredient_id == Ingredient.id
            ).join(
                Aisle, Ingredient.aisle_id == Aisle.id
            ).filter(
                RecipeIngredient.recipe_id == recipe.id
            ).all()
            
            print("\nIngredients:")
            for ing in ingredients:
                print(f"- {ing.quantity} {ing.unit} {ing.name} {ing.notes if ing.notes else ''} ({ing.aisle})")

if __name__ == "__main__":
    list_recipes()
