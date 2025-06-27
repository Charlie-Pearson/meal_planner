from app import app, db
from app.models import Recipe

def list_all_recipes():
    with app.app_context():
        recipes = Recipe.query.all()
        if not recipes:
            print("No recipes found in the database.")
            return
            
        print("\nRecipes in the database:")
        print("ID\tName\t\tServings\tMeal Types")
        print("-" * 50)
        
        for recipe in recipes:
            meal_types = []
            if recipe.is_breakfast:
                meal_types.append("Breakfast")
            if recipe.is_lunch:
                meal_types.append("Lunch")
            if recipe.is_dinner:
                meal_types.append("Dinner")
                
            print(f"{recipe.id}\t{recipe.name}\t{recipe.servings}\t\t{', '.join(meal_types)}")

if __name__ == "__main__":
    list_all_recipes()
