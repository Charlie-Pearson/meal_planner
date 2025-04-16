# meal_planner/app.py

# --- Standard Library Imports ---
import os
import random
import math
from collections import defaultdict
from decimal import Decimal, InvalidOperation
from typing import Dict, Any, List, Optional, Set, Tuple # Added for type hints
from datetime import datetime

# --- Third-Party Imports ---
from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.sql import func
from sqlalchemy.orm import joinedload # Explicit import for clarity
from flask_migrate import Migrate

# --- Configuration ---
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
DATABASE_PATH = os.path.join(BASE_DIR, 'database.db')

# --- Flask App Initialization ---
app = Flask(__name__)
# IMPORTANT: DO NOT use this hardcoded key in production.
# Generate a strong, random key and load it from environment variables or a config file.
# Example: app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'a_default_secret_key')
app.config['SECRET_KEY'] = 'a_much_better_secret_key_v6' # CHANGE THIS!
app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{DATABASE_PATH}'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False # Good practice

# --- Global Constants ---
days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
meal_types = ["Breakfast", "Lunch", "Dinner"]

# --- Database and Migration Initialization ---
db = SQLAlchemy(app)
migrate = Migrate(app, db)

# --- Database Models ---
# NOTE: Storing quantity as String is not ideal for calculations but kept due to constraints.
# Consider migrating to db.Numeric or db.Float if DB changes are allowed later.
class Recipe(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), nullable=False, unique=True)
    source_link = db.Column(db.String(500), nullable=True)
    method = db.Column(db.Text, nullable=True) # Optional
    servings = db.Column(db.Integer, nullable=False)
    is_breakfast = db.Column(db.Boolean, default=False, nullable=False)
    is_lunch = db.Column(db.Boolean, default=False, nullable=False)
    is_dinner = db.Column(db.Boolean, default=False, nullable=False)
    ingredients = db.relationship('Ingredient', backref='recipe', lazy=True, cascade="all, delete-orphan")

    def __repr__(self):
        return f'<Recipe {self.name}>'

class Ingredient(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), nullable=False)
    quantity = db.Column(db.String(50), nullable=True) # Limitation: Stored as string
    unit = db.Column(db.String(50), nullable=True)
    aisle = db.Column(db.String(100), nullable=True, default=None)
    recipe_id = db.Column(db.Integer, db.ForeignKey('recipe.id'), nullable=False)

    def __repr__(self):
        return f'<Ingredient {self.name} for Recipe {self.recipe_id}>'

class PantryItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), nullable=False, unique=True)
    quantity = db.Column(db.String(50), nullable=True) # Limitation: Stored as string
    unit = db.Column(db.String(50), nullable=True)
    aisle = db.Column(db.String(100), nullable=True, default=None)

    def __repr__(self):
        return f'<PantryItem {self.name}>'

class LockedMeal(db.Model):
    """Stores persistent lock states for meal slots."""
    id = db.Column(db.Integer, primary_key=True)
    day = db.Column(db.String(10), nullable=False)  # Monday, Tuesday, etc.
    meal_type = db.Column(db.String(20), nullable=False)  # Breakfast, Lunch, Dinner
    recipe_id = db.Column(db.Integer, db.ForeignKey('recipe.id'), nullable=True)  # NULL for manual entries
    manual_text = db.Column(db.String(200), nullable=True)  # For manual text entries
    is_manual = db.Column(db.Boolean, default=False, nullable=False)  # True if manually set by user
    is_default = db.Column(db.Boolean, default=False, nullable=False)  # True if default breakfast lock
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # Unique constraint to ensure one lock per slot
    __table_args__ = (
        db.UniqueConstraint('day', 'meal_type', name='uix_day_meal'),
    )

    def __repr__(self):
        return f'<LockedMeal {self.day} {self.meal_type}>'


# --- Helper Functions ---
def get_pantry_items() -> Dict[str, PantryItem]:
    """
    Fetches all pantry items and returns a dictionary mapping
    normalized (lowercase, stripped) item names to PantryItem objects.
    """
    items = PantryItem.query.all()
    # Normalize keys for consistent lookup
    return {item.name.strip().lower(): item for item in items}

def update_pantry(item_name: str, quantity: str, unit: str, aisle: Optional[str] = None) -> None:
    """
    Adds a new item or updates an existing item in the pantry.
    Performs case-insensitive matching based on the normalized name.
    """
    normalized_name = item_name.strip().lower()
    # Case-insensitive query to find existing item
    pantry_item = PantryItem.query.filter(func.lower(PantryItem.name) == normalized_name).first()

    if pantry_item:
        pantry_item.quantity = quantity.strip() if quantity else None
        pantry_item.unit = unit.strip() if unit else None
        pantry_item.aisle = aisle.strip() if aisle else None
        flash(f"Updated '{pantry_item.name}' in pantry.", "info")
    else:
        # Create new item if not found
        pantry_item = PantryItem(
            name=item_name.strip(),
            quantity=quantity.strip() if quantity else None,
            unit=unit.strip() if unit else None,
            aisle=aisle.strip() if aisle else None
        )
        db.session.add(pantry_item)
        flash(f"Added '{item_name.strip()}' to pantry.", "success")
    try:
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        flash(f"Error updating pantry: {e}", "danger")
        app.logger.error(f"Error updating pantry item '{item_name}': {e}") # Log error

def remove_from_pantry(item_id: int) -> None:
    """Removes an item from the pantry by its primary key ID."""
    # Use get for efficient primary key lookup
    pantry_item = db.session.get(PantryItem, item_id)
    if pantry_item:
        item_name = pantry_item.name
        db.session.delete(pantry_item)
        try:
            db.session.commit()
            flash(f"Removed '{item_name}' from pantry.", "success")
        except Exception as e:
            db.session.rollback()
            flash(f"Error removing '{item_name}' from pantry: {e}", "danger")
            app.logger.error(f"Error removing pantry item ID {item_id}: {e}") # Log error
    else:
        flash(f"Pantry item ID {item_id} not found for deletion.", "warning")

def format_decimal(value: Optional[Decimal]) -> str:
    """Formats a Decimal, removing trailing .0 if it's an integer."""
    if value is None:
        return ""
    return str(value).rstrip('0').rstrip('.')

def get_distinct_aisles() -> List[str]:
    """Gets unique, non-empty, sorted aisle names from Ingredients and Pantry."""
    # Query distinct aisles from Ingredients
    q1 = db.session.query(Ingredient.aisle).filter(Ingredient.aisle.isnot(None), Ingredient.aisle != '').distinct()
    # Query distinct aisles from Pantry
    q2 = db.session.query(PantryItem.aisle).filter(PantryItem.aisle.isnot(None), PantryItem.aisle != '').distinct()
    # Combine results using union, convert to set for uniqueness, filter out None again just in case, sort.
    all_aisles = {row[0] for row in q1.union(q2).all() if row[0]}
    return sorted(list(all_aisles))

def get_persistent_locks() -> Dict[str, Dict[str, Any]]:
    """Get all persistent locks from the database."""
    locks = {}
    for lock in LockedMeal.query.all():
        slot_id = f"{lock.day}_{lock.meal_type}"
        lock_info = {
            'recipe_id': lock.recipe_id,
            'manual': lock.is_manual,
            'default': lock.is_default
        }
        if lock.manual_text:
            lock_info['text'] = lock.manual_text
        locks[slot_id] = lock_info
    return locks

def update_persistent_lock(slot_id: str, lock_info: Optional[Dict[str, Any]]) -> None:
    """Update or remove a persistent lock for a slot."""
    try:
        day, meal_type = slot_id.split('_')
        existing_lock = LockedMeal.query.filter_by(day=day, meal_type=meal_type).first()
        
        if lock_info is None:
            # Remove lock if it exists
            if existing_lock:
                db.session.delete(existing_lock)
        else:
            # Update or create lock
            if existing_lock:
                existing_lock.recipe_id = lock_info.get('recipe_id')
                existing_lock.manual_text = lock_info.get('text')
                existing_lock.is_manual = lock_info.get('manual', False)
                existing_lock.is_default = lock_info.get('default', False)
            else:
                new_lock = LockedMeal(
                    day=day,
                    meal_type=meal_type,
                    recipe_id=lock_info.get('recipe_id'),
                    manual_text=lock_info.get('text'),
                    is_manual=lock_info.get('manual', False),
                    is_default=lock_info.get('default', False)
                )
                db.session.add(new_lock)
        
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        app.logger.error(f"Error updating persistent lock for {slot_id}: {e}")
        raise

def sync_session_locks_with_db() -> None:
    """Sync session locks with database locks."""
    db_locks = get_persistent_locks()
    session['locked_meals'] = db_locks
    session.modified = True


