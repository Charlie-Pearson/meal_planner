from app import app, db, Recipe

with app.app_context():
    recipes = Recipe.query.all()
    print(f"\nTotal number of recipes: {len(recipes)}\n")
    
    print("Recipe details:")
    print("-" * 50)
    for recipe in recipes:
        print(f"\nName: {recipe.name}")
        if recipe.source_link:
            print(f"Source: {recipe.source_link}")
        print(f"\nServings: {recipe.servings}")
        print(f"Meal types: {'Breakfast ' if recipe.is_breakfast else ''}{'Lunch ' if recipe.is_lunch else ''}{'Dinner' if recipe.is_dinner else ''}")
        print("\nIngredients:")
        for ingredient in recipe.ingredients:
            print(f"- {ingredient.quantity} {ingredient.unit} {ingredient.name}")
        if recipe.method:
            print("\nInstructions:")
            print(recipe.method)
        print("-" * 50) 