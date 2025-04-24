import app
from app import db, Recipe, Ingredient
from datetime import datetime, UTC

# List of vegan recipes with their details
vegan_recipes = [
    {
        "name": "Overnight Oats with Berries",
        "method": "1. Mix oats with plant milk in a jar\n2. Add chia seeds and maple syrup\n3. Refrigerate overnight\n4. Top with fresh berries before serving",
        "servings": 1,
        "is_breakfast": True,
        "is_lunch": False,
        "is_dinner": False,
        "ingredients": [
            ("Rolled oats", 50, "g"),
            ("Plant milk", 120, "ml"),
            ("Chia seeds", 10, "g"),
            ("Maple syrup", 15, "ml"),
            ("Mixed berries", 80, "g")
        ]
    },
    {
        "name": "Chickpea Curry",
        "method": "1. Sauté onions and garlic\n2. Add spices and cook until fragrant\n3. Add chickpeas and coconut milk\n4. Simmer for 20 minutes\n5. Serve with rice",
        "servings": 4,
        "is_breakfast": False,
        "is_lunch": True,
        "is_dinner": True,
        "ingredients": [
            ("Chickpeas", 400, "g"),
            ("Coconut milk", 400, "ml"),
            ("Onion", 1, "unit"),
            ("Garlic", 3, "cloves"),
            ("Curry powder", 2, "tbsp"),
            ("Rice", 300, "g")
        ]
    },
    {
        "name": "Buddha Bowl",
        "method": "1. Cook quinoa according to package instructions\n2. Roast sweet potatoes and chickpeas\n3. Steam kale\n4. Assemble bowl with all ingredients\n5. Drizzle with tahini dressing",
        "servings": 2,
        "is_breakfast": False,
        "is_lunch": True,
        "is_dinner": True,
        "ingredients": [
            ("Quinoa", 100, "g"),
            ("Sweet potato", 1, "large"),
            ("Chickpeas", 200, "g"),
            ("Kale", 100, "g"),
            ("Tahini", 30, "ml"),
            ("Lemon juice", 15, "ml")
        ]
    },
    {
        'name': 'Vegan Lentil Curry',
        'servings': 4,
        'is_breakfast': False,
        'is_lunch': True,
        'is_dinner': True,
        'ingredients': [
            ("Red lentils", 1, "cup"),
            ("Onion", 1, "large"),
            ("Garlic", 3, "cloves"),
            ("Ginger", 1, "inch"),
            ("Tomatoes", 2, "medium"),
            ("Coconut milk", 1, "can"),
            ("Curry powder", 2, "tbsp"),
            ("Turmeric", 1, "tsp"),
            ("Cumin", 1, "tsp"),
            ("Salt", 1, "tsp")
        ],
        'method': '''1. Rinse lentils and set aside.
2. Sauté onion, garlic, and ginger until fragrant.
3. Add spices and cook for 1 minute.
4. Add tomatoes and cook until soft.
5. Add lentils and coconut milk.
6. Simmer for 20-25 minutes until lentils are tender.
7. Season with salt and serve with rice.'''
    },
    {
        'name': 'Vegan Breakfast Burrito',
        'servings': 2,
        'is_breakfast': True,
        'is_lunch': False,
        'is_dinner': False,
        'ingredients': [
            ("Tortillas", 2, "large"),
            ("Black beans", 1, "can"),
            ("Tofu", 1, "block"),
            ("Bell pepper", 1, "medium"),
            ("Onion", 0.5, "medium"),
            ("Spinach", 2, "cups"),
            ("Avocado", 1, "whole"),
            ("Nutritional yeast", 2, "tbsp"),
            ("Turmeric", 0.5, "tsp"),
            ("Salt", 0.5, "tsp")
        ],
        'method': '''1. Crumble tofu and season with turmeric, salt, and nutritional yeast.
2. Sauté bell pepper and onion until soft.
3. Add tofu and cook until golden.
4. Warm tortillas.
5. Heat black beans.
6. Assemble burritos with beans, tofu scramble, fresh spinach, and sliced avocado.
7. Roll up and serve.'''
    },
    {
        'name': 'Vegan Mushroom Risotto',
        'servings': 4,
        'is_breakfast': False,
        'is_lunch': True,
        'is_dinner': True,
        'ingredients': [
            ("Arborio rice", 1.5, "cups"),
            ("Mushrooms", 16, "oz"),
            ("Onion", 1, "medium"),
            ("Garlic", 3, "cloves"),
            ("White wine", 0.5, "cup"),
            ("Vegetable broth", 4, "cups"),
            ("Nutritional yeast", 0.25, "cup"),
            ("Olive oil", 2, "tbsp"),
            ("Salt", 1, "tsp"),
            ("Black pepper", 0.5, "tsp")
        ],
        'method': '''1. Sauté mushrooms until golden and set aside.
2. In the same pan, sauté onion and garlic until soft.
3. Add rice and toast for 2 minutes.
4. Add wine and cook until absorbed.
5. Gradually add hot broth, stirring constantly.
6. Cook until rice is creamy and tender.
7. Stir in mushrooms, nutritional yeast, salt, and pepper.'''
    },
    {
        'name': 'Vegan Chickpea Salad',
        'servings': 4,
        'is_breakfast': False,
        'is_lunch': True,
        'is_dinner': False,
        'ingredients': [
            ("Chickpeas", 2, "cans"),
            ("Celery", 2, "stalks"),
            ("Red onion", 0.5, "medium"),
            ("Dill pickle", 1, "large"),
            ("Vegan mayo", 0.5, "cup"),
            ("Dijon mustard", 1, "tbsp"),
            ("Lemon juice", 1, "tbsp"),
            ("Salt", 0.5, "tsp"),
            ("Black pepper", 0.25, "tsp")
        ],
        'method': '''1. Drain and rinse chickpeas.
2. Mash chickpeas with a fork or potato masher.
3. Finely chop celery, onion, and pickle.
4. Mix all ingredients in a large bowl.
5. Season with salt and pepper.
6. Chill for at least 1 hour before serving.
7. Serve on bread or lettuce wraps.'''
    },
    {
        'name': 'Vegan Pad Thai',
        'servings': 4,
        'is_breakfast': False,
        'is_lunch': True,
        'is_dinner': True,
        'ingredients': [
            ("Rice noodles", 8, "oz"),
            ("Tofu", 1, "block"),
            ("Bean sprouts", 2, "cups"),
            ("Carrots", 2, "medium"),
            ("Green onions", 4, "stalks"),
            ("Peanuts", 0.5, "cup"),
            ("Tamarind paste", 2, "tbsp"),
            ("Soy sauce", 3, "tbsp"),
            ("Maple syrup", 2, "tbsp"),
            ("Lime", 1, "whole")
        ],
        'method': '''1. Soak rice noodles in warm water for 30 minutes.
2. Press and cube tofu, then pan-fry until golden.
3. Julienne carrots and slice green onions.
4. Make sauce by mixing tamarind, soy sauce, and maple syrup.
5. Stir-fry tofu with sauce.
6. Add noodles and vegetables, stir-fry until heated through.
7. Garnish with peanuts, lime wedges, and bean sprouts.'''
    },
    {
        'name': 'Vegan Overnight Oats',
        'servings': 1,
        'is_breakfast': True,
        'is_lunch': False,
        'is_dinner': False,
        'ingredients': [
            ("Rolled oats", 0.5, "cup"),
            ("Almond milk", 0.5, "cup"),
            ("Chia seeds", 1, "tbsp"),
            ("Maple syrup", 1, "tbsp"),
            ("Vanilla extract", 0.25, "tsp"),
            ("Banana", 1, "medium"),
            ("Berries", 0.5, "cup"),
            ("Almonds", 2, "tbsp"),
            ("Cinnamon", 0.25, "tsp")
        ],
        'method': '''1. Mix oats, almond milk, chia seeds, maple syrup, and vanilla.
2. Refrigerate overnight.
3. In the morning, slice banana.
4. Top with banana, berries, almonds, and cinnamon.
5. Add more almond milk if desired.
6. Stir well before eating.
7. Enjoy cold or warm.'''
    },
    {
        'name': 'Vegan Stuffed Peppers',
        'servings': 4,
        'is_breakfast': False,
        'is_lunch': True,
        'is_dinner': True,
        'ingredients': [
            ("Bell peppers", 4, "large"),
            ("Quinoa", 1, "cup"),
            ("Black beans", 1, "can"),
            ("Corn", 1, "cup"),
            ("Onion", 1, "medium"),
            ("Garlic", 2, "cloves"),
            ("Tomato sauce", 1, "cup"),
            ("Cumin", 1, "tsp"),
            ("Chili powder", 1, "tsp"),
            ("Salt", 0.5, "tsp")
        ],
        'method': '''1. Cook quinoa according to package instructions.
2. Cut tops off peppers and remove seeds.
3. Sauté onion and garlic until soft.
4. Mix quinoa, beans, corn, and seasonings.
5. Stuff peppers with mixture.
6. Pour tomato sauce over peppers.
7. Bake at 375°F for 30-35 minutes.'''
    },
    {
        'name': 'Vegan Tempeh Stir-Fry',
        'servings': 4,
        'is_breakfast': False,
        'is_lunch': True,
        'is_dinner': True,
        'ingredients': [
            ("Tempeh", 1, "block"),
            ("Broccoli", 2, "cups"),
            ("Carrots", 2, "medium"),
            ("Bell pepper", 1, "large"),
            ("Soy sauce", 3, "tbsp"),
            ("Rice vinegar", 1, "tbsp"),
            ("Sesame oil", 1, "tbsp"),
            ("Ginger", 1, "inch"),
            ("Garlic", 2, "cloves")
        ],
        'method': '''1. Cut tempeh into cubes and steam for 10 minutes.
2. Prepare sauce by mixing soy sauce, rice vinegar, and sesame oil.
3. Cut vegetables into bite-sized pieces.
4. Stir-fry tempeh until golden.
5. Add vegetables and stir-fry until tender-crisp.
6. Pour sauce over and cook until heated through.
7. Serve over rice or noodles.'''
    },
    {
        'name': 'Vegan Chocolate Smoothie',
        'servings': 1,
        'is_breakfast': True,
        'is_lunch': False,
        'is_dinner': False,
        'ingredients': [
            ("Banana", 1, "large"),
            ("Almond milk", 1, "cup"),
            ("Cocoa powder", 2, "tbsp"),
            ("Medjool dates", 2, "whole"),
            ("Almond butter", 1, "tbsp"),
            ("Vanilla extract", 0.5, "tsp"),
            ("Cinnamon", 0.25, "tsp"),
            ("Ice", 1, "cup")
        ],
        'method': '''1. Pit dates and soak in warm water for 5 minutes.
2. Peel and freeze banana.
3. Add all ingredients to blender.
4. Blend until smooth and creamy.
5. Add more almond milk if needed.
6. Taste and adjust sweetness if desired.
7. Serve immediately.'''
    },
    {
        'name': 'Vegan Cauliflower Steak',
        'servings': 2,
        'is_breakfast': False,
        'is_lunch': True,
        'is_dinner': True,
        'ingredients': [
            ("Cauliflower", 1, "large head"),
            ("Olive oil", 2, "tbsp"),
            ("Garlic powder", 1, "tsp"),
            ("Smoked paprika", 1, "tsp"),
            ("Cumin", 0.5, "tsp"),
            ("Salt", 0.5, "tsp"),
            ("Black pepper", 0.25, "tsp"),
            ("Lemon", 1, "whole"),
            ("Fresh herbs", 0.25, "cup")
        ],
        'method': '''1. Cut cauliflower into 1-inch thick steaks.
2. Mix oil and spices for marinade.
3. Brush both sides of steaks with marinade.
4. Roast at 400°F for 20-25 minutes.
5. Flip halfway through cooking.
6. Squeeze lemon over steaks.
7. Garnish with fresh herbs and serve.'''
    },
    {
        'name': 'Vegan Mediterranean Bowl',
        'servings': 2,
        'is_breakfast': False,
        'is_lunch': True,
        'is_dinner': False,
        'ingredients': [
            ("Quinoa", 1, "cup"),
            ("Chickpeas", 1, "can"),
            ("Cucumber", 1, "medium"),
            ("Tomatoes", 2, "medium"),
            ("Red onion", 0.5, "medium"),
            ("Kalamata olives", 0.5, "cup"),
            ("Hummus", 0.5, "cup"),
            ("Tahini", 2, "tbsp"),
            ("Lemon juice", 1, "tbsp"),
            ("Fresh parsley", 0.25, "cup")
        ],
        'method': '''1. Cook quinoa according to package instructions.
2. Drain and rinse chickpeas.
3. Chop vegetables into bite-sized pieces.
4. Make tahini sauce by mixing tahini and lemon juice.
5. Assemble bowls with quinoa base.
6. Top with vegetables, chickpeas, and olives.
7. Drizzle with tahini sauce and serve with hummus.'''
    }
]

def add_recipes():
    # Clear existing recipes
    Recipe.query.delete()
    Ingredient.query.delete()
    db.session.commit()
    
    # Add new recipes
    for recipe_data in vegan_recipes:
        recipe = Recipe(
            name=recipe_data['name'],
            method=recipe_data['method'],
            servings=recipe_data['servings'],
            is_breakfast=recipe_data['is_breakfast'],
            is_lunch=recipe_data['is_lunch'],
            is_dinner=recipe_data['is_dinner'],
            created_at=datetime.now(UTC)
        )
        db.session.add(recipe)
        db.session.flush()  # Get the recipe ID
        
        # Add ingredients
        for name, quantity, unit in recipe_data['ingredients']:
            ingredient = Ingredient(
                recipe_id=recipe.id,
                name=name,
                quantity=quantity,
                unit=unit
            )
            db.session.add(ingredient)
    
    db.session.commit()
    print("Successfully added vegan recipes to the database.")

if __name__ == '__main__':
    add_recipes() 