# --- Shopping List Generation ---
# Type Alias for clarity
AggregatedIngredientInfo = Dict[str, Any] # Contains unit, recipes, aisle, needs_check, required_qty
ShoppingListDict = Dict[str, List[Dict[str, Any]]] # Aisle -> List of Item Dicts

def generate_shopping_list_data(plan_ids: Dict[str, Dict[str, Optional[Dict[str, Any]]]]) -> ShoppingListDict:
    """
    Generates shopping list data based on the meal plan IDs.
    Aggregates ingredients across unique recipes in the plan,
    deducts available pantry items, and structures the list by aisle.

    Args:
        plan_ids: Dictionary representing the meal plan {day: {meal_type: meal_info_dict}}.

    Returns:
        A dictionary where keys are aisle names and values are lists of
        ingredient dictionaries needed for shopping.
    """
    aggregated_ingredients: Dict[str, AggregatedIngredientInfo] = defaultdict(
        lambda: {'unit': None, 'recipes': set(), 'aisle': None, 'needs_check': False, 'required_qty': None}
    )

    # 1. Get UNIQUE recipe IDs from the plan (exclude manual entries: -1 and None)
    unique_recipe_ids_in_plan: Set[int] = set()
    for day_plan in plan_ids.values():
        for meal_info in day_plan.values():
            # Check if meal_info exists and has a valid recipe_id
            if meal_info and meal_info.get('recipe_id') and meal_info['recipe_id'] != -1:
                unique_recipe_ids_in_plan.add(meal_info['recipe_id'])

    if not unique_recipe_ids_in_plan:
        return {} # No recipes in the plan, return empty list

    # 2. Fetch unique recipes and EAGERLY load their ingredients to prevent N+1 queries
    #    This is a significant performance optimization.
    recipes = Recipe.query.options(joinedload(Recipe.ingredients))\
                           .filter(Recipe.id.in_(unique_recipe_ids_in_plan))\
                           .all()

    # 3. Aggregate required ingredients ONCE per unique recipe
    for recipe in recipes:
        for ing in recipe.ingredients:
            norm_name = ing.name.strip().lower()
            current_agg = aggregated_ingredients[norm_name]

            current_agg['recipes'].add(recipe.name)
            # Use ingredient's aisle if set, otherwise keep potentially existing aggregated aisle
            current_agg['aisle'] = ing.aisle or current_agg['aisle']

            ing_quantity_str = (ing.quantity or '').strip()
            ing_unit_str = (ing.unit or '').strip().lower()

            # Determine unit and check for mismatches
            if current_agg['unit'] is None and ing_unit_str:
                current_agg['unit'] = ing_unit_str
            elif ing_unit_str and current_agg['unit'] and ing_unit_str != current_agg['unit']:
                # Units differ for the same ingredient across recipes
                current_agg['needs_check'] = True
                current_agg['required_qty'] = None # Cannot reliably sum different units

            # Try to sum quantities if no unit mismatch or conversion error occurred yet
            if not current_agg['needs_check'] and ing_quantity_str:
                try:
                    quantity_dec = Decimal(ing_quantity_str)
                    # Initialize required_qty to 0 if it's the first time or was reset
                    if current_agg['required_qty'] is None:
                        current_agg['required_qty'] = Decimal('0')
                    current_agg['required_qty'] += quantity_dec
                except InvalidOperation:
                    # Handle non-numeric quantity strings (due to DB limitation)
                    current_agg['needs_check'] = True
                    current_agg['required_qty'] = None # Cannot sum non-numeric values

    # 4. Attempt Pantry Deduction and Structure by Aisle
    shopping_list_by_aisle: ShoppingListDict = defaultdict(list)
    pantry_items = get_pantry_items() # Fetch pantry items once

    for norm_name, data in aggregated_ingredients.items():
        final_needed_qty: Optional[Decimal] = data['required_qty']
        pantry_deducted_qty = Decimal('0')
        pantry_available_str = ""
        in_pantry = False
        unit_match = False
        can_deduct = False
        needs_check = data['needs_check'] # Carry over check status

        pantry_item = pantry_items.get(norm_name)

        # Check pantry stock if item exists and conditions allow deduction
        if pantry_item:
            in_pantry = True
            pantry_unit = (pantry_item.unit or '').strip().lower()
            # Format available pantry info string
            pantry_qty_str = pantry_item.quantity or '?'
            pantry_unit_str = pantry_item.unit or ''
            pantry_available_str = f"{pantry_item.name}: {pantry_qty_str} {pantry_unit_str}".strip()

            unit_match = (data['unit'] == pantry_unit)

            # Conditions for deduction: unit matches, quantity is known decimal, no previous check flag
            if unit_match and final_needed_qty is not None and not needs_check:
                try:
                    pantry_qty_dec = Decimal((pantry_item.quantity or '0').strip())
                    # Only proceed if pantry quantity is also a valid Decimal
                    can_deduct = True
                except (InvalidOperation, TypeError):
                    # Pantry quantity is not a valid number, cannot deduct
                    can_deduct = False
                    # Optional: flag for check if pantry qty is unusable? Depends on desired behavior.
                    # needs_check = True

        # Perform deduction if possible
        if can_deduct and final_needed_qty is not None and pantry_qty_dec is not None:
            deduction = min(final_needed_qty, pantry_qty_dec)
            final_needed_qty -= deduction
            pantry_deducted_qty = deduction

        # Determine display quantity and unit
        display_quantity_str = ""
        display_unit = data['unit']

        # If quantity couldn't be calculated, mark for check
        if final_needed_qty is None and not needs_check:
             needs_check = True # Mark if calculation failed unexpectedly

        if needs_check:
            # Indicate manual check needed if units mismatched or quantities were non-numeric
            display_quantity_str = "(Check recipes/pantry)"
            display_unit = None # Unit is uncertain
        elif final_needed_qty is not None:
             if final_needed_qty <= 0:
                 # Don't add to shopping list if pantry covers the need
                 continue
             else:
                 # Format the needed quantity nicely
                 display_quantity_str = format_decimal(final_needed_qty)

        # Determine aisle, defaulting to "Unknown"
        aisle = data['aisle'] or "Unknown"

        # Append item details to the correct aisle list
        shopping_list_by_aisle[aisle].append({
            'name': norm_name.capitalize(),
            'normalized_name': norm_name,
            'display_quantity': display_quantity_str,
            'unit': display_unit,
            'needs_check': needs_check,
            'recipes': sorted(list(data['recipes'])),
            'aisle': aisle,
            'in_pantry': in_pantry,
            'pantry_available': pantry_available_str,
            'pantry_deducted': format_decimal(pantry_deducted_qty) if pantry_deducted_qty > 0 else None,
            'unit_match': unit_match,
            'is_custom': False # Mark as non-custom
        })

    # 5. Add Custom Items from Session state
    list_state = session.get('shopping_list_state', {})
    custom_items_state: List[Dict[str, Any]] = list_state.get('custom_items', [])
    removed_norm_names: Set[str] = set(list_state.get('removed', {}).keys())

    # Cache known aisles for custom items to avoid repeated DB lookups if many custom items
    # Only query once if there are custom items to process
    known_aisles_cache: Dict[str, str] = {}
    if custom_items_state:
        all_ingredient_aisles = db.session.query(Ingredient.name, Ingredient.aisle)\
                                          .filter(Ingredient.aisle.isnot(None), Ingredient.aisle != '')\
                                          .distinct().all()
        known_aisles_cache = { name.strip().lower(): aisle for name, aisle in all_ingredient_aisles if aisle }

    for index, item in enumerate(custom_items_state):
        norm_name = item['name'].strip().lower()
        # Skip if this custom item was marked as 'removed'
        if norm_name in removed_norm_names:
            continue

        # Determine aisle: Use provided, fallback to cache, then "Unknown"
        item_aisle = item.get('aisle') or known_aisles_cache.get(norm_name) or "Unknown"

        # Check if custom item exists in pantry
        pantry_str = ""
        in_pantry_custom = False
        if norm_name in pantry_items:
            in_pantry_custom = True
            pantry_item_obj = pantry_items[norm_name]
            pantry_qty_str = pantry_item_obj.quantity or '?'
            pantry_unit_str = pantry_item_obj.unit or ''
            pantry_str = f"{pantry_item_obj.name}: {pantry_qty_str} {pantry_unit_str}".strip()

        shopping_list_by_aisle[item_aisle].append({
            'name': item['name'], # Keep original casing for display
            'normalized_name': norm_name,
            'display_quantity': "", # Custom items don't have quantities here
            'unit': None,
            'needs_check': False, # Assume custom items don't need checking unless specified
            'recipes': [], # No associated recipes
            'aisle': item_aisle,
            'in_pantry': in_pantry_custom,
            'pantry_available': pantry_str,
            'pantry_deducted': None, # No deduction logic for custom items here
            'unit_match': False, # No unit to match against here
            'is_custom': True,
            'custom_item_index': index # Include index if needed for removal later
        })

    # 6. Sort Aisles and Items within aisles for consistent display
    # Define preferred aisle order
    aisle_order = ["Produce", "Meat", "Dairy", "Bakery", "Frozen", "Pantry", "Canned Goods", "Spices", "Drinks", "Household", "Misc", "Unknown"]
    aisle_order_map = {a: i for i, a in enumerate(aisle_order)}

    # Sort aisle keys based on the defined order, then alphabetically
    sorted_aisle_keys = sorted(
        shopping_list_by_aisle.keys(),
        key=lambda a: (aisle_order_map.get(a, 999), a) # Use 999 for unknown aisles to put them last
    )

    # Create the final sorted dictionary
    sorted_list: ShoppingListDict = {
        aisle: sorted(shopping_list_by_aisle[aisle], key=lambda x: x['name']) # Sort items alphabetically by name within each aisle
        for aisle in sorted_aisle_keys
    }
    return sorted_list


