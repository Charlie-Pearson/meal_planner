from app import app, db
from app.models import Recipe, Ingredient, RecipeIngredient

def check_recipe(recipe_name):
    with app.app_context():
        # Find the recipe
        recipe = Recipe.query.filter_by(name=recipe_name).first()
        
        if not recipe:
            print(f"Recipe '{recipe_name}' not found in the database.")
            return
        
        print(f"\nRecipe: {recipe.name}")
        print(f"Servings: {recipe.servings}")
        print(f"Meal types: {'Breakfast' if recipe.is_breakfast else ''} {'Lunch' if recipe.is_lunch else ''} {'Dinner' if recipe.is_dinner else ''}")
        print(f"Source: {recipe.source_link}")
        
        print("\nIngredients:")
        for ri in recipe.recipe_ingredients:
            print(f"- {ri.quantity} {ri.unit} {ri.ingredient.name} {ri.notes if ri.notes else ''}")
        
        print("\nMethod:")
        print(recipe.method)

if __name__ == "__main__":
    check_recipe("Saag Aloo")
