from app import app, db
from app import Recipe, Ingredient, Aisle, RecipeIngredient
from datetime import datetime, timezone

def add_avocado_pasta_recipe():
    with app.app_context():
        # Check if recipe already exists
        if Recipe.query.filter_by(name="Avocado Pasta").first():
            print("Recipe 'Avocado Pasta' already exists in the database.")
            return
            
        try:

            # Create or get aisles
            aisles = {}
            for aisle_name in ["Produce", "Pasta & Grains", "Dairy & Eggs", "Canned Goods"]:
                aisle = Aisle.query.filter_by(name=aisle_name).first()
                if not aisle:
                    aisle = Aisle(name=aisle_name)
                    db.session.add(aisle)
                aisles[aisle_name] = aisle
            
            # Create all ingredients first
            ingredients_data = [
                {"name": "pasta", "quantity": "8", "unit": "oz", "aisle": "Pasta & Grains"},
                {"name": "avocado", "quantity": "2", "unit": "", "aisle": "Produce"},
                {"name": "basil", "quantity": "1/4", "unit": "cup", "aisle": "Produce"},
                {"name": "garlic", "quantity": "2", "unit": "cloves", "aisle": "Produce"},
                {"name": "lemon juice", "quantity": "2", "unit": "tbsp", "aisle": "Produce"},
                {"name": "cherry tomatoes", "quantity": "1", "unit": "cup", "aisle": "Produce"},
                {"name": "feta cheese", "quantity": "1/2", "unit": "cup", "aisle": "Dairy & Eggs"},
                {"name": "salt", "quantity": "to taste", "unit": "", "aisle": "Canned Goods"},
                {"name": "black pepper", "quantity": "to taste", "unit": "", "aisle": "Canned Goods"}
            ]
            
            # Create or get all ingredients first
            ingredients = {}
            for item in ingredients_data:
                # Create or get ingredient
                ingredient = Ingredient.query.filter_by(name=item["name"]).first()
                if not ingredient:
                    # Get or create aisle
                    aisle = Aisle.query.filter_by(name=item["aisle"]).first()
                    if not aisle:
                        aisle = Aisle(name=item["aisle"])
                        db.session.add(aisle)
                        db.session.flush()
                    
                    ingredient = Ingredient(
                        name=item["name"],
                        unit=item["unit"],
                        aisle_id=aisle.id,
                        created_at=datetime.now(timezone.utc),
                        updated_at=datetime.now(timezone.utc)
                    )
                    db.session.add(ingredient)
                    db.session.flush()
                ingredients[item["name"]] = ingredient
            
            # Create the recipe
            recipe = Recipe(
                name="Avocado Pasta",
                servings=4,
                method="""1. Cook pasta according to package instructions. Reserve 1/2 cup of pasta water, then drain.
2. In a food processor, combine avocado, basil, garlic, lemon juice, and 1/4 cup of the reserved pasta water. Blend until smooth.
3. Toss the sauce with the hot pasta, adding more pasta water if needed to reach desired consistency.
4. Stir in cherry tomatoes, feta, and season with salt and pepper to taste.
5. Serve immediately, garnished with additional basil if desired.""",
                source_link="",
                is_breakfast=False,
                is_lunch=True,
                is_dinner=True,
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc)
            )
            db.session.add(recipe)
            db.session.flush()  # Get the recipe ID
            
            # Create recipe-ingredient relationships
            for item in ingredients_data:
                ingredient = ingredients[item["name"]]
                recipe_ingredient = RecipeIngredient(
                    recipe_id=recipe.id,
                    ingredient_id=ingredient.id,
                    quantity=item["quantity"],
                    created_at=datetime.now(timezone.utc),
                    updated_at=datetime.now(timezone.utc)
                )
                db.session.add(recipe_ingredient)
            
            # Commit the transaction
            db.session.commit()
            print("Successfully added 'Avocado Pasta' recipe to the database!")
            return True
            
        except Exception as e:
            db.session.rollback()
            print(f"An error occurred: {str(e)}")
            raise

if __name__ == "__main__":
    add_avocado_pasta_recipe()