# --- Meal Plan Generation ---
# Type Aliases for Meal Plan structure
MealInfoDict = Dict[str, Any] # Holds recipe_id, status, locks etc.
DayPlanDict = Dict[str, Optional[MealInfoDict]] # meal_type -> MealInfoDict
PlanIdsDict = Dict[str, DayPlanDict] # day_name -> DayPlanDict
LockedMealsDict = Dict[str, Dict[str, Any]] # slot_id -> lock_info_dict
Coords = Tuple[int, str] # (day_index, meal_type)

def generate_meal_plan(num_people: int, locked_meals: LockedMealsDict, default_breakfast_recipe_name: str = "Cereal") -> PlanIdsDict:
    """
    Generates a 7-day meal plan, considering locked meals, default breakfast,
    and propagating leftovers and lock status.

    Args:
        num_people: The number of people the plan is for (affects leftovers).
        locked_meals: A dictionary of user-defined locks {slot_id: lock_info}.
        default_breakfast_recipe_name: Name of the default breakfast recipe.

    Returns:
        A dictionary representing the 7-day plan with recipe IDs and status.
    """
    plan_ids: PlanIdsDict = {day: {meal_type: None for meal_type in meal_types} for day in days}

    # Tracking states during generation
    leftovers_to_assign: Dict[Coords, Dict[str, Any]] = {} # {(day_idx, meal): {recipe_id: X, source_slot: Y}}
    active_locks: Dict[Coords, Union[int, str]] = {} # {(day_idx, meal): recipe_id or -1 } Includes defaults & user locks
    additional_locks: Dict[Coords, int] = {} # {(day_idx, meal): recipe_id } Locks propagated from leftovers of locked meals

    # --- Process Defaults & User Locks ---
    # Find default breakfast ID (case-insensitive)
    default_breakfast_id = db.session.query(Recipe.id)\
        .filter(func.lower(Recipe.name) == default_breakfast_recipe_name.lower())\
        .scalar()

    # Apply default breakfast if found and not overridden by user lock
    if default_breakfast_id:
        for day_index, day in enumerate(days):
            slot_id = f"{day}_Breakfast"
            breakfast_coords: Coords = (day_index, "Breakfast")
            # Only apply default if the user hasn't explicitly locked this slot
            if slot_id not in locked_meals:
                active_locks[breakfast_coords] = default_breakfast_id
                # Mark in plan_ids with status and default flag
                plan_ids[day]["Breakfast"] = {
                    'recipe_id': default_breakfast_id,
                    'status': 'locked',
                    'locked_by_main': False, # Not locked by user directly
                    'default_lock': True     # Indicates it's a default lock
                }

    # Process user-provided locks
    for slot_id, lock_info in locked_meals.items():
        try:
            day, meal_type = slot_id.split('_')
            day_index = days.index(day)
            current_coords: Coords = (day_index, meal_type)
        except (ValueError, IndexError):
            app.logger.warning(f"Invalid slot_id format in locked_meals: {slot_id}")
            continue # Skip malformed slot_id

        if isinstance(lock_info, dict) and 'recipe_id' in lock_info:
             recipe_id = lock_info['recipe_id']
             # Handle manual entry lock (-1)
             if recipe_id == -1:
                 active_locks[current_coords] = -1
                 plan_ids[day][meal_type] = {
                     'recipe_id': -1,
                     'manual_text': lock_info.get('text', 'Manual Entry'),
                     'status': 'locked',
                     'locked_by_main': True # User explicitly set this
                 }
             elif recipe_id is not None:
                 # Check if the locked recipe actually exists in the DB
                 if db.session.get(Recipe, recipe_id):
                     active_locks[current_coords] = recipe_id
                     plan_ids[day][meal_type] = {
                         'recipe_id': recipe_id,
                         'status': 'locked',
                         'locked_by_main': True, # User explicitly locked this
                         'default_lock': False # Overrides default if applicable
                     }
                     # If this lock replaced a default breakfast lock, update plan_ids status
                     if meal_type == "Breakfast" and plan_ids[day][meal_type] and plan_ids[day][meal_type].get('default_lock'):
                         plan_ids[day][meal_type]['default_lock'] = False

                 else:
                     # Locked recipe doesn't exist (maybe deleted)
                     flash(f"Locked recipe ID {recipe_id} for {slot_id} not found in database. Lock ignored.", "warning")
                     # Ensure this invalid lock is not active and plan slot is cleared if it held the bad ID
                     if current_coords in active_locks and active_locks[current_coords] == recipe_id:
                         del active_locks[current_coords]
                     if plan_ids[day][meal_type] and plan_ids[day][meal_type].get('recipe_id') == recipe_id:
                         plan_ids[day][meal_type] = None

    # --- Fetch Recipes ---
    # Fetch all recipes once for efficiency
    all_recipes = Recipe.query.all()
    recipes_by_type: Dict[str, List[Recipe]] = {
        "Breakfast": [r for r in all_recipes if r.is_breakfast],
        "Lunch": [r for r in all_recipes if r.is_lunch],
        "Dinner": [r for r in all_recipes if r.is_dinner]
    }

    # --- Main Generation Loop ---
    for day_index, day in enumerate(days):
        for meal_type in meal_types:
            current_slot_coords: Coords = (day_index, meal_type)

            # Skip if slot is already filled (by locks or previous leftover assignment)
            if plan_ids[day][meal_type] is not None:
                continue

            # --- 1. Try Assigning Leftovers First ---
            if current_slot_coords in leftovers_to_assign:
                leftover_info = leftovers_to_assign.pop(current_slot_coords)
                recipe = db.session.get(Recipe, leftover_info['recipe_id']) # Verify recipe still exists
                if recipe:
                    source_slot_coords: Coords = leftover_info['source_slot']
                    # Determine if the *source* of the leftover was locked by the user
                    is_source_locked_by_user = source_slot_coords in active_locks and active_locks[source_slot_coords] != default_breakfast_id

                    status = 'locked' if is_source_locked_by_user else 'leftover'
                    plan_ids[day][meal_type] = {
                        'recipe_id': leftover_info['recipe_id'],
                        'status': status,
                        'locked_by_main': is_source_locked_by_user # Inherit lock status
                    }
                    # If source was locked, propagate the lock to this leftover slot
                    if is_source_locked_by_user:
                        additional_locks[current_slot_coords] = leftover_info['recipe_id']
                else:
                    # Source recipe deleted? Log or handle as needed. Leave slot empty for now.
                    app.logger.warning(f"Recipe ID {leftover_info['recipe_id']} for leftover assignment at {current_slot_coords} not found.")
                    plan_ids[day][meal_type] = None
                continue # Move to next slot

            # --- 2. Assign New Random Recipe if No Leftover ---
            available_recipes = recipes_by_type.get(meal_type, [])
            if not available_recipes:
                # No recipes available for this meal type
                plan_ids[day][meal_type] = {'recipe_id': None, 'status': 'empty', 'locked_by_main': False}
                continue

            recipes_to_choose = available_recipes
            # Avoid choosing default breakfast if other breakfast options exist
            if meal_type == "Breakfast" and default_breakfast_id:
                 non_default_breakfasts = [r for r in available_recipes if r.id != default_breakfast_id]
                 if non_default_breakfasts:
                     recipes_to_choose = non_default_breakfasts
                 # If only default breakfast exists, recipes_to_choose remains [default_breakfast_recipe]

            if not recipes_to_choose:
                 # This case should be rare (only default breakfast exists, but was filtered out?)
                 plan_ids[day][meal_type] = {'recipe_id': None, 'status': 'empty', 'locked_by_main': False}
                 continue

            # Choose a random recipe from the suitable list
            chosen_recipe = random.choice(recipes_to_choose)
            plan_ids[day][meal_type] = {'recipe_id': chosen_recipe.id, 'status': 'new', 'locked_by_main': False}

            # --- 3. Calculate and Schedule Potential Leftovers ---
            try:
                # Check if leftovers should be generated
                # Requires valid servings, positive num_people, and servings > num_people
                if (chosen_recipe.servings is not None and
                        isinstance(num_people, int) and num_people > 0 and
                        chosen_recipe.servings > num_people):

                    # Calculate number of *additional* slots this meal covers
                    # Use float division and ceiling to ensure enough slots
                    additional_slots = int(math.ceil(chosen_recipe.servings / float(num_people))) - 1

                    # Determine if the source meal itself is now considered 'locked' by the user
                    # (either directly locked or was locked before generation)
                    is_source_now_locked_by_user = current_slot_coords in active_locks and active_locks[current_slot_coords] != default_breakfast_id

                    # Schedule leftovers for subsequent days for the same meal type
                    for i in range(1, additional_slots + 1):
                        next_day_index = day_index + i
                        # Ensure we don't go beyond the 7-day week
                        if next_day_index < len(days):
                            next_slot_coords: Coords = (next_day_index, meal_type)

                            # Check if the target leftover slot is available (not locked, not already assigned)
                            if (plan_ids[days[next_day_index]][meal_type] is None and
                                next_slot_coords not in active_locks and
                                next_slot_coords not in additional_locks and # Check propagated locks too
                                next_slot_coords not in leftovers_to_assign):

                                # Schedule the leftover assignment
                                leftovers_to_assign[next_slot_coords] = {
                                    'recipe_id': chosen_recipe.id,
                                    'source_slot': current_slot_coords
                                }
                                # If the source meal was locked, propagate the lock to the leftover slot
                                # Note: This check happens *after* the source meal is assigned,
                                # considering any user locks present for that source slot.
                                if is_source_now_locked_by_user:
                                    additional_locks[next_slot_coords] = chosen_recipe.id

            except (TypeError, ValueError, ZeroDivisionError) as e:
                 # Catch potential errors with servings calculation or num_people
                 app.logger.error(f"Error calculating leftovers for recipe {chosen_recipe.id} (servings: {chosen_recipe.servings}, num_people: {num_people}): {e}")
                 # Continue without generating leftovers for this meal

    # --- Final leftover assignment pass ---
    # This catches any leftovers that couldn't be assigned in the main loop
    # (e.g., if a later meal assignment blocked a potential leftover slot)
    # Process a copy of the items to allow modification during iteration
    for leftover_coords, leftover_info in list(leftovers_to_assign.items()):
         day_idx, meal_t = leftover_coords
         day_n = days[day_idx]

         # Double-check if the slot is still empty and not locked
         if plan_ids[day_n][meal_t] is None and leftover_coords not in active_locks and leftover_coords not in additional_locks:
             recipe = db.session.get(Recipe, leftover_info['recipe_id']) # Verify recipe exists
             if recipe:
                 source_slot_coords: Coords = leftover_info['source_slot']
                 # Final check if the source slot ended up being locked (user lock OR propagated lock)
                 is_source_finally_locked = source_slot_coords in active_locks or source_slot_coords in additional_locks
                 # Check if the source was the default breakfast lock (which shouldn't propagate as a 'main' lock)
                 source_plan_info = plan_ids[days[source_slot_coords[0]]][source_slot_coords[1]]
                 is_default_src_lock = source_plan_info.get('default_lock', False) if source_plan_info else False

                 # A leftover is 'locked_by_main' if its source was locked AND it wasn't just the default breakfast
                 is_locked_by_main = is_source_finally_locked and not is_default_src_lock
                 status = 'locked' if is_locked_by_main else 'leftover'

                 plan_ids[day_n][meal_t] = {
                     'recipe_id': leftover_info['recipe_id'],
                     'status': status,
                     'locked_by_main': is_locked_by_main
                 }
             else:
                app.logger.warning(f"Recipe ID {leftover_info['recipe_id']} for final leftover assignment at {leftover_coords} not found.")
                plan_ids[day_n][meal_t] = None # Ensure slot remains empty

    return plan_ids


