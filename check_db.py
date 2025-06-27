import sqlite3

def check_database():
    # Connect to the SQLite database
    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()
    
    # Check if the recipe was added
    print("\n=== Checking for Saag Aloo recipe ===")
    cursor.execute("SELECT id, name, servings, source_link FROM recipe WHERE name LIKE '%Saag Aloo%';")
    recipe = cursor.fetchone()
    
    if recipe:
        print(f"✅ Found recipe: {recipe[1]} (ID: {recipe[0]})")
        print(f"   Servings: {recipe[2]}")
        print(f"   Source: {recipe[3]}")
        
        # Get recipe ingredients
        print("\nRecipe Ingredients:")
        cursor.execute("""
            SELECT i.name, ri.quantity, ri.unit, ri.notes, a.name as aisle
            FROM recipe_ingredients ri
            JOIN ingredients i ON ri.ingredient_id = i.id
            LEFT JOIN aisles a ON i.aisle_id = a.id
            WHERE ri.recipe_id = ?
        """, (recipe[0],))
        
        ingredients = cursor.fetchall()
        if ingredients:
            for i, (name, qty, unit, notes, aisle) in enumerate(ingredients, 1):
                print(f"   {i}. {qty} {unit} {name} {notes if notes else ''} ({aisle if aisle else 'No Aisle'})")
        else:
            print("   No ingredients found for this recipe.")
    else:
        print("❌ Saag Aloo recipe not found in the database.")
    
    # List all recipes
    print("\n=== All Recipes in Database ===")
    cursor.execute("SELECT id, name, servings, source_link FROM recipe;")
    recipes = cursor.fetchall()
    
    if recipes:
        for recipe in recipes:
            print(f"- {recipe[1]} (ID: {recipe[0]}, Servings: {recipe[2]})")
    else:
        print("No recipes found in the database.")
    
    # Check database schema
    print("\n=== Database Schema ===")
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
    tables = cursor.fetchall()
    print("\nTables in the database:")
    for table in tables:
        print(f"- {table[0]}")
    
    # Show structure of key tables
    for table in ['recipe', 'ingredients', 'recipe_ingredients', 'aisles']:
        print(f"\nStructure of {table} table:")
        try:
            cursor.execute(f"PRAGMA table_info({table});")
            columns = cursor.fetchall()
            for column in columns:
                print(f"  - {column[1]} ({column[2]}) {'NOT NULL' if column[3] else ''} {'PRIMARY KEY' if column[5] == 1 else ''}")
        except sqlite3.OperationalError:
            print(f"  Table {table} does not exist.")
    
    conn.close()

if __name__ == '__main__':
    check_database()
