from typing import Dict, Any, Optional, List, Tuple, Set
from decimal import Decimal
import math
import random
from flask import session, flash, jsonify, current_app
from flask_login import current_user
from sqlalchemy.sql import func

from . import db, meal_types
from .models import PantryItem, Recipe, LockedMeal, ShoppingListItem

# Type aliases for meal plan structures
MealInfoDict = Dict[str, Any]  # Holds recipe_id, status, locks etc.
DayPlanDict = Dict[str, Optional[MealInfoDict]]  # meal_type -> MealInfoDict
PlanIdsDict = Dict[str, DayPlanDict]  # day_name -> DayPlanDict
LockedMealsDict = Dict[str, Dict[str, Any]]  # slot_id -> lock_info_dict
Coords = Tuple[int, str]  # (day_index, meal_type)

# Pantry helpers

def get_pantry_items() -> Dict[str, PantryItem]:
    items = PantryItem.query.all()
    return {item.name.strip().lower(): item for item in items}

def update_pantry(item_name: str, quantity: str, unit: str, aisle: Optional[str] = None) -> None:
    normalized_name = item_name.strip().lower()
    pantry_item = PantryItem.query.filter(func.lower(PantryItem.name) == normalized_name).first()
    if pantry_item:
        pantry_item.quantity = quantity.strip() if quantity else None
        pantry_item.unit = unit.strip() if unit else None
        pantry_item.aisle = aisle.strip() if aisle else None
        flash(f"Updated '{pantry_item.name}' in pantry.", "info")
    else:
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
        current_app.logger.error(f"Error updating pantry item '{item_name}': {e}")

def generate_meal_plan(num_people: int, locked_meals: LockedMealsDict, days: Optional[List[str]] = None) -> PlanIdsDict:
    """
    Generates a meal plan for the specified days, considering locked meals and user default settings for each meal type.
    If days is None, defaults to all 7 days (Monday-Sunday).
    """
    if days is None:
        days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    plan_ids: PlanIdsDict = {day: {meal_type: None for meal_type in meal_types} for day in days}

    # Fetch user default meal settings
    account = current_user.accounts.first()
    settings = getattr(account, 'settings', None)
    default_breakfast_id = getattr(settings, 'default_breakfast_id', None)
    default_lunch_id = getattr(settings, 'default_lunch_id', None)
    default_dinner_id = getattr(settings, 'default_dinner_id', None)

    # Apply defaults for each meal type if not locked
    for day in days:
        for meal_type in meal_types:
            slot_id = f"{day}_{meal_type}"
            if slot_id not in locked_meals:
                if meal_type == 'Breakfast' and default_breakfast_id:
                    plan_ids[day][meal_type] = {
                        'recipe_id': int(default_breakfast_id),
                        'status': 'locked',
                        'locked_by_main': False,
                        'default_lock': True
                    }
                elif meal_type == 'Lunch' and default_lunch_id:
                    plan_ids[day][meal_type] = {
                        'recipe_id': int(default_lunch_id),
                        'status': 'locked',
                        'locked_by_main': False,
                        'default_lock': True
                    }
                elif meal_type == 'Dinner' and default_dinner_id:
                    plan_ids[day][meal_type] = {
                        'recipe_id': int(default_dinner_id),
                        'status': 'locked',
                        'locked_by_main': False,
                        'default_lock': True
                    }
    # (rest of the original function logic for locked meals and random assignments follows...)

    # Handle locked meals from session
    active_locks = {}  # (Coords) -> recipe_id
    additional_locks = {}  # For leftovers
    leftovers_to_assign = {}  # For leftovers
    for slot_id, lock_info in locked_meals.items():
        try:
            day, meal_type = slot_id.split('_', 1)
            if day not in days or meal_type not in meal_types:
                current_app.logger.warning(f"Invalid slot_id format in locked_meals: {slot_id}")
                continue  # Skip malformed slot_id
            current_coords = (days.index(day), meal_type)
        except Exception:
            current_app.logger.warning(f"Invalid slot_id format in locked_meals: {slot_id}")
            continue  # Skip malformed slot_id

        if isinstance(lock_info, dict) and 'recipe_id' in lock_info:
            recipe_id = lock_info['recipe_id']
            # Handle manual entry lock (-1)
            if recipe_id == -1:
                active_locks[current_coords] = -1
                plan_ids[day][meal_type] = {
                    'recipe_id': -1,
                    'manual_text': lock_info.get('text', 'Manual Entry'),
                    'status': 'locked',
                    'locked_by_main': True  # User explicitly set this
                }
            elif recipe_id is not None:
                # Check if the locked recipe actually exists in the DB
                if db.session.get(Recipe, recipe_id):
                    active_locks[current_coords] = recipe_id
                    plan_ids[day][meal_type] = {
                        'recipe_id': recipe_id,
                        'status': 'locked',
                        'locked_by_main': True,  # User explicitly locked this
                        'default_lock': False  # Overrides default if applicable
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
                    # Note: This check happens *after* the source meal is assigned,
                    # considering any user locks present for that source slot.
                    if is_source_locked_by_user:
                        additional_locks[current_slot_coords] = leftover_info['recipe_id']
                else:
                    # Source recipe deleted? Log or handle as needed. Leave slot empty for now.
                    current_app.logger.warning(f"Recipe ID {leftover_info['recipe_id']} for leftover assignment at {current_slot_coords} not found.")
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
                 current_app.logger.error(f"Error calculating leftovers for recipe {chosen_recipe.id} (servings: {chosen_recipe.servings}, num_people: {num_people}): {e}")
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
                current_app.logger.warning(f"Recipe ID {leftover_info['recipe_id']} for final leftover assignment at {leftover_coords} not found.")
                plan_ids[day_n][meal_t] = None # Ensure slot remains empty

    return plan_ids