# --- Routes (MUST come after app, db, models, helpers are defined) ---

@app.route('/', methods=['GET', 'POST'])
def dashboard():
    # Initialize session variables if they don't exist
    if 'num_people' not in session:
        session['num_people'] = 2
    if 'locked_meals' not in session:
        sync_session_locks_with_db()

    # Handle POST request (form submission)
    if request.method == 'POST':
        # Get form data
        try:
            num_people = int(request.form.get('num_people', session['num_people']))
            if num_people < 1:
                raise ValueError("Number of people must be at least 1")
            session['num_people'] = num_people
        except (ValueError, TypeError):
            flash("Invalid number of people. Using previous value.", "warning")
            num_people = session['num_people']

        # Check if this is a "Lock All" request
        lock_all = request.form.get('lock_all_flag') == 'true'
        
        # Initialize new locked meals dictionary
        new_locked_meals: Dict[str, Dict[str, Any]] = {}
        plan_ids_before_update: PlanIdsDict = session.get('current_plan_ids', {})

        # --- Loop through all possible slots and determine lock state based on form data ---
        for day in days:
            for meal_type in meal_types:
                slot_id = f"{day}_{meal_type}"
                # Get relevant form inputs for this slot
                manual_select = request.form.get(f'manual_select_{slot_id}')
                manual_text = request.form.get(f'manual_text_{slot_id}', '').strip()
                lock_checkbox = request.form.get(f'lock_{slot_id}')
                recipe_id_in_slot_str = request.form.get(f"recipeid_{slot_id}")

                lock_info_to_set: Optional[Dict[str, Any]] = None

                # --- Determine Lock State Based on Priority ---
                # 1. Manual Text Input (Highest priority)
                if manual_select == "-1" and manual_text:
                    lock_info_to_set = {
                        'recipe_id': -1,
                        'text': manual_text,
                        'manual': True,
                        'default': False
                    }

                # 2. Manual Recipe Selection
                elif manual_select and manual_select != "0" and manual_select != "-1":
                    try:
                        recipe_id = int(manual_select)
                        if db.session.get(Recipe, recipe_id):
                            lock_info_to_set = {
                                'recipe_id': recipe_id,
                                'manual': True,
                                'default': False
                            }
                        else:
                            flash(f"Selected recipe ID {recipe_id} for {slot_id} not found. Selection ignored.", "warning")
                    except (ValueError, TypeError):
                        flash(f"Invalid recipe selection value '{manual_select}' for {slot_id}. Selection ignored.", "warning")

                # 3. Checkbox or Lock All
                else:
                    should_lock_this_slot = (lock_checkbox == 'on') or lock_all
                    if should_lock_this_slot:
                        current_recipe_id: Optional[int] = None
                        try:
                            if recipe_id_in_slot_str and recipe_id_in_slot_str.isdigit():
                                current_recipe_id = int(recipe_id_in_slot_str)
                            elif lock_all:
                                slot_info = plan_ids_before_update.get(day, {}).get(meal_type, {})
                                plan_recipe_id = slot_info.get('recipe_id')
                                if plan_recipe_id and plan_recipe_id != -1:
                                    current_recipe_id = plan_recipe_id
                        except (ValueError, TypeError):
                            flash(f"Invalid recipe ID format '{recipe_id_in_slot_str}' found for {slot_id} during lock.", "warning")
                            current_recipe_id = None

                        if current_recipe_id and current_recipe_id > 0:
                            if db.session.get(Recipe, current_recipe_id):
                                lock_info_to_set = {
                                    'recipe_id': current_recipe_id,
                                    'manual': False,
                                    'default': False
                                }
                            else:
                                flash(f"Cannot lock recipe ID {current_recipe_id} for {slot_id} - recipe not found.", "warning")

                # Update persistent lock in database
                try:
                    update_persistent_lock(slot_id, lock_info_to_set)
                except Exception as e:
                    flash(f"Error updating lock for {slot_id}: {str(e)}", "danger")
                    continue

                # Add to new_locked_meals if a lock was determined
                if lock_info_to_set:
                    new_locked_meals[slot_id] = lock_info_to_set

        # Sync session with database locks
        sync_session_locks_with_db()

        # Regenerate the meal plan
        plan_ids = generate_meal_plan(session['num_people'], session['locked_meals'])
        session['current_plan_ids'] = plan_ids
        session.modified = True

        # Clear shopping list state as the plan has changed
        session.pop('shopping_list_state', None)

        flash("Meal plan regenerated.", "success")
        return redirect(url_for('dashboard'))

    # --- GET Request Rendering ---
    # Ensure a plan exists in the session
    if 'current_plan_ids' not in session:
        session['current_plan_ids'] = generate_meal_plan(session['num_people'], session.get('locked_meals', {}))
        session.modified = True

    plan_ids_from_session: PlanIdsDict = session['current_plan_ids']

    # Fetch all unique recipe objects needed for the current plan efficiently
    all_recipe_ids_in_plan: Set[int] = {
        mi['recipe_id']
        for dp in plan_ids_from_session.values()
        for mi in dp.values()
        if mi and mi.get('recipe_id') and mi['recipe_id'] != -1 # Check existence and valid ID
    }
    recipes_in_plan_dict: Dict[int, Recipe] = {
        r.id: r for r in Recipe.query.filter(Recipe.id.in_(all_recipe_ids_in_plan)).all()
    } if all_recipe_ids_in_plan else {}

    # Prepare the plan data structure for the template
    plan_for_template = {day: {meal_type: None for meal_type in meal_types} for day in days}
    active_locked_meals_state = session.get('locked_meals', {}) # Get current lock state for template

    for day in days:
        for meal_type in meal_types:
            meal_info_ids = plan_ids_from_session.get(day, {}).get(meal_type)
            slot_id = f"{day}_{meal_type}" # Used for referencing locks in template

            # Default display info for an empty slot
            display_info = {
                'recipe': None,
                'status': 'empty',
                'locked_by_main': False,
                'is_manual_entry': False,
                'default_lock': False,
                'manual_text': None
            }

            if meal_info_ids:
                 recipe_id = meal_info_ids.get('recipe_id')
                 status = meal_info_ids.get('status', 'empty') # Default status if missing

                 # Update display info with data from the plan session state
                 display_info.update({
                     'status': status,
                     'locked_by_main': meal_info_ids.get('locked_by_main', False),
                     'default_lock': meal_info_ids.get('default_lock', False)
                 })

                 # Handle manual entry display (-1)
                 if recipe_id == -1:
                     display_info.update({
                         'manual_text': meal_info_ids.get('manual_text', 'Manual Entry'),
                         'is_manual_entry': True,
                         'status': 'locked' # Manual entries are always locked
                     })
                 # Handle regular recipe display
                 elif recipe_id is not None and recipe_id > 0:
                     # Fetch the Recipe object from our pre-fetched dictionary
                     recipe_object = recipes_in_plan_dict.get(recipe_id)
                     if recipe_object:
                         display_info['recipe'] = recipe_object
                         # Keep the status from the plan ('new', 'leftover', 'locked')
                         display_info['status'] = status
                     else:
                         # Recipe ID exists in plan, but not in DB (deleted?)
                         display_info['recipe'] = None
                         display_info['status'] = 'deleted' # Indicate missing recipe
                         # Optional: Log this inconsistency
                         app.logger.warning(f"Recipe ID {recipe_id} found in plan but not in database for slot {slot_id}.")

            plan_for_template[day][meal_type] = display_info

    # Fetch all recipes for the dropdown menu
    recipes_for_dropdown = Recipe.query.order_by(Recipe.name).all()
    # Get distinct aisles for the shopping list
    distinct_aisles = get_distinct_aisles()

    return render_template('dashboard.html',
                           plan=plan_for_template,
                           num_people=session['num_people'],
                           locked_meals=active_locked_meals_state, # Pass the raw lock state for form defaults
                           days=days,
                           meal_types=meal_types,
                           all_recipes=recipes_for_dropdown, # For dropdowns
                           distinct_aisles=distinct_aisles) # For shopping list add form


@app.route('/add', methods=['GET', 'POST'])
def add_recipe():
    # Passed to template to repopulate form on error
    current_data = request.form if request.method == 'POST' else {}

    if request.method == 'POST':
        try:
            name = request.form.get('name', '').strip()
            # Use empty string as default if method is not provided or empty
            method = request.form.get('method', '').strip()
            servings_str = request.form.get('servings', '').strip()
            ingredients_raw = request.form.get('ingredients', '').strip()
            source_link = request.form.get('source_link', '').strip() or None
            # Boolean flags from checkboxes
            is_breakfast = 'is_breakfast' in request.form
            is_lunch = 'is_lunch' in request.form
            is_dinner = 'is_dinner' in request.form

            # --- Validation ---
            errors = False
            if not name:
                flash("Recipe name is required.", "danger")
                errors = True
            if not servings_str:
                flash("Servings is required.", "danger")
                errors = True
            if not ingredients_raw:
                flash("Ingredients are required.", "danger")
                errors = True

            servings_int = None
            if servings_str:
                try:
                    servings_int = int(servings_str)
                    if servings_int <= 0:
                        flash("Servings must be a positive whole number.", "danger")
                        errors = True
                except ValueError:
                    flash("Servings must be a valid whole number.", "danger")
                    errors = True

            # Check for duplicate recipe name (case-insensitive)
            if name and Recipe.query.filter(func.lower(Recipe.name) == name.lower()).first():
                flash(f"A recipe named '{name}' already exists. Please choose a different name.", "warning")
                errors = True

            if errors:
                # Return template with errors and repopulated data
                return render_template('add_recipe.html', current_data=request.form)

            # --- Create Recipe ---
            new_recipe = Recipe(
                name=name,
                source_link=source_link,
                method=method,
                servings=servings_int, # Already validated as positive int
                is_breakfast=is_breakfast,
                is_lunch=is_lunch,
                is_dinner=is_dinner
            )
            db.session.add(new_recipe)
            # Flush session to get the new_recipe.id assigned by the database,
            # needed for linking ingredients *before* the commit.
            db.session.flush()

            # --- Process Ingredients ---
            ingredients_to_add = []
            has_valid_ingredient = False
            # Pre-fetch known aisles for efficiency if there are many ingredients
            all_ingredient_aisles = db.session.query(Ingredient.name, Ingredient.aisle)\
                                              .filter(Ingredient.aisle.isnot(None), Ingredient.aisle != '')\
                                              .distinct().all()
            known_aisles_cache = { ing_name.strip().lower(): aisle
                                   for ing_name, aisle in all_ingredient_aisles if aisle }

            for line in ingredients_raw.splitlines(): # Use splitlines() handles different line endings
                line = line.strip()
                if not line:
                    continue # Skip empty lines

                # Split line into parts based on '-'
                parts = [p.strip() for p in line.split('-', 2)]
                ing_name = parts[0]
                if not ing_name:
                    continue # Skip lines that might start with '-' or are just whitespace

                # Assign quantity and unit, defaulting to None if not provided
                ing_qty = parts[1] if len(parts) > 1 and parts[1] else None
                ing_unit = parts[2] if len(parts) > 2 and parts[2] else None

                # Attempt to find existing aisle for this ingredient name (case-insensitive)
                ing_name_lower = ing_name.lower()
                aisle = known_aisles_cache.get(ing_name_lower) # Use cache

                ingredients_to_add.append(Ingredient(
                    name=ing_name,
                    quantity=ing_qty,
                    unit=ing_unit,
                    aisle=aisle,
                    recipe_id=new_recipe.id # Link to the flushed recipe ID
                ))
                has_valid_ingredient = True

            if not has_valid_ingredient:
                # If no valid ingredients were parsed, rollback the recipe addition
                db.session.rollback()
                flash("No valid ingredients found. Each line should be 'Name - Quantity - Unit' (Quantity and Unit are optional). Recipe not added.", "danger")
                return render_template('add_recipe.html', current_data=request.form)

            # Add all valid ingredients to the session
            db.session.add_all(ingredients_to_add)
            # Commit the recipe and its ingredients together
            db.session.commit()
            flash(f"Recipe '{new_recipe.name}' added successfully.", "success")
            return redirect(url_for('dashboard'))

        except Exception as e:
            db.session.rollback() # Rollback any partial changes on unexpected error
            flash(f"An unexpected error occurred while adding the recipe: {e}", "danger")
            app.logger.error(f"Error adding recipe: {e}", exc_info=True) # Log detailed error
            # Return template with potentially repopulated data
            return render_template('add_recipe.html', current_data=request.form)

    # --- GET Request ---
    return render_template('add_recipe.html', current_data={})


@app.route('/edit_recipe/<int:recipe_id>', methods=['GET', 'POST'])
def edit_recipe(recipe_id: int):
    # Fetch the recipe or return 404. Eagerly load ingredients.
    recipe = Recipe.query.options(joinedload(Recipe.ingredients)).get_or_404(recipe_id)
    distinct_aisles = get_distinct_aisles() # For aisle dropdowns

    # Helper function to reconstruct ingredient data from form for repopulation on error
    def get_submitted_ingredients(form_data) -> List[Dict[str, Any]]:
         submitted = []
         ids = form_data.getlist('ingredient_id[]')
         names = form_data.getlist('ingredient_name[]')
         qtys = form_data.getlist('ingredient_qty[]')
         units = form_data.getlist('ingredient_unit[]')
         aisles = form_data.getlist('ingredient_aisle[]')

         max_len = max(len(ids), len(names), len(qtys), len(units), len(aisles))

         for i in range(max_len):
             name = names[i].strip() if i < len(names) else ''
             # Include row even if name is empty, to preserve structure on error page
             # Validation will catch empty required names later
             submitted.append({
                 'id': ids[i].strip() if i < len(ids) else '',
                 'name': name,
                 'quantity': qtys[i].strip() if i < len(qtys) else '',
                 'unit': units[i].strip() if i < len(units) else '',
                 # Handle 'None' string from dropdown or empty string
                 'aisle': aisles[i].strip() if i < len(aisles) and aisles[i].strip() and aisles[i] != 'None' else None
             })
         # Ensure at least one empty row if everything was deleted
         if not submitted:
             submitted.append({'id': '', 'name': '', 'quantity': '', 'unit': '', 'aisle': None})
         return submitted

    if request.method == 'POST':
        form_ingredients = [] # Initialize in case of early exit before assignment
        try:
            original_name = recipe.name
            name = request.form.get('name', '').strip()
            method = request.form.get('method', '').strip()
            servings_str = request.form.get('servings', '').strip()
            source_link = request.form.get('source_link', '').strip() or None
            is_breakfast = 'is_breakfast' in request.form
            is_lunch = 'is_lunch' in request.form
            is_dinner = 'is_dinner' in request.form

            # Get ingredient lists from the form
            ingredient_ids = request.form.getlist('ingredient_id[]')
            ingredient_names = request.form.getlist('ingredient_name[]')
            ingredient_qtys = request.form.getlist('ingredient_qty[]')
            ingredient_units = request.form.getlist('ingredient_unit[]')
            ingredient_aisles = request.form.getlist('ingredient_aisle[]')

            # --- Validation ---
            errors = False
            if not name:
                flash("Recipe name is required.", "danger")
                errors = True
            if not servings_str:
                flash("Servings is required.", "danger")
                errors = True
            # Check if at least one non-empty ingredient name was submitted
            if not any(n.strip() for n in ingredient_names):
                flash("At least one ingredient name is required.", "danger")
                errors = True

            servings_int = None
            if servings_str:
                try:
                    servings_int = int(servings_str)
                    if servings_int <= 0:
                        flash("Servings must be a positive whole number.", "danger")
                        errors = True
                except ValueError:
                    flash("Servings must be a valid whole number.", "danger")
                    errors = True

            # Check for duplicate name only if the name has changed (case-insensitive)
            if name and name.lower() != original_name.lower():
                if Recipe.query.filter(
                    func.lower(Recipe.name) == name.lower(),
                    Recipe.id != recipe_id # Exclude self
                ).first():
                    flash(f"Another recipe named '{name}' already exists.", "warning")
                    errors = True

            if errors:
                # Reconstruct form state for template
                form_ingredients = get_submitted_ingredients(request.form)
                return render_template('edit_recipe.html', recipe=recipe, form_ingredients=form_ingredients, distinct_aisles=distinct_aisles)

            # --- Update Recipe Fields ---
            recipe.name = name
            recipe.source_link = source_link
            recipe.method = method
            recipe.servings = servings_int # Validated int
            recipe.is_breakfast = is_breakfast
            recipe.is_lunch = is_lunch
            recipe.is_dinner = is_dinner

            # --- Update Ingredients ---
            # Efficiently track changes using sets and dictionaries
            existing_ingredient_ids: Set[int] = {ing.id for ing in recipe.ingredients}
            submitted_ingredient_ids: Set[int] = set()
            ingredients_to_add: List[Ingredient] = []
            ingredients_to_update: Dict[int, Dict[str, Any]] = {} # {ing_id: {data}}

            # Iterate through submitted ingredient data
            max_len = max(len(ingredient_ids), len(ingredient_names), len(ingredient_qtys), len(ingredient_units), len(ingredient_aisles))
            for i in range(max_len):
                name_val = ingredient_names[i].strip() if i < len(ingredient_names) else ''
                # Skip rows where the name is empty (usually indicates deletion or empty new row)
                if not name_val:
                    continue

                current_id: Optional[int] = None
                try:
                    current_id_str = ingredient_ids[i].strip() if i < len(ingredient_ids) else ''
                    if current_id_str.isdigit():
                        current_id = int(current_id_str)
                except IndexError:
                    current_id = None # Should not happen with max_len, but safe check

                # Get other fields safely
                qty_val = ingredient_qtys[i].strip() if i < len(ingredient_qtys) and ingredient_qtys[i].strip() else None
                unit_val = ingredient_units[i].strip() if i < len(ingredient_units) and ingredient_units[i].strip() else None
                aisle_val = ingredient_aisles[i].strip() if i < len(ingredient_aisles) and ingredient_aisles[i].strip() and ingredient_aisles[i] != 'None' else None

                data = {
                    'name': name_val,
                    'quantity': qty_val,
                    'unit': unit_val,
                    'aisle': aisle_val,
                    'recipe_id': recipe.id # Link to parent recipe
                }

                # Check if it's an existing ingredient being updated
                if current_id and current_id in existing_ingredient_ids:
                    submitted_ingredient_ids.add(current_id)
                    ingredients_to_update[current_id] = data
                # Check if it's a new ingredient (no ID or ID not in existing set)
                # We only add if the name is non-empty (checked earlier)
                elif not current_id or current_id not in existing_ingredient_ids:
                     # Create a new Ingredient object, don't include 'id'
                     ingredients_to_add.append(Ingredient(**data))

            # --- Process Deletions ---
            ids_to_delete = existing_ingredient_ids - submitted_ingredient_ids
            if ids_to_delete:
                # Delete ingredients that were present before but not submitted now
                # Using synchronize_session='fetch' might be okay for smaller deletes
                # For large deletes, 'fetch' can be slow; 'evaluate' might be faster but requires caution.
                Ingredient.query.filter(Ingredient.id.in_(ids_to_delete)).delete(synchronize_session='fetch')

            # --- Process Updates ---
            for ing_id, data in ingredients_to_update.items():
                 # Fetch the specific ingredient to update
                 ing = db.session.get(Ingredient, ing_id)
                 if ing: # Ensure it still exists
                     ing.name = data['name']
                     ing.quantity = data['quantity']
                     ing.unit = data['unit']
                     ing.aisle = data['aisle']
                 else:
                     app.logger.warning(f"Ingredient ID {ing_id} marked for update but not found in session/DB.")


            # --- Process Additions ---
            if ingredients_to_add:
                db.session.add_all(ingredients_to_add)

            # --- Commit Changes ---
            db.session.commit()
            flash(f"Recipe '{recipe.name}' updated successfully.", "success")
            # Clear potentially stale shopping list
            session.pop('shopping_list_state', None)
            return redirect(url_for('dashboard'))

        except Exception as e:
             db.session.rollback() # Rollback on any error during processing
             flash(f"An unexpected error occurred while updating the recipe: {e}", "danger")
             app.logger.error(f"Error updating recipe {recipe_id}: {e}", exc_info=True)
             # Reconstruct form state for template on error
             form_ingredients = get_submitted_ingredients(request.form)
             return render_template('edit_recipe.html', recipe=recipe, form_ingredients=form_ingredients, distinct_aisles=distinct_aisles)

    else: # --- GET Request ---
        # Populate form_ingredients from the loaded recipe's ingredients
        form_ingredients = [
            {'id': ing.id, 'name': ing.name, 'quantity': ing.quantity or '', 'unit': ing.unit or '', 'aisle': ing.aisle}
            for ing in recipe.ingredients
        ]
        # Ensure at least one (potentially empty) row for the template's add functionality
        if not form_ingredients:
            form_ingredients.append({'id': '', 'name': '', 'quantity': '', 'unit': '', 'aisle': None})

    return render_template('edit_recipe.html', recipe=recipe, form_ingredients=form_ingredients, distinct_aisles=distinct_aisles)


@app.route('/view_recipe/<int:recipe_id>')
def view_recipe(recipe_id: int):
    # Use get_or_404 for robust fetching by ID
    recipe = Recipe.query.options(joinedload(Recipe.ingredients)).get_or_404(recipe_id)
    return render_template('view_recipe.html', recipe=recipe)

@app.route('/delete_recipe/<int:recipe_id>', methods=['POST'])
def delete_recipe(recipe_id: int):
    # Ensure recipe exists before attempting deletion
    recipe = Recipe.query.get_or_404(recipe_id)
    recipe_name = recipe.name # Store name for flash message

    try:
        # --- IMPORTANT: Clean up session references BEFORE deleting ---
        # 1. Remove any locks associated with this recipe ID
        locked_meals: LockedMealsDict = session.get('locked_meals', {})
        keys_to_remove = [
            k for k, v in locked_meals.items()
            if isinstance(v, dict) and v.get('recipe_id') == recipe_id
        ]
        if keys_to_remove:
            for key in keys_to_remove:
                if key in locked_meals:
                    del locked_meals[key]
            session['locked_meals'] = locked_meals
            session.modified = True
            flash(f"Removed associated meal locks for deleted recipe '{recipe_name}'.", "info")

        # 2. Remove recipe ID from the current meal plan in the session
        if 'current_plan_ids' in session:
            plan_ids: PlanIdsDict = session['current_plan_ids']
            plan_changed = False
            for day in plan_ids:
                 for meal_type in plan_ids[day]:
                     # Check if the slot exists and contains the recipe being deleted
                     if plan_ids[day][meal_type] and plan_ids[day][meal_type].get('recipe_id') == recipe_id:
                         # Reset the slot to empty (or None)
                         plan_ids[day][meal_type] = None
                         plan_changed = True
            if plan_changed:
                session['current_plan_ids'] = plan_ids
                session.modified = True
                flash(f"Removed '{recipe_name}' from the current meal plan.", "info")

        # 3. Clear potentially stale shopping list state
        session.pop('shopping_list_state', None)

        # --- Perform Deletion ---
        # Ingredients associated via relationship with cascade="all, delete-orphan"
        # should be deleted automatically by SQLAlchemy when the recipe is deleted.
        db.session.delete(recipe)
        db.session.commit()
        flash(f"Recipe '{recipe_name}' and its ingredients deleted successfully.", "success")

    except Exception as e:
        db.session.rollback()
        flash(f"Error deleting recipe '{recipe_name}': {e}", "danger")
        app.logger.error(f"Error deleting recipe {recipe_id}: {e}", exc_info=True)

    return redirect(url_for('dashboard'))


@app.route('/shopping_list', methods=['GET', 'POST'])
def shopping_list():
    # Ensure shopping list state exists in session
    if 'shopping_list_state' not in session:
        # Initialize with empty removed dict and custom items list
        session['shopping_list_state'] = {'removed': {}, 'custom_items': []}
        session.modified = True
    list_state = session['shopping_list_state']
    distinct_aisles = get_distinct_aisles() # For add custom item form

    if request.method == 'POST':
        # This POST handler now focuses on adding custom items
        # Re-adding items is primarily handled via the AJAX endpoint '/move_shopping_item'
        # but keep the form-based re-add as a fallback for non-JS scenarios if needed.

        # --- Fallback Re-add from Form Submit (if JS fails) ---
        readd_items_norm_names = request.form.getlist('readd_item')
        removed_dict = list_state.setdefault('removed', {})
        readded_count = 0
        if readd_items_norm_names:
            for norm_name in readd_items_norm_names:
                 if norm_name in removed_dict:
                     del removed_dict[norm_name]
                     readded_count += 1
            if readded_count > 0:
                 flash(f"Re-added {readded_count} item(s) to the shopping list.", "info")


        # --- Add New Custom Item ---
        custom_item_name = request.form.get('custom_item_name', '').strip()
        # Get aisle, treat empty string or 'None' as None
        custom_item_aisle_raw = request.form.get('custom_item_aisle', '').strip()
        custom_item_aisle = custom_item_aisle_raw if custom_item_aisle_raw and custom_item_aisle_raw != 'None' else None

        if custom_item_name:
             norm_custom_name = custom_item_name.lower()
             custom_items_list: List[Dict[str, Any]] = list_state.setdefault('custom_items', [])

             # Check if custom item (case-insensitive) already exists in the custom list
             exists = any(item['name'].strip().lower() == norm_custom_name for item in custom_items_list)

             if not exists:
                 # If aisle wasn't provided, try to infer it from existing Ingredients
                 if not custom_item_aisle:
                     # Query only if needed
                     existing_ing = db.session.query(Ingredient.aisle)\
                         .filter(func.lower(Ingredient.name) == norm_custom_name, Ingredient.aisle.isnot(None), Ingredient.aisle != '')\
                         .first()
                     if existing_ing:
                         custom_item_aisle = existing_ing.aisle
                 # Append the new custom item
                 custom_items_list.append({'name': custom_item_name, 'aisle': custom_item_aisle})
                 list_state['custom_items'] = custom_items_list # Ensure update
                 flash(f"Added custom item '{custom_item_name}' to the shopping list.", "success")
             else:
                 flash(f"Custom item '{custom_item_name}' already exists in the shopping list.", "warning")
        elif request.form.get('submit_custom'): # Check if the custom add button was pressed specifically
            flash("Please enter a name for the custom item.", "warning")


        # Save changes to session
        session['shopping_list_state'] = list_state
        session.modified = True
        return redirect(url_for('shopping_list')) # Redirect after POST

    # --- GET Request ---
    # Generate the shopping list data based on the current plan and session state
    plan_ids: PlanIdsDict = session.get('current_plan_ids', {})
    shopping_list_data_by_aisle: ShoppingListDict = generate_shopping_list_data(plan_ids)

    # Get pantry items for display (potentially showing stock levels)
    pantry_items_dict = get_pantry_items()

    # Prepare removed items for display, sorted alphabetically
    removed_items_display = sorted(
        list(list_state.get('removed', {}).values()),
        key=lambda x: x.get('name', '').lower()
    )

    return render_template('shopping_list.html',
                           shopping_list=shopping_list_data_by_aisle,
                           removed_items=removed_items_display,
                           pantry_items=pantry_items_dict, # Pass pantry items
                           distinct_aisles=distinct_aisles) # For add custom dropdown


@app.route('/move_shopping_item', methods=['POST'])
def move_shopping_item():
    """AJAX endpoint to move items between 'active' and 'removed' states in the session."""
    if not request.is_json:
        app.logger.warning("Received non-JSON request at /move_shopping_item")
        return jsonify(success=False, error="Invalid request format, JSON expected."), 400

    data = request.get_json()
    norm_name = data.get('norm_name') # Normalized name acts as the key
    is_checked = data.get('isChecked') # Boolean: True means moving TO removed, False means moving FROM removed
    item_data = data.get('item_data', {}) # Additional data about the item from the client

    if not norm_name:
        app.logger.warning("Missing 'norm_name' in request to /move_shopping_item")
        return jsonify(success=False, error="Missing item identifier ('norm_name')."), 400

    # Ensure session state structure exists
    if 'shopping_list_state' not in session:
        session['shopping_list_state'] = {'removed': {}, 'custom_items': []}
    list_state = session['shopping_list_state']
    # Use setdefault to ensure 'removed' key exists and get the dictionary
    removed_items_dict = list_state.setdefault('removed', {})

    # Data to potentially send back to the client JS for UI updates
    item_data_for_client: Optional[Dict[str, Any]] = None

    if is_checked: # --- Moving item TO removed list ---
        if norm_name not in removed_items_dict:
            # Store essential data needed to display the item in the "removed" section
            # and potentially re-add it later. Get data from what JS sent.
            item_data_for_client = {
                'name': item_data.get('name', norm_name.capitalize()), # Display name
                'normalized_name': norm_name, # Key
                'aisle': item_data.get('aisle', 'Unknown'),
                'is_custom': item_data.get('is_custom', False),
                # Store index if it's a custom item, might be useful for re-adding logic
                'custom_item_index': item_data.get('custom_index') if item_data.get('is_custom') else None,
                # Store display quantity/unit for context in removed list
                'display_quantity': item_data.get('display_quantity', ''),
                'unit': item_data.get('unit', '')
            }
            removed_items_dict[norm_name] = item_data_for_client
            action = "removed"
        else:
            # Item already in removed dict, likely a double-click or race condition
            action = "already_removed"
            item_data_for_client = removed_items_dict.get(norm_name) # Send back existing data

    else: # --- Moving item FROM removed list (Re-adding) ---
        if norm_name in removed_items_dict:
            # Pop the item from removed dict; pop returns the removed item's data.
            item_data_for_client = removed_items_dict.pop(norm_name, None)
            action = "readded"
        else:
            # Item not found in removed dict, cannot re-add
            action = "not_found_in_removed"
            item_data_for_client = None


    # Save the modified state back to the session
    list_state['removed'] = removed_items_dict # Ensure the updated dict is saved
    session['shopping_list_state'] = list_state
    session.modified = True

    # Send back success status and the data of the item that was moved (or info about it)
    # This allows the frontend JS to update the UI accordingly (e.g., move the item element)
    return jsonify(success=True, action=action, item_data=item_data_for_client)


@app.route('/manage_aisles', methods=['GET', 'POST'])
def manage_aisles():
    distinct_aisles_options = get_distinct_aisles() # For dropdown options

    if request.method == 'POST':
        items_updated: Set[str] = set() # Track names of ingredients successfully updated
        errors: List[str] = [] # Collect potential errors

        # Iterate through all submitted form data items
        for key, new_aisle_value in request.form.items():
            # Process only keys related to aisle inputs
            if key.startswith('aisle_'):
                # Extract original ingredient name (key is 'aisle_<ingredient_name>')
                # The name might contain spaces or special characters, handle as is.
                ingredient_name = key[len('aisle_'):]
                # Get the original aisle value submitted via hidden input
                original_aisle_key = f'original_aisle_{ingredient_name}'
                original_aisle = request.form.get(original_aisle_key) # This might be 'None' string or actual aisle

                # Clean the submitted new aisle value
                new_aisle = new_aisle_value.strip() or None # Treat empty string as None

                # Convert 'None' string from hidden input back to None type for comparison
                original_aisle_comp = None if original_aisle == 'None' else original_aisle

                # --- Update only if the aisle value has actually changed ---
                if new_aisle != original_aisle_comp:
                    try:
                        # Prepare for case-insensitive update
                        ing_name_to_update_lower = ingredient_name.lower()
                        update_data = {'aisle': new_aisle}

                        # Update all matching Ingredients (case-insensitive)
                        # synchronize_session=False is efficient but means session objects are stale.
                        # This is generally okay if we redirect immediately after.
                        ing_updated_count = Ingredient.query.filter(func.lower(Ingredient.name) == ing_name_to_update_lower)\
                                                            .update(update_data, synchronize_session=False)

                        # Update all matching PantryItems (case-insensitive)
                        pan_updated_count = PantryItem.query.filter(func.lower(PantryItem.name) == ing_name_to_update_lower)\
                                                            .update(update_data, synchronize_session=False)

                        # If any rows were affected in either table, record the update
                        if ing_updated_count > 0 or pan_updated_count > 0:
                            items_updated.add(ingredient_name) # Use original name for reporting

                    except Exception as e:
                        # Collect errors for this specific ingredient
                        db.session.rollback() # Rollback immediately on error for safety? Or collect all first?
                                              # Let's collect first, rollback at the end if any error occurred.
                        error_msg = f"Error updating aisle for '{ingredient_name}': {e}"
                        errors.append(error_msg)
                        app.logger.error(error_msg, exc_info=True)
                        # Stop processing further updates for this item if an error occurred
                        # (though the loop will continue for others)


        # --- Finalize Transaction (Commit or Rollback) ---
        if errors:
            db.session.rollback() # Rollback all changes if any error occurred during the process
            for error in errors:
                flash(error, "danger")
            flash("No changes were saved due to errors.", "warning")
        elif items_updated:
             # If there were no errors and at least one item was changed, commit.
             try:
                 db.session.commit() # Commit all successful updates together
                 updated_names_str = ", ".join(sorted(list(items_updated)))
                 flash(f"Successfully updated aisles for {len(items_updated)} ingredient(s): {updated_names_str}.", "success")
                 # Clear shopping list state as aisles might affect sorting/grouping
                 session.pop('shopping_list_state', None)
             except Exception as e:
                 db.session.rollback() # Rollback on commit error
                 flash(f"Error committing aisle updates: {e}", "danger")
                 app.logger.error(f"Error committing aisle updates: {e}", exc_info=True)
        else:
             # No errors and no items were actually changed
             flash("No aisle changes detected or submitted.", "info")

        return redirect(url_for('manage_aisles'))

    # --- GET Request ---
    # Query distinct ingredient names and their *latest* associated aisle for editing.
    # Using ROW_NUMBER() partitioned by lowercased name, ordered by ID desc,
    # ensures we get the aisle from the most recently added/edited ingredient instance.
    subq = db.session.query(
        Ingredient.name,
        Ingredient.aisle,
        func.row_number().over(
            partition_by=func.lower(Ingredient.name), # Group by normalized name
            order_by=Ingredient.id.desc()             # Get the latest entry first
        ).label('rn') # Assign alias 'rn' to the row number
    ).subquery() # Create a subquery

    # Select name and aisle from the subquery where row number is 1 (the latest)
    distinct_ingredients_q = db.session.query(subq.c.name, subq.c.aisle)\
                                    .filter(subq.c.rn == 1)\
                                    .order_by(func.lower(subq.c.name))\
                                    .all() # Sort results case-insensitively by name

    # Prepare data for the template
    ingredients_for_template = [
        {'name': name, 'aisle': aisle} for name, aisle in distinct_ingredients_q
    ]

    return render_template('manage_aisles.html',
                           ingredients=ingredients_for_template,
                           distinct_aisles=distinct_aisles_options)


@app.route('/cupboard', methods=['GET', 'POST'])
def cupboard():
    """Manages the Pantry (Cupboard) items."""
    distinct_aisles_options = get_distinct_aisles() # For add/edit form

    if request.method == 'POST':
        delete_id_str = request.form.get('delete_id')
        add_name = request.form.get('add_name', '').strip()
        add_qty = request.form.get('add_qty', '').strip()
        add_unit = request.form.get('add_unit', '').strip()
        # Get aisle, treat empty or 'None' as None
        add_aisle_raw = request.form.get('add_aisle', '').strip()
        add_aisle = add_aisle_raw if add_aisle_raw and add_aisle_raw != 'None' else None

        if delete_id_str:
            # --- Handle Deletion ---
            try:
                delete_id = int(delete_id_str)
                remove_from_pantry(delete_id) # Use helper function
            except ValueError:
                flash("Invalid ID provided for deletion.", "danger")
        elif add_name:
             # --- Handle Add/Update ---
             # If aisle is not provided, try to inherit from Ingredient table
             if not add_aisle:
                 existing_ing = db.session.query(Ingredient.aisle)\
                     .filter(func.lower(Ingredient.name) == add_name.lower(), Ingredient.aisle.isnot(None), Ingredient.aisle != '')\
                     .first()
                 if existing_ing:
                     add_aisle = existing_ing.aisle
                     flash(f"Inherited aisle '{add_aisle}' for '{add_name}' from ingredients.", "info")

             # Use helper function to add or update the pantry item
             update_pantry(add_name, add_qty, add_unit, add_aisle)
             # Clear shopping list state as pantry changes affect it
             session.pop('shopping_list_state', None)
        # Allow updating existing items via the add form (update_pantry handles this)
        # Check if it was an 'add' attempt specifically without a name
        elif request.form.get('submit_add'):
             flash("Item name is required to add or update an item in the pantry.", "warning")

        return redirect(url_for('cupboard')) # Redirect after POST

    # --- GET Request ---
    # Fetch all pantry items, ordered for predictable display (Aisle, then Name)
    pantry_items_list = PantryItem.query.order_by(PantryItem.aisle.asc().nullslast(), func.lower(PantryItem.name)).all()

    # Group items by aisle for template rendering
    pantry_by_aisle: Dict[str, List[PantryItem]] = defaultdict(list)
    aisle_order = ["Produce", "Meat", "Dairy", "Bakery", "Frozen", "Pantry", "Canned Goods", "Spices", "Drinks", "Household", "Misc", "Unknown"]
    aisle_order_map = {a: i for i, a in enumerate(aisle_order)}

    for item in pantry_items_list:
        # Group by aisle, treating None aisle as "Unknown"
        aisle_key = item.aisle or 'Unknown'
        pantry_by_aisle[aisle_key].append(item)

    # Sort the aisles based on the preferred order, then alphabetically
    sorted_aisle_keys = sorted(
        pantry_by_aisle.keys(),
        key=lambda a: (aisle_order_map.get(a, 999), a) # Use 999 for unknown/other aisles
    )

    # Create the final sorted structure for the template
    # Items within each aisle are already sorted by name due to the initial query order
    sorted_pantry: Dict[str, List[PantryItem]] = {
        aisle: pantry_by_aisle[aisle] for aisle in sorted_aisle_keys
    }

    return render_template('cupboard.html',
                           pantry_items=sorted_pantry,
                           distinct_aisles=distinct_aisles_options)

# --- Main Execution ---
if __name__ == '__main__':
    # Create database tables if they don't exist.
    # Needs the application context.
    with app.app_context():
        # Check if the database file exists before creating tables
        # This is a simple check; migrations are better for managing changes.
        if not os.path.exists(DATABASE_PATH):
            print("Database file not found, creating tables...")
            db.create_all()
            print("Tables created.")
        else:
            print("Database file found.")
            # Consider running migrations here if using Flask-Migrate extensively
            # Example: upgrade() from flask_migrate import upgrade; upgrade()

    # Run the Flask development server
    # host='0.0.0.0' makes it accessible on your network
    # debug=True enables interactive debugger and auto-reloading (DISABLE IN PRODUCTION)
    print("Starting Flask development server...")
    app.run(host='0.0.0.0', port=5000, debug=True) # Set debug=False for production!