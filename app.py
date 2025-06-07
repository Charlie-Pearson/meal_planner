# meal_planner/app.py

# --- Standard Library Imports ---
import os
import random
import math
from collections import defaultdict
from decimal import Decimal, InvalidOperation
from typing import Dict, Any, List, Optional, Set, Tuple # Added for type hints
from datetime import datetime, timedelta, UTC
import re
import socket
import time
import json
import uuid
from functools import wraps
from pathlib import Path

# --- Third-Party Imports ---
from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify, abort, send_file
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.sql import func
from sqlalchemy.orm import joinedload, aliased # Explicit import for clarity
from flask_migrate import Migrate
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from flask_wtf.csrf import CSRFProtect
from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, SubmitField, SelectField
from wtforms.validators import DataRequired, Email
import bcrypt
from werkzeug.security import generate_password_hash, check_password_hash
from flask_socketio import SocketIO, emit, join_room, leave_room
from sqlalchemy import or_, and_, func, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.sql import exists

# --- Forms ---
class LoginForm(FlaskForm):
    email = StringField('Email', validators=[DataRequired(), Email()])
    password = PasswordField('Password', validators=[DataRequired()])
    submit = SubmitField('Login')

class InviteUserForm(FlaskForm):
    email = StringField('Email', validators=[DataRequired(), Email()])
    role = SelectField('Role', choices=[('user', 'User'), ('admin', 'Admin')], default='user')
    submit = SubmitField('Send Invitation')

# --- Configuration ---
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
DATABASE_PATH = os.path.join(BASE_DIR, 'database.db')

# --- Flask App Initialization ---
import logging
app = Flask(__name__)
app.logger.setLevel(logging.DEBUG)
# Use environment variable for secret key if available, otherwise use a default value
app.secret_key = os.environ.get('FLASK_SECRET_KEY', 'your-secret-key-here')
app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{DATABASE_PATH}'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False # Good practice

# Initialize CSRF protection
csrf = CSRFProtect(app)

# Initialize SocketIO
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading')

# --- Global Constants ---
ALL_DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
meal_types = ["Breakfast", "Lunch", "Dinner"]

# --- Database and Migration Initialization ---
db = SQLAlchemy(app)
migrate = Migrate(app, db)

# --- Login Manager Initialization ---
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'
login_manager.login_message = 'Please log in to access this page.'
login_manager.login_message_category = 'info'

@login_manager.user_loader
def load_user(user_id):
    """Load user by ID."""
    return User.query.get(int(user_id))

# --- Database Models ---
# NOTE: Storing quantity as String is not ideal for calculations but kept due to constraints.
# Consider migrating to db.Numeric or db.Float if DB changes are allowed later.

# User and Account Models
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(128))
    name = db.Column(db.String(100), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_login = db.Column(db.DateTime)
    is_active = db.Column(db.Boolean, default=True)
    
    # Update relationship to use back_populates and overlaps
    accounts = db.relationship('Account', secondary='account_user', 
                             back_populates='users',
                             lazy='dynamic',
                             overlaps="account_users,user")
    account_users = db.relationship('AccountUser', back_populates='user',
                                  overlaps="accounts,account")
    
    def set_password(self, password):
        salt = bcrypt.gensalt()
        self.password_hash = bcrypt.hashpw(password.encode('utf-8'), salt).decode('utf-8')
        
    def check_password(self, password):
        return bcrypt.checkpw(password.encode('utf-8'), self.password_hash.encode('utf-8'))

class Account(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    is_active = db.Column(db.Boolean, default=True)
    users = db.relationship('User', secondary='account_user', 
                          back_populates='accounts',
                          lazy='dynamic',
                          overlaps="account_users,account")
    account_users = db.relationship('AccountUser', back_populates='account',
                                  overlaps="users,user")
    
    def __init__(self, name):
        self.name = name
        self.settings = AccountSettings(account=self)

class AccountUser(db.Model):
    __tablename__ = 'account_user'
    id = db.Column(db.Integer, primary_key=True)
    account_id = db.Column(db.Integer, db.ForeignKey('account.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    role = db.Column(db.String(20), nullable=False, default='member')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Update relationships to use back_populates and overlaps
    account = db.relationship('Account', back_populates='account_users',
                            overlaps="users")
    user = db.relationship('User', back_populates='account_users',
                          overlaps="accounts")
    
    # Add unique constraint
    __table_args__ = (
        db.UniqueConstraint('account_id', 'user_id', name='uix_account_user'),
    )

class Invitation(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    account_id = db.Column(db.Integer, db.ForeignKey('account.id'), nullable=False)
    email = db.Column(db.String(120), nullable=False)
    token = db.Column(db.String(100), unique=True, nullable=False)
    created_by = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    expires_at = db.Column(db.DateTime, nullable=False)
    is_used = db.Column(db.Boolean, default=False, nullable=False)
    role = db.Column(db.String(20), nullable=False, default='user')
    
    # Add relationship to the user who created the invitation
    invited_by = db.relationship('User', foreign_keys=[created_by], backref=db.backref('invitations_sent', lazy='dynamic'))
    
    def __repr__(self):
        return f'<Invitation {self.email} to {self.account_id}>'

# Existing Models
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
    
    # New fields for account and privacy
    account_id = db.Column(db.Integer, db.ForeignKey('account.id'), nullable=True)
    is_public = db.Column(db.Boolean, default=False, nullable=False)
    created_by = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    def __repr__(self):
        return f'<Recipe {self.name}>'

class Ingredient(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    quantity = db.Column(db.String(50))
    unit = db.Column(db.String(50))
    aisle = db.Column(db.String(50))
    recipe_id = db.Column(db.Integer, db.ForeignKey('recipe.id'), nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __repr__(self):
        return f'<Ingredient {self.name} for Recipe {self.recipe_id}>'

class PantryItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    quantity = db.Column(db.String(50))
    unit = db.Column(db.String(50))
    aisle = db.Column(db.String(50))
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __repr__(self):
        return f'<PantryItem {self.name}>'

class LockedMeal(db.Model):
    """Model for storing locked meals in the database."""
    id = db.Column(db.Integer, primary_key=True)
    day = db.Column(db.String(10), nullable=False)
    meal_type = db.Column(db.String(20), nullable=False)
    recipe_id = db.Column(db.Integer, db.ForeignKey('recipe.id'), nullable=True)
    manual_text = db.Column(db.String(200), nullable=True)
    is_manual = db.Column(db.Boolean, default=False)
    is_default = db.Column(db.Boolean, default=False)
    lock_type = db.Column(db.String(20), default='user')  # Add lock_type field with default 'user'
    
    __table_args__ = (
        db.UniqueConstraint('day', 'meal_type', name='unique_day_meal'),
    )

    def __repr__(self):
        return f'<LockedMeal {self.day} {self.meal_type}>'

class AccountSettings(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    account_id = db.Column(db.Integer, db.ForeignKey('account.id'), nullable=False)
    num_people = db.Column(db.Integer, default=1)
    meal_plan_start_day = db.Column(db.String(10), default='Monday')  # Monday, Tuesday, etc.
    meal_plan_duration = db.Column(db.Integer, default=7)  # Number of days
    meal_repeat_interval = db.Column(db.Integer, default=0)  # 0 means no restriction, otherwise number of days
    default_breakfast_id = db.Column(db.Integer, db.ForeignKey('recipe.id'))
    default_lunch_id = db.Column(db.Integer, db.ForeignKey('recipe.id'))
    default_dinner_id = db.Column(db.Integer, db.ForeignKey('recipe.id'))
    
    # Relationships
    account = db.relationship('Account', backref=db.backref('settings', uselist=False))
    default_breakfast = db.relationship('Recipe', foreign_keys=[default_breakfast_id])
    default_lunch = db.relationship('Recipe', foreign_keys=[default_lunch_id])
    default_dinner = db.relationship('Recipe', foreign_keys=[default_dinner_id])

class ShoppingListItem(db.Model):
    """Model for storing shopping list items."""
    id = db.Column(db.Integer, primary_key=True)
    account_id = db.Column(db.Integer, db.ForeignKey('account.id'), nullable=False)
    name = db.Column(db.String(100), nullable=False)
    quantity = db.Column(db.Float)
    unit = db.Column(db.String(20))
    aisle = db.Column(db.String(50))
    is_checked = db.Column(db.Boolean, default=False, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'quantity': self.quantity,
            'unit': self.unit,
            'aisle': self.aisle,
            'is_checked': self.is_checked,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }


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
            'default': lock.is_default,
            'lock_type': lock.lock_type
        }
        if lock.manual_text:
            lock_info['text'] = lock.manual_text
        
        app.logger.debug(f"Retrieved lock from DB: {slot_id} - recipe_id: {lock_info['recipe_id']}, manual: {lock_info['manual']}, default: {lock_info['default']}, lock_type: {lock_info['lock_type']}")
        locks[slot_id] = lock_info
    
    app.logger.info(f"Retrieved {len(locks)} persistent locks from database")
    return locks

def update_persistent_lock(slot_id: str, lock_info: Optional[Dict[str, Any]]) -> None:
    """
    Update the persistent lock for a meal slot in the database.

    Args:
        slot_id: The slot identifier (e.g., 'Monday_Breakfast')
        lock_info: Dictionary containing lock information or None to remove the lock
    """
    try:
        day, meal_type = slot_id.split('_')
        
        # Remove any existing locks for this slot
        LockedMeal.query.filter_by(day=day, meal_type=meal_type).delete()
        
        if lock_info:
            # Create new lock with lock type information
            new_lock = LockedMeal(
                day=day,
                meal_type=meal_type,
                recipe_id=lock_info.get('recipe_id'),
                # Persist manual text using the same key used in the session
                manual_text=lock_info.get('text'),
                is_manual=lock_info.get('manual', False),
                is_default=lock_info.get('default', False),
                lock_type=lock_info.get('lock_type', 'user')  # Add lock type with default 'user'
            )
            db.session.add(new_lock)
            
        db.session.commit()
        app.logger.info(f"Updated persistent lock for {slot_id}: {lock_info}")
    except Exception as e:
        db.session.rollback()
        app.logger.error(f"Error updating persistent lock for {slot_id}: {str(e)}", exc_info=True)
        raise

def sync_session_locks_with_db() -> None:
    """Sync session locks with database locks."""
    db_locks = get_persistent_locks()
    app.logger.info(f"Syncing session locks with database. Found {len(db_locks)} locks in database.")
    # Update session with database locks
    session['locked_meals'] = db_locks
    session.modified = True


# --- Shopping List Generation ---
# Type Alias for clarity
AggregatedIngredientInfo = Dict[str, Any] # Contains unit, recipes, aisle, needs_check, required_qty
ShoppingListDict = Dict[str, List[Dict[str, Any]]] # Aisle -> List of Item Dicts
PlanIdsDict = Dict[str, Dict[str, Dict[str, Any]]] # day -> meal_type -> recipe_id or manual text

def generate_shopping_list_data(plan_ids: PlanIdsDict) -> ShoppingListDict:
            
    """
    Generates shopping list data based on the meal plan IDs.
    Aggregates ingredients across unique recipes in the plan,
    deducts available pantry items, and structures the list by aisle.
    Uses DB to persist checked state, with session as fallback.
    """
    from collections import defaultdict
    shopping_list_by_aisle: ShoppingListDict = defaultdict(list)
    app.logger.debug(f"[SHOPLIST] Called generate_shopping_list_data with plan_ids: {plan_ids}")
    # --- 1. Gather unique recipe IDs ---
    unique_recipe_ids = set()
    for day, meals in plan_ids.items():
        for meal_type, meal_info in meals.items():
            if (meal_info and meal_info.get('recipe_id') not in (None, -1)
                    and meal_info.get('status') != 'leftover'):
                unique_recipe_ids.add(meal_info['recipe_id'])
    app.logger.debug(f"[SHOPLIST] Unique recipe IDs for aggregation: {unique_recipe_ids}")
    # --- 2. Aggregate ingredients ---
    ingredient_map = defaultdict(lambda: {'quantity': 0, 'unit': None, 'aisle': None, 'recipes': set()})
    if unique_recipe_ids:
        recipes = Recipe.query.filter(Recipe.id.in_(unique_recipe_ids)).all()
        for recipe in recipes:
            for ing in recipe.ingredients:
                key = (ing.name.strip().lower(), (ing.unit or '').strip().lower())
                ingredient_map[key]['quantity'] += float(ing.quantity or 0)
                ingredient_map[key]['unit'] = ing.unit
                ingredient_map[key]['aisle'] = ing.aisle or 'Other'
                ingredient_map[key]['recipes'].add(recipe.name)
    app.logger.debug(f"[SHOPLIST] Aggregated ingredient map: {ingredient_map}")
    # --- 3. Deduct pantry items ---
    pantry_items = {i.name.strip().lower(): i for i in PantryItem.query.all()}
    for (name, unit), data in ingredient_map.items():
        pantry_item = pantry_items.get(name)
        pantry_qty = 0
        if pantry_item and (pantry_item.unit or '').strip().lower() == (unit or '').strip().lower():
            try:
                pantry_qty = float(pantry_item.quantity or 0)
            except Exception:
                pantry_qty = 0
        remaining_qty = max(0, data['quantity'] - pantry_qty)
        if remaining_qty > 0:
            shopping_list_by_aisle[data['aisle']].append({
                'name': name,
                'quantity': remaining_qty,
                'unit': data['unit'],
                'recipes': list(data['recipes']),
                'in_pantry': pantry_qty > 0,
                'pantry_deducted': min(data['quantity'], pantry_qty) if pantry_qty else 0
            })
            app.logger.debug(f"[SHOPLIST] Added item: {name}, qty: {remaining_qty}, aisle: {data['aisle']}, unit: {data['unit']}")
    # --- 4. Add custom items from session (fallback) ---
    custom_items = session.get('shopping_list_state', {}).get('custom_items', [])
    for item in custom_items:
        aisle = item.get('aisle', 'Other')
        shopping_list_by_aisle[aisle].append({
            'name': item['name'],
            'quantity': item.get('quantity', 1),
            'unit': item.get('unit', ''),
            'is_custom': True
        })
        app.logger.debug(f"[SHOPLIST] Added custom item from session: {item}")
    # --- 5. Sort items within each aisle ---
    for aisle in shopping_list_by_aisle:
        shopping_list_by_aisle[aisle].sort(key=lambda x: x['name'])
    app.logger.debug(f"[SHOPLIST] Final shopping_list_by_aisle: {shopping_list_by_aisle}")
    return shopping_list_by_aisle


# --- Meal Plan Generation ---
# Type Aliases for Meal Plan structure
MealInfoDict = Dict[str, Any] # Holds recipe_id, status, locks etc.
DayPlanDict = Dict[str, Optional[MealInfoDict]] # meal_type -> MealInfoDict
PlanIdsDict = Dict[str, DayPlanDict] # day_name -> DayPlanDict
LockedMealsDict = Dict[str, Dict[str, Any]] # slot_id -> lock_info_dict
Coords = Tuple[int, str] # (day_index, meal_type)

from flask import jsonify, request

@app.route('/toggle_meal_lock', methods=['POST'])
@login_required
@csrf.exempt # If using Flask-WTF CSRF, otherwise remove
def toggle_meal_lock():
    data = request.get_json()
    
    slot_id = data.get('slot_id')
    locked = data.get('locked')
    # Force locked to boolean
    if isinstance(locked, str):
        locked = locked.lower() == 'true'
    if not slot_id or locked is None:
        
        return jsonify({'success': False, 'error': 'Missing slot_id or locked'}), 400
    # Update persistent lock in DB
    # Find the recipe_id for this slot from the current plan
    plan = session.get('current_plan_ids', {})
    recipe_id = None
    try:
        day, meal_type = slot_id.split('_')
        recipe_info = plan.get(day, {}).get(meal_type, {})
        recipe_id = recipe_info.get('recipe_id')
    except Exception as e:
        app.logger.warning(f"[TOGGLE_LOCK] Could not find recipe_id for {slot_id}: {e}")

    if locked and recipe_id:
        lock_info = {'recipe_id': recipe_id, 'manual': False, 'default': False, 'lock_type': 'user'}
        update_persistent_lock(slot_id, lock_info)
    else:
        update_persistent_lock(slot_id, None)
    # Update session lock state for this slot
    session_locks = session.get('locked_meals', {})
    if locked and recipe_id:
        session_locks[slot_id] = {'recipe_id': recipe_id, 'manual': False, 'default': False, 'lock_type': 'user'}
        
    else:
        session_locks.pop(slot_id, None)
        
    session['locked_meals'] = session_locks
    session.modified = True
    
    return jsonify({'success': True})

def get_next_day(current_day: str, days: List[str]) -> Optional[str]:
    """Helper to get the next day name in the week list."""
    try:
        idx = days.index(current_day)
    except ValueError:
        return None
    if idx + 1 < len(days):
        return days[idx + 1]
    return None


def assign_leftovers(plan_ids: PlanIdsDict, current_day: str, meal_type: str, leftovers: int, num_people: int,
                     current_recipe_id: int, days: List[str]) -> None:
    """Assign leftover servings to subsequent meal slots."""
    next_day = get_next_day(current_day, days)
    while leftovers >= num_people and next_day:
        slot_info = plan_ids.get(next_day, {}).get(meal_type)

        # Skip if slot exists and is locked (user or default)
        if slot_info is not None:
            if slot_info.get('locked_by_main', False) or slot_info.get('default_lock', False):
                next_day = get_next_day(next_day, days)
                continue
            # Also skip if this slot already has a leftover assigned
            if slot_info.get('status') == 'leftover':
                next_day = get_next_day(next_day, days)
                continue

        leftover_label = f"Leftover from {current_day}'s {meal_type.lower()}"
        plan_ids[next_day][meal_type] = {
            "recipe_id": current_recipe_id,
            "status": "leftover",
            "manual_text": leftover_label,
            "locked_by_main": False,
            "locked_by_user": False,
        }

        slot_id = f"{next_day}_{meal_type}"

        # Persist leftover lock in DB and update session state
        lock_info = {
            "recipe_id": current_recipe_id,
            "manual": False,
            "default": False,
            "lock_type": "leftover",
            "text": leftover_label,
        }
        update_persistent_lock(slot_id, lock_info)

        session_locks = session.get("locked_meals", {})
        session_locks[slot_id] = lock_info
        session["locked_meals"] = session_locks
        session.modified = True

        leftovers -= num_people
        next_day = get_next_day(next_day, days)

    return None


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
    for slot_id, lock_info in locked_meals.items():
        try:
            day, meal_type = slot_id.split('_', 1)
            if day not in days or meal_type not in meal_types:
                app.logger.warning(f"Invalid slot_id format in locked_meals: {slot_id}")
                continue  # Skip malformed slot_id
            current_coords = (days.index(day), meal_type)
        except Exception:
            app.logger.warning(f"Invalid slot_id format in locked_meals: {slot_id}")
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
                    if lock_info.get('lock_type') == 'leftover':
                        # Leftover slots are not treated as locked
                        plan_ids[day][meal_type] = {
                            'recipe_id': recipe_id,
                            'status': 'leftover',
                            'manual_text': lock_info.get('text'),
                            'locked_by_main': False,
                            'locked_by_user': False
                        }
                    else:
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

            # --- 3. Calculate and Assign Leftovers ---
            try:
                servings = chosen_recipe.servings
                if servings is not None and isinstance(num_people, int) and num_people > 0:
                    leftovers = servings - num_people
                    if leftovers >= num_people:
                        assign_leftovers(plan_ids, day, meal_type, leftovers, num_people, chosen_recipe.id, days)
            except (TypeError, ValueError, ZeroDivisionError) as e:
                app.logger.error(
                    f"Error calculating leftovers for recipe {chosen_recipe.id} (servings: {chosen_recipe.servings}, num_people: {num_people}): {e}")
                # Continue without generating leftovers for this meal

    return plan_ids
# --- Routes (MUST come after app, db, models, helpers are defined) ---

@app.route('/update-shopping-item-checked', methods=['POST'])
@login_required
@csrf.exempt  # Exempt this route from CSRF protection since we handle it manually
def update_shopping_item_checked():
    """Update the checked status of a shopping list item."""
    try:
        # Verify CSRF token
        token = request.headers.get('X-CSRFToken')
        if not token:
            return jsonify({'success': False, 'error': 'CSRF token missing'}), 400
            
        data = request.get_json()
        if not data or 'item_id' not in data or 'is_checked' not in data:
            return jsonify({'success': False, 'error': 'Invalid request data'}), 400

        try:
            item_id = int(data['item_id'])
        except (TypeError, ValueError):
            return jsonify({'success': False, 'error': 'Invalid item ID'}), 400
            
        is_checked = bool(data['is_checked'])
        
        # Get current user's account
        account = current_user.accounts.first()
        if not account:
            return jsonify({'success': False, 'error': 'No account found'}), 404

        # Get the item and verify ownership
        item = ShoppingListItem.query.get(item_id)
        if not item:
            return jsonify({'success': False, 'error': 'Item not found'}), 404
        if item.account_id != account.id:
            return jsonify({'success': False, 'error': 'Unauthorized'}), 403

        # Update the item
        item.is_checked = is_checked
        item.updated_at = datetime.utcnow()
        db.session.commit()

        # Verify the update
        db.session.refresh(item)
        if item.is_checked != is_checked:
            return jsonify({'success': False, 'error': 'Failed to update item'}), 500

        # Emit update to all users in the same account
        room = f'shopping_list_{account.id}'
        app.logger.debug(f'[WEBSOCKET] Emitting item_updated to room {room}')
        socketio.emit('item_updated', {
            'item_id': item_id,
            'is_checked': item.is_checked,
            'updated_at': item.updated_at.isoformat()
        }, room=room)

        return jsonify({
            'success': True,
            'item_id': item_id,
            'is_checked': item.is_checked
        })

    except Exception as e:
        app.logger.error(f"Error updating shopping item: {str(e)}")
        return jsonify({'success': False, 'error': 'Server error'}), 500

    account = current_user.accounts.first()
    if not account:
        app.logger.error('[DEBUG-update-item] No account found for current user')
        return jsonify({'success': False, 'error': 'No account found'}), 400

    item = ShoppingListItem.query.get(item_id)
    if not item or item.account_id != account.id:
        app.logger.error(f'[DEBUG-update-item] Item not found or access denied for item_id={item_id}')
        return jsonify({'success': False, 'error': 'Item not found'}), 404

    item.is_checked = bool(is_checked)
    db.session.commit()
    print(f"[CONSOLE] Shopping list item update: item_id={item_id}, is_checked={item.is_checked}")
    app.logger.info(f'[DEBUG-update-item] Updated item_id={item_id} is_checked={is_checked}')
    return jsonify({'success': True})


from flask import request, jsonify
from flask_login import login_required, current_user
import logging
logging.basicConfig(level=logging.DEBUG)

@login_required
def unlock_all_meals():

    try:
        account = current_user.accounts.first()
        if not account:
            return jsonify({'success': False, 'error': 'No account found'}), 400
        # Remove all LockedMeal entries for this account
        num_deleted = LockedMeal.query.delete()
        db.session.commit()
        app.logger.info(f"Unlock All: Deleted {num_deleted} locked meals for account {account.id}")
        return jsonify({'success': True, 'unlocked_count': num_deleted})
    except Exception as e:
        db.session.rollback()
        app.logger.error(f"Unlock All: Error unlocking all meals: {str(e)}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500

app.add_url_rule('/unlock_all_meals', view_func=unlock_all_meals, methods=['POST'])


@app.route('/', methods=['GET', 'POST'])
@login_required
def dashboard():
    # Initialize session variables if they don't exist
    if 'num_people' not in session:
        session['num_people'] = 2
    if 'locked_meals' not in session:
        sync_session_locks_with_db()

    # Fetch user meal plan settings
    account = current_user.accounts.first()
    settings = getattr(account, 'settings', None)
    meal_plan_start_day = getattr(settings, 'meal_plan_start_day', 'Monday') if settings else 'Monday'
    meal_plan_duration = getattr(settings, 'meal_plan_duration', 7) if settings else 7
    num_people = getattr(settings, 'num_people', 2) if settings else 2
    try:
        meal_plan_duration = int(meal_plan_duration)
    except Exception:
        meal_plan_duration = 7
    if meal_plan_duration < 1 or meal_plan_duration > 31:
        meal_plan_duration = 7
    try:
        num_people = int(num_people)
    except Exception:
        num_people = 2
    if num_people < 1:
        num_people = 2

    # Compute the days for the plan, starting from meal_plan_start_day
    start_idx = ALL_DAYS.index(meal_plan_start_day) if meal_plan_start_day in ALL_DAYS else 0
    days = [ALL_DAYS[(start_idx + i) % 7] for i in range(meal_plan_duration)]

    # Handle POST request (form submission)
    if request.method == 'POST':
        # No longer handle num_people from dashboard form; it is now only set via settings page
        pass

        # Check if this is a "Lock All" request
        lock_all = request.form.get('lock_all_flag') == 'true'
        app.logger.info(f"Lock all flag: {lock_all}")
        
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
                
                app.logger.debug(f"Processing slot {slot_id}: manual_select={manual_select}, lock_checkbox={lock_checkbox}, recipe_id={recipe_id_in_slot_str}")

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
                    app.logger.info(f"Setting manual text lock for {slot_id}: {manual_text}")

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
                            app.logger.info(f"Setting manual recipe lock for {slot_id}: {recipe_id}")
                        else:
                            flash(f"Selected recipe ID {recipe_id} for {slot_id} not found. Selection ignored.", "warning")
                    except (ValueError, TypeError):
                        flash(f"Invalid recipe selection value '{manual_select}' for {slot_id}. Selection ignored.", "warning")

                # 3. Checkbox or Lock All
                else:
                    # IMPORTANT FIX: Explicitly handle both checked and unchecked states
                    should_lock_this_slot = (lock_checkbox == 'on') or lock_all
                    app.logger.debug(f"Slot {slot_id} should_lock: {should_lock_this_slot}, lock_checkbox: {lock_checkbox}, lock_all: {lock_all}")
                    
                    # If checkbox is unchecked and not a lock_all request, explicitly remove the lock
                    if not should_lock_this_slot and not lock_all:
                        # Explicitly set to None to remove the lock
                        lock_info_to_set = None
                        app.logger.info(f"Removing lock for {slot_id} (checkbox unchecked)")
                    elif should_lock_this_slot:
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
                                # FIXED: Ensure manual flag is set to False for user locks
                                lock_info_to_set = {
                                    'recipe_id': current_recipe_id,
                                    'manual': False,  # This is a user lock, not a manual lock
                                    'default': False,
                                    'lock_type': 'user'  # Add lock type information
                                }
                                app.logger.info(f"Setting user lock for {slot_id}: {current_recipe_id}, manual=False, lock_type=user")
                            else:
                                flash(f"Recipe ID {current_recipe_id} for {slot_id} not found. Lock not applied.", "warning")
                                lock_info_to_set = None

                # Update the locked_meals dictionary with the determined lock state
                if lock_info_to_set is not None:
                    new_locked_meals[slot_id] = lock_info_to_set
                elif slot_id in session.get('locked_meals', {}):
                    # If lock_info_to_set is None and there was a previous lock, remove it
                    del session['locked_meals'][slot_id]

        # Update session with new locked meals
        session['locked_meals'] = new_locked_meals
        app.logger.info(f"Updated session locked_meals: {new_locked_meals}")

        # Update persistent locks in database
        try:
            for slot_id, lock_info in new_locked_meals.items():
                update_persistent_lock(slot_id, lock_info)
        except Exception as e:
            app.logger.error(f"Error updating persistent locks: {e}")

        # Sync session with database locks
        sync_session_locks_with_db()
        
        # Log the final state of locked_meals for debugging
        app.logger.info(f"Final locked_meals state: {session.get('locked_meals')}")

        # Regenerate the meal plan
        plan_ids = generate_meal_plan(session['num_people'], session['locked_meals'])
        session['current_plan_ids'] = plan_ids
        session.modified = True

        # Clear shopping list state as the plan has changed
        session.pop('shopping_list_state', None)

        # Regenerate the shopping list
        generate_shopping_list()

        return redirect(url_for('dashboard'))

    # --- GET Request Rendering ---
    # Ensure a plan exists in the session
    if 'current_plan_ids' not in session:
        # Generate plan with correct days and duration
        session['current_plan_ids'] = generate_meal_plan(num_people, session.get('locked_meals', {}), days=days)
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
    app.logger.debug(f"[DASHBOARD] Passing locked_meals to template: {active_locked_meals_state}")

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
                status = meal_info_ids.get('status', 'empty')  # Default status if missing

                display_info.update({
                    'status': status,
                    'locked_by_main': meal_info_ids.get('locked_by_main', False),
                    'default_lock': meal_info_ids.get('default_lock', False),
                    'manual_text': meal_info_ids.get('manual_text')
                })

                if recipe_id == -1:
                    display_info.update({
                        'manual_text': meal_info_ids.get('manual_text', 'Manual Entry'),
                        'is_manual_entry': True,
                        'status': 'locked'  # Manual entries are always locked
                    })
                elif recipe_id is not None and recipe_id > 0:
                    recipe_object = recipes_in_plan_dict.get(recipe_id)
                    if recipe_object:
                        display_info['recipe'] = recipe_object
                        display_info['status'] = status
                    else:
                        display_info['recipe'] = None
                        display_info['status'] = 'deleted'
                        app.logger.warning(
                            f"Recipe ID {recipe_id} found in plan but not in database for slot {slot_id}.")

            plan_for_template[day][meal_type] = display_info

    # Fetch all recipes for the dropdown menu
    recipes_for_dropdown = Recipe.query.order_by(Recipe.name).all()
    # Get distinct aisles for the shopping list
    distinct_aisles = get_distinct_aisles()

    return render_template('dashboard.html',
                           plan=plan_for_template,
                           num_people=num_people,
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


@app.route('/shopping-list', methods=['GET', 'POST'])
@login_required
def shopping_list():
    app.logger.debug("[DEBUG-shopping-list] Entered shopping_list route")
    if request.method == 'POST':
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'error': 'No data provided'}), 400
            
        item_id = data.get('item_id')
        is_checked = data.get('is_checked')
        
        if not item_id or is_checked is None:
            return jsonify({'success': False, 'error': 'Missing required fields'}), 400
            
        # Get user's account
        account = current_user.accounts.first()
        if not account:
            return jsonify({'success': False, 'error': 'No account found'}), 400
            
        # Get the item and verify it belongs to the user's account
        item = ShoppingListItem.query.get(item_id)
        if not item or item.account_id != account.id:
            return jsonify({'success': False, 'error': 'Item not found'}), 404
            
        # Update the item
        item.is_checked = is_checked
        item.updated_at = datetime.utcnow()  # Force update of timestamp
        db.session.commit()
        
        return jsonify({'success': True})
        
    # GET request - display shopping list
    account = current_user.accounts.first()
    if not account:
        flash('No account found. Please create an account first.', 'error')
        return redirect(url_for('dashboard'))
        
    # Get all shopping list items for the account
    items = ShoppingListItem.query.filter_by(account_id=account.id).order_by(ShoppingListItem.aisle, ShoppingListItem.name).all()
    app.logger.debug(f"[DEBUG-shopping-list] Items fetched from DB: {[ (item.id, item.name, item.quantity, item.unit, item.aisle) for item in items ]}")
    # Group items by aisle
    items_by_aisle = {}
    for item in items:
        aisle = item.aisle or 'Other'
        if aisle not in items_by_aisle:
            items_by_aisle[aisle] = []
        items_by_aisle[aisle].append(item)
    app.logger.debug(f"[DEBUG-shopping-list] items_by_aisle: {items_by_aisle}")
    # Get list of unique aisles for the dropdown
    aisles = sorted(set(item.aisle for item in items if item.aisle))
    
    return render_template('shopping_list.html', items_by_aisle=items_by_aisle, aisles=aisles)

@app.route('/add-shopping-item', methods=['POST'])
@login_required
def add_shopping_item():
    account = current_user.accounts.first()
    if not account:
        flash('No account found. Please create an account first.', 'error')
        return redirect(url_for('shopping_list'))
        
    name = request.form.get('name')
    quantity = request.form.get('quantity')
    unit = request.form.get('unit')
    aisle = request.form.get('aisle')
    
    if not name:
        flash('Item name is required.', 'error')
        return redirect(url_for('shopping_list'))
        
    item = ShoppingListItem(
        account_id=account.id,
        name=name,
        quantity=float(quantity) if quantity else None,
        unit=unit,
        aisle=aisle,
        is_checked=False
    )
    
    db.session.add(item)
    db.session.commit()
    
    flash('Item added to shopping list.', 'success')
    return redirect(url_for('shopping_list'))

@app.route('/delete-shopping-item', methods=['POST'])
@login_required
def delete_shopping_item():
    data = request.get_json()
    if not data:
        return jsonify({'success': False, 'error': 'No data provided'}), 400
        
    item_id = data.get('item_id')
    if not item_id:
        return jsonify({'success': False, 'error': 'Item ID is required'}), 400
        
    account = current_user.accounts.first()
    if not account:
        return jsonify({'success': False, 'error': 'No account found'}), 400
        
    item = ShoppingListItem.query.get(item_id)
    if not item or item.account_id != account.id:
        return jsonify({'success': False, 'error': 'Item not found'}), 404
        
    db.session.delete(item)
    db.session.commit()
    
    return jsonify({'success': True})

@app.route('/move_shopping_item', methods=['POST'])
def move_shopping_item():

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


def update_shopping_list_aisles(ingredient_name: str, new_aisle: Optional[str]) -> None:

    # Update ShoppingListItem table
    ShoppingListItem.query.filter(
        func.lower(ShoppingListItem.name) == func.lower(ingredient_name)
    ).update(
        {'aisle': new_aisle},
        synchronize_session=False
    )

@app.route('/manage_aisles', methods=['GET', 'POST'])
@login_required
def manage_aisles():
    # Get distinct aisles for dropdown options
    distinct_aisles = get_distinct_aisles()

    if request.method == 'POST':
        try:
            # Start a transaction
            db.session.begin_nested()
            
            # Get all form data
            form_data = request.form.to_dict()
            
            # Process updates in batches
            updates = []
            for key, value in form_data.items():
                if key.startswith('aisle_'):
                    ingredient_name = key[6:]  # Remove 'aisle_' prefix
                    original_aisle = form_data.get(f'original_aisle_{ingredient_name}')
                    
                    # Only update if the value has changed
                    if value != original_aisle:
                        updates.append({
                            'name': ingredient_name,
                            'new_aisle': value if value else None
                        })
            
            if not updates:
                flash('No changes were made to aisle assignments.', 'info')
                return redirect(url_for('manage_aisles'))
            
            # Perform bulk updates
            for update in updates:
                # Update Ingredients table
                Ingredient.query.filter(
                    Ingredient.name.ilike(update['name'])
                ).update(
                    {
                        'aisle': update['new_aisle'],
                        'updated_at': datetime.utcnow()
                    },
                    synchronize_session=False
                )
                
                # Update PantryItems table
                PantryItem.query.filter(
                    PantryItem.name.ilike(update['name'])
                ).update(
                    {'aisle': update['new_aisle']},
                    synchronize_session=False
                )
                
                # Update ShoppingListItem table
                ShoppingListItem.query.filter(
                    func.lower(ShoppingListItem.name) == func.lower(update['name'])
                ).update(
                    {
                        'aisle': update['new_aisle'],
                        'updated_at': datetime.utcnow()
                    },
                    synchronize_session=False
                )
            
            # Commit the transaction
            db.session.commit()
            
            # Flash success message with count
            flash(f'Successfully updated {len(updates)} ingredient aisle assignments.', 'success')
            return redirect(url_for('manage_aisles'))
        except Exception as e:
            db.session.rollback()
            flash(f'Error updating aisle assignments: {str(e)}', 'error')
            return redirect(url_for('manage_aisles'))

    # GET request - display the form
    try:
        # Get distinct ingredients with their latest aisle
        ingredients = db.session.query(
        Ingredient.name,
            func.max(Ingredient.aisle).label('aisle')
        ).group_by(
            Ingredient.name
        ).order_by(
            Ingredient.name
        ).all()
        
        # Convert to list of dicts for template
        ingredients = [{'name': i.name, 'aisle': i.aisle} for i in ingredients]
        
        return render_template(
            'manage_aisles.html',
            ingredients=ingredients,
            distinct_aisles=distinct_aisles
        )
        
    except Exception as e:
        flash(f'Error loading ingredients: {str(e)}', 'error')
        return redirect(url_for('dashboard'))

@app.route('/cupboard', methods=['GET', 'POST'])
def cupboard():

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

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    
    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(email=form.email.data).first()
        if user and user.check_password(form.password.data):
            # Get remember me value from form
            remember = request.form.get('remember_me') == 'on'
            login_user(user, remember=remember)
            user.last_login = datetime.utcnow()
            db.session.commit()
            return redirect(url_for('dashboard'))
        flash('Invalid email or password', 'error')
    return render_template('login.html', form=form)

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        name = request.form.get('name')
        email = request.form.get('email')
        password = request.form.get('password')
        confirm_password = request.form.get('confirm_password')
        
        print(f"DEBUG: Registration attempt - Name: {name}, Email: {email}")
        
        # Validate email format
        if not re.match(r"[^@]+@[^@]+\.[^@]+", email):
            flash('Invalid email address', 'error')
            print(f"DEBUG: Invalid email format: {email}")
            return redirect(url_for('register'))
        
        # Check if passwords match
        if password != confirm_password:
            flash('Passwords must match', 'error')
            print(f"DEBUG: Passwords don't match")
            return redirect(url_for('register'))
        
        # Check if user already exists
        existing_user = User.query.filter_by(email=email).first()
        if existing_user:
            flash('Email already registered', 'error')
            print(f"DEBUG: Email already registered: {email}")
            return redirect(url_for('register'))
        
        try:
            print(f"DEBUG: Creating new account for {name}")
            # Create new account
            account = Account(name=f"{name}'s Account")
            db.session.add(account)
            db.session.flush()  # Get account ID without committing
            print(f"DEBUG: Account created with ID: {account.id}")
            
            # Create new user
            print(f"DEBUG: Creating new user with email: {email}")
            user = User(name=name, email=email)
            user.set_password(password)
            db.session.add(user)
            db.session.flush()  # Get user ID without committing
            print(f"DEBUG: User created with ID: {user.id}")
            
            # Create account-user relationship
            print(f"DEBUG: Creating account-user relationship")
            account_user = AccountUser(
                account_id=account.id,
                user_id=user.id,
                role='admin'  # First user is admin
            )
            db.session.add(account_user)
            
            # Commit all changes
            print(f"DEBUG: Committing all changes to database")
            db.session.commit()
            print(f"DEBUG: Registration successful for {email}")
            
            flash('Registration successful! Please login.', 'success')
            return redirect(url_for('login'))
            
        except Exception as e:
            db.session.rollback()
            print(f"DEBUG: Registration error: {str(e)}")
            import traceback
            print(f"DEBUG: Traceback: {traceback.format_exc()}")
            flash('An error occurred during registration. Please try again.', 'error')
            return redirect(url_for('register'))
    
    return render_template('register.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('You have been logged out.', 'info')
    return redirect(url_for('login'))

@app.route('/debug/users')
@login_required
def debug_users():
    users = User.query.all()
    output = []
    for user in users:
        user_data = {
            'id': user.id,
            'email': user.email,
            'name': user.name,
            'created_at': user.created_at,
            'last_login': user.last_login,
            'is_active': user.is_active,
            'accounts': [{'id': acc.id, 'name': acc.name} for acc in user.accounts]
        }
        output.append(user_data)
    return jsonify(output)

@app.route('/debug/db')
def debug_db():

    try:
        # Get all table names
        inspector = db.inspect(db.engine)
        table_names = inspector.get_table_names()
        
        # Get column info for each table
        tables_info = {}
        for table_name in table_names:
            columns = inspector.get_columns(table_name)
            tables_info[table_name] = [{"name": col["name"], "type": str(col["type"])} for col in columns]
        
        # Check if User table exists and has records
        user_count = 0
        if 'user' in table_names:
            user_count = db.session.query(User).count()
        
        # Check if Account table exists and has records
        account_count = 0
        if 'account' in table_names:
            account_count = db.session.query(Account).count()
        
        # Check if AccountUser table exists and has records
        account_user_count = 0
        if 'account_user' in table_names:
            account_user_count = db.session.query(AccountUser).count()
        
        return jsonify({
            "tables": tables_info,
            "user_count": user_count,
            "account_count": account_count,
            "account_user_count": account_user_count
        })
    except Exception as e:
        import traceback
        return jsonify({
            "error": str(e),
            "traceback": traceback.format_exc()
        })

@app.route('/invite', methods=['GET', 'POST'])
@login_required
def invite_user():
    form = InviteUserForm()
    
    if form.validate_on_submit():
        email = form.email.data
        role = form.role.data
        
        # Get the current user's account
        account_user = AccountUser.query.filter_by(
            user_id=current_user.id,
            role='admin'
        ).first()
        
        if not account_user:
            flash('You do not have permission to invite users.', 'error')
            return redirect(url_for('dashboard'))
        
        # Check if user is already a member
        existing_user = User.query.filter_by(email=email).first()
        if existing_user:
            existing_membership = AccountUser.query.filter_by(
                account_id=account_user.account_id,
                user_id=existing_user.id
            ).first()
            if existing_membership:
                flash('User is already a member of this account.', 'error')
                return redirect(url_for('manage_users'))
        
        # Generate a unique token
        token = os.urandom(32).hex()
        
        # Create invitation
        invitation = Invitation(
            account_id=account_user.account_id,
            email=email,
            token=token,
            created_by=current_user.id,
            expires_at=datetime.utcnow() + timedelta(days=7),
            role=role  # Set the role field
        )
        
        try:
            db.session.add(invitation)
            db.session.commit()
            
            # Get the local IP address
            hostname = socket.gethostname()
            local_ip = socket.gethostbyname(hostname)
            
            # In a real application, you would send an email here
            # For now, we'll just show the invitation link
            invitation_url = url_for('accept_invitation', token=token, _external=True)
            flash(f'Invitation sent to {email}. Invitation link: {invitation_url}', 'success')
            
        except Exception as e:
            db.session.rollback()
            app.logger.error(f"Error creating invitation: {str(e)}")
            flash('An error occurred while creating the invitation.', 'error')
            
        return redirect(url_for('manage_users'))
    
    # GET request - show invitation form
    return render_template('invite_user.html', form=form)

@app.route('/manage_users')
@login_required
def manage_users():
    # Get the current user's account
    account_user = AccountUser.query.filter_by(
        user_id=current_user.id,
        role='admin'
    ).first()
    
    if not account_user:
        flash('You do not have permission to manage users.', 'error')
        return redirect(url_for('dashboard'))
    
    # Get all users in the account
    account_users = AccountUser.query.filter_by(account_id=account_user.account_id).all()
    
    # Get pending invitations
    pending_invites = Invitation.query.filter_by(
        account_id=account_user.account_id,
        is_used=False
    ).all()
    
    # Extract users from account_users
    users = []
    for au in account_users:
        user = au.user
        # Add role attribute to user object
        user.role = au.role
        users.append(user)
    
    return render_template('manage_users.html', 
                         users=users,
                         pending_invites=pending_invites)

@app.route('/update_user_role/<int:user_id>', methods=['POST'])
@login_required
def update_user_role(user_id):
    # Get the current user's account
    current_account_user = AccountUser.query.filter_by(
        user_id=current_user.id,
        role='admin'
    ).first()
    
    if not current_account_user:
        flash('You do not have permission to update user roles.', 'error')
        return redirect(url_for('manage_users'))
    
    # Get the target user's account membership
    account_user = AccountUser.query.filter_by(
        account_id=current_account_user.account_id,
        user_id=user_id
    ).first()
    
    if not account_user:
        flash('User not found in this account.', 'error')
        return redirect(url_for('manage_users'))
    
    # Update the role
    new_role = request.form.get('role')
    if new_role in ['user', 'admin']:
        account_user.role = new_role
        db.session.commit()
        flash(f'User role updated to {new_role}.', 'success')
    else:
        flash('Invalid role specified.', 'error')
    
    return redirect(url_for('manage_users'))

@app.route('/toggle_user_status/<int:user_id>', methods=['POST'])
@login_required
def toggle_user_status(user_id):
    # Get the current user's account
    current_account_user = AccountUser.query.filter_by(
        user_id=current_user.id,
        role='admin'
    ).first()
    
    if not current_account_user:
        flash('You do not have permission to update user status.', 'error')
        return redirect(url_for('manage_users'))
    
    # Get the target user's account membership
    account_user = AccountUser.query.filter_by(
        account_id=current_account_user.account_id,
        user_id=user_id
    ).first()
    
    if not account_user:
        flash('User not found in this account.', 'error')
        return redirect(url_for('manage_users'))
    
    # Toggle the user's active status
    account_user.user.is_active = not account_user.user.is_active
    db.session.commit()
    
    status = 'activated' if account_user.user.is_active else 'deactivated'
    flash(f'User has been {status}.', 'success')
    
    return redirect(url_for('manage_users'))

@app.route('/remove_user/<int:user_id>', methods=['POST'])
@login_required
def remove_user(user_id):
    # Get the current user's account
    current_account_user = AccountUser.query.filter_by(
        user_id=current_user.id,
        role='admin'
    ).first()
    
    if not current_account_user:
        flash('You do not have permission to remove users.', 'error')
        return redirect(url_for('manage_users'))
    
    # Get the target user's account membership
    account_user = AccountUser.query.filter_by(
        account_id=current_account_user.account_id,
        user_id=user_id
    ).first()
    
    if not account_user:
        flash('User not found in this account.', 'error')
        return redirect(url_for('manage_users'))
    
    # Remove the user from the account
    db.session.delete(account_user)
    db.session.commit()
    
    flash('User has been removed from the account.', 'success')
    return redirect(url_for('manage_users'))

@app.route('/accept-invitation/<token>', methods=['GET', 'POST'])
def accept_invitation(token):
    invitation = Invitation.query.filter_by(token=token).first()
    
    if not invitation:
        flash('Invalid or expired invitation.', 'error')
        return redirect(url_for('login'))
    
    if invitation.is_used:
        flash('This invitation has already been used.', 'error')
        return redirect(url_for('login'))
    
    if invitation.expires_at < datetime.utcnow():
        flash('This invitation has expired.', 'error')
        return redirect(url_for('login'))
    
    if request.method == 'POST':
        # If user is not logged in, they need to register
        if not current_user.is_authenticated:
            name = request.form.get('name')
            email = request.form.get('email')
            password = request.form.get('password')
            
            # Validate email matches invitation
            if email != invitation.email:
                flash('Email must match the invitation.', 'error')
                return redirect(url_for('accept_invitation', token=token))
            
            # Create new user
            user = User(name=name, email=email)
            user.set_password(password)
            db.session.add(user)
            db.session.flush()
            
        else:
            # If user is logged in, verify email matches
            if current_user.email != invitation.email:
                flash('You must be logged in with the email address the invitation was sent to.', 'error')
                return redirect(url_for('accept_invitation', token=token))
            user = current_user
        
        try:
            # Create account-user relationship with the role from the invitation
            account_user = AccountUser(
                account_id=invitation.account_id,
                user_id=user.id,
                role=invitation.role  # Use the role from the invitation
            )
            db.session.add(account_user)
            
            # Mark invitation as used
            invitation.is_used = True
            db.session.commit()
            
            flash('You have successfully joined the account!', 'success')
            return redirect(url_for('dashboard'))
            
        except Exception as e:
            db.session.rollback()
            app.logger.error(f"Error accepting invitation: {str(e)}")
            flash('An error occurred while accepting the invitation.', 'error')
            return redirect(url_for('accept_invitation', token=token))
    
    # GET request - show acceptance form
    return render_template('accept_invitation.html', invitation=invitation, now=datetime.utcnow())

@app.route('/resend_invite/<int:invite_id>', methods=['POST'])
@login_required
def resend_invite(invite_id):
    # Get the current user's account
    current_account_user = AccountUser.query.filter_by(
        user_id=current_user.id,
        role='admin'
    ).first()
    
    if not current_account_user:
        flash('You do not have permission to resend invitations.', 'error')
        return redirect(url_for('manage_users'))
    
    # Get the invitation
    invitation = Invitation.query.filter_by(
        id=invite_id,
        account_id=current_account_user.account_id,
        is_used=False
    ).first()
    
    if not invitation:
        flash('Invitation not found or already used.', 'error')
        return redirect(url_for('manage_users'))
    
    # Generate a new token
    invitation.token = os.urandom(32).hex()
    invitation.expires_at = datetime.utcnow() + timedelta(days=7)
    
    try:
        db.session.commit()
        
        # In a real application, you would send an email here
        # For now, we'll just show the invitation link
        invitation_url = url_for('accept_invitation', token=invitation.token, _external=True)
        flash(f'Invitation resent to {invitation.email}. Invitation link: {invitation_url}', 'success')
        
    except Exception as e:
        db.session.rollback()
        app.logger.error(f"Error resending invitation: {str(e)}")
        flash('An error occurred while resending the invitation.', 'error')
    
    return redirect(url_for('manage_users'))

@app.route('/cancel_invite/<int:invite_id>', methods=['POST'])
@login_required
def cancel_invite(invite_id):
    # Get the current user's account
    current_account_user = AccountUser.query.filter_by(
        user_id=current_user.id,
        role='admin'
    ).first()
    
    if not current_account_user:
        flash('You do not have permission to cancel invitations.', 'error')
        return redirect(url_for('manage_users'))
    
    # Get the invitation
    invitation = Invitation.query.filter_by(
        id=invite_id,
        account_id=current_account_user.account_id,
        is_used=False
    ).first()
    
    if not invitation:
        flash('Invitation not found or already used.', 'error')
        return redirect(url_for('manage_users'))
    
    try:
        db.session.delete(invitation)
        db.session.commit()
        flash('Invitation cancelled successfully.', 'success')
        
    except Exception as e:
        db.session.rollback()
        app.logger.error(f"Error cancelling invitation: {str(e)}")
        flash('An error occurred while cancelling the invitation.', 'error')
    
    return redirect(url_for('manage_users'))

@app.route('/settings', methods=['GET', 'POST'])
@login_required
def settings():
    account = current_user.accounts.first()
    if not account:
        flash('No account found.', 'error')
        return redirect(url_for('dashboard'))
    
    settings = account.settings
    if request.method == 'POST':
        try:
            # Update meal plan settings
            settings.num_people = int(request.form.get('num_people', 1))
            settings.meal_plan_start_day = request.form.get('meal_plan_start_day', 'Monday')
            settings.meal_plan_duration = int(request.form.get('meal_plan_duration', 7))
            settings.meal_repeat_interval = int(request.form.get('meal_repeat_interval', 0))
            
            # Update default meals
            settings.default_breakfast_id = request.form.get('default_breakfast_id') or None
            settings.default_lunch_id = request.form.get('default_lunch_id') or None
            settings.default_dinner_id = request.form.get('default_dinner_id') or None
            
            db.session.commit()
            flash('Settings updated successfully.', 'success')
            return redirect(url_for('settings'))
        except Exception as e:
            db.session.rollback()
            flash('Error updating settings. Please try again.', 'error')
            app.logger.error(f"Error updating settings: {str(e)}")
    
    # Get recipes for default meal selection
    breakfast_recipes = Recipe.query.filter_by(is_breakfast=True).all()
    lunch_recipes = Recipe.query.filter_by(is_lunch=True).all()
    dinner_recipes = Recipe.query.filter_by(is_dinner=True).all()
    
    return render_template('settings.html', 
                         settings=settings,
                         breakfast_recipes=breakfast_recipes,
                         lunch_recipes=lunch_recipes,
                         dinner_recipes=dinner_recipes)

@app.route('/generate_meal_plan', methods=['GET', 'POST'])
@login_required
def generate_meal_plan_route():
    if request.method == 'POST':
        # Get form data
        start_date = request.form.get('start_date')
        end_date = request.form.get('end_date')
        meal_types = request.form.getlist('meal_types')
        meal_locks = {}
        
        # Process meal locks
        for key, value in request.form.items():
            if key.startswith('lock_'):
                slot_id = key.replace('lock_', '')
                recipe_id = request.form.get(f'recipeid_{slot_id}')
                
                # Check if this is a manual entry
                if recipe_id == '-1':
                    # Get the manual text if it exists
                    manual_text = request.form.get(f'manual_text_{slot_id}')
                    if manual_text:
                        meal_locks[slot_id] = {
                            'recipe_id': -1,
                            'manual_text': manual_text
                        }
                elif recipe_id:
                    # Regular recipe selection
                    meal_locks[slot_id] = {
                        'recipe_id': int(recipe_id)
                    }
        
        try:
            # Get user's account
            account = current_user.accounts.first()
            if not account:
                flash('No account found. Please create or join an account first.', 'error')
                return redirect(url_for('dashboard'))
            
            # Get account settings
            settings = AccountSettings.query.filter_by(account_id=account.id).first()
            if not settings:
                settings = AccountSettings(account_id=account.id)
                db.session.add(settings)
                db.session.commit()
            
            # Generate the meal plan using the helper function
            plan_ids = generate_meal_plan(
                num_people=settings.num_people,
                locked_meals=meal_locks,
                default_breakfast_recipe_name="Cereal"  # You can make this configurable
            )
            
            # Store the generated plan in the session for confirmation
            session['meal_plan'] = {
                'start_date': start_date,
                'end_date': end_date,
                'meals': plan_ids
            }
            
            # Regenerate the shopping list
            try:
                generate_shopping_list()
                app.logger.debug("Shopping list regenerated after meal plan update")
            except Exception as e:
                app.logger.error(f"Error regenerating shopping list: {e}")
                flash('Shopping list may be out of date. Please refresh it manually.', 'warning')
            
            flash('Meal plan generated successfully! Please review and confirm.', 'success')
            return redirect(url_for('meal_plan'))
            
        except Exception as e:
            db.session.rollback()
            flash(f'Error generating meal plan: {str(e)}', 'error')
            return redirect(url_for('dashboard'))
    
    # Get recipes for default meal selection
    breakfast_recipes = Recipe.query.filter_by(is_breakfast=True).all()
    lunch_recipes = Recipe.query.filter_by(is_lunch=True).all()
    dinner_recipes = Recipe.query.filter_by(is_dinner=True).all()
    
    return render_template('generate_meal_plan.html', 
                         breakfast_recipes=breakfast_recipes,
                         lunch_recipes=lunch_recipes,
                         dinner_recipes=dinner_recipes)

@app.route('/generate_meal_plan', methods=['POST'])
@login_required
def generate_meal_plan_post():
    app.logger.debug("[DEBUG] Entered generate_meal_plan_post")
    try:
        # Get form data
        start_date = datetime.strptime(request.form['start_date'], '%Y-%m-%d').date()
        end_date = datetime.strptime(request.form['end_date'], '%Y-%m-%d').date()
        meal_types = request.form.getlist('meal_types')
        meal_locks = request.form.getlist('meal_locks')
        meal_locks = [lock for lock in meal_locks if lock.strip()]  # Remove empty strings
        
        # Get account ID
        account_id = current_user.accounts[0].id if current_user.accounts else None
        if not account_id:
            flash('No account found. Please create or join an account first.', 'error')
            return redirect(url_for('dashboard'))
        
        # Get all recipes for the account
        recipes = Recipe.query.filter_by(account_id=account_id).all()
        if not recipes:
            flash('No recipes found. Please add some recipes first.', 'error')
            return redirect(url_for('dashboard'))
        
        # Create a new meal plan
        meal_plan = MealPlan(
            account_id=account_id,
            start_date=start_date,
            end_date=end_date
        )
        db.session.add(meal_plan)
        
        # Process meal locks
        locked_meals = {}
        for lock in meal_locks:
            try:
                recipe_id, day_offset, meal_type = lock.split('_')
                recipe_id = int(recipe_id)
                day_offset = int(day_offset)
                
                # Verify recipe exists and belongs to account
                recipe = Recipe.query.filter_by(id=recipe_id, account_id=account_id).first()
                if not recipe:
                    continue
                
                meal_date = start_date + timedelta(days=day_offset)
                if meal_date <= end_date:
                    locked_meals[(meal_date, meal_type)] = recipe_id
            except (ValueError, IndexError):
                continue
        
        # Generate meal plan
        current_date = start_date
        while current_date <= end_date:
            for meal_type in meal_types:
                # Check if meal is locked
                if (current_date, meal_type) in locked_meals:
                    recipe_id = locked_meals[(current_date, meal_type)]
                else:
                    # Get available recipes for this meal type
                    available_recipes = [
                        r for r in recipes
                        if (
                            (meal_type == 'Breakfast' and r.is_breakfast) or
                            (meal_type == 'Lunch' and r.is_lunch) or
                            (meal_type == 'Dinner' and r.is_dinner)
                        )
                    ]
                    if not available_recipes:
                        continue
                    
                    # Select a random recipe
                    recipe = random.choice(available_recipes)
                    recipe_id = recipe.id
                
                # Create meal
                meal = Meal(
                    meal_plan=meal_plan,
                    date=current_date,
                    meal_type=meal_type,
                    recipe_id=recipe_id
                )
                db.session.add(meal)
            
            current_date += timedelta(days=1)
        
        # DEBUG: Log start and end dates
        app.logger.debug(f"[DEBUG-gmpost] start_date: {start_date}, end_date: {end_date}")
        # DEBUG: Log account_id
        app.logger.debug(f"[DEBUG-gmpost] account_id: {account_id}")
        # DEBUG: Log meal_types
        app.logger.debug(f"[DEBUG-gmpost] meal_types: {meal_types}")
        # DEBUG: Log meal_locks
        app.logger.debug(f"[DEBUG-gmpost] meal_locks: {meal_locks}")
        # DEBUG: Log recipes
        app.logger.debug(f"[DEBUG-gmpost] recipes: {[r.id for r in recipes]}")

        # Save the meal plan
        db.session.commit()
        app.logger.debug(f"[DEBUG-gmpost] meal_plan.id after commit: {meal_plan.id}")

        # Build plan_ids for session['current_plan_ids']
        plan_ids = {}
        meals = Meal.query.filter_by(meal_plan_id=meal_plan.id).all()
        app.logger.debug(f"[DEBUG-gmpost] meals in DB for meal_plan.id={meal_plan.id}: {[{'id': m.id, 'date': m.date, 'meal_type': m.meal_type, 'recipe_id': m.recipe_id} for m in meals]}")
        for meal in meals:
            day_str = meal.date.strftime('%A')
            if day_str not in plan_ids:
                plan_ids[day_str] = {}
            plan_ids[day_str][meal.meal_type] = {'recipe_id': meal.recipe_id}
        app.logger.debug(f"[DEBUG-gmpost] built plan_ids: {plan_ids}")
        session['current_plan_ids'] = plan_ids
        session.modified = True
        app.logger.debug(f"[DEBUG-gmpost] session['current_plan_ids']: {session.get('current_plan_ids')}")
        print(f"[PRINT-gmpost] plan_ids after form submission: {plan_ids}")

        # Regenerate shopping list based on new meal plan
        try:
            # Get the shopping list data
            shopping_list_data = generate_shopping_list_data(plan_ids)
            
            # Clear existing shopping list items
            ShoppingListItem.query.filter_by(account_id=account.id).delete()
            
            # Add new items to the shopping list
            for aisle, items in shopping_list_data.items():
                for item in items:
                    shopping_item = ShoppingListItem(
                        account_id=account.id,
                        name=item['name'],
                        quantity=item.get('quantity', 1),
                        unit=item.get('unit', ''),
                        aisle=aisle,
                        is_checked=False
                    )
                    db.session.add(shopping_item)
            
            db.session.commit()
            app.logger.debug(f"[DEBUG-gmpost] Successfully regenerated shopping list")
            flash('Meal plan and shopping list generated successfully!', 'success')
        except Exception as e:
            db.session.rollback()
            app.logger.error(f"[ERROR-gmpost] Failed to regenerate shopping list: {str(e)}")
            flash('Meal plan generated but shopping list may be out of date.', 'warning')
            
        return redirect(url_for('meal_plan'))
        end_date = datetime.strptime(request.form['end_date'], '%Y-%m-%d').date()
        account_id = current_user.accounts[0].id
        meal_plan = MealPlan(
            account_id=account_id,
            start_date=start_date,
            end_date=end_date
        )
        db.session.add(meal_plan)
        db.session.flush()
        for day, meals in plan_ids.items():
            for meal_type, meal_info in meals.items():
                recipe_id = meal_info.get('recipe_id')
                if recipe_id:
                    meal = Meal(
                        meal_plan_id=meal_plan.id,
                        recipe_id=recipe_id,
                        date=day,
                        meal_type=meal_type
                    )
                    db.session.add(meal)
        db.session.commit()

        # Generate shopping list
        app.logger.debug("[DEBUG-gmpost] Calling generate_shopping_list()...")
        shopping_list = generate_shopping_list()
        app.logger.debug(f"[DEBUG-gmpost] Finished generate_shopping_list() call. Shopping list: {shopping_list}")

        flash('Meal plan generated and shopping list updated successfully!', 'success')
        return redirect(url_for('shopping_list'))
        
    except Exception as e:
        db.session.rollback()
        print(f"[PRINT-gmpost] Meal plan DB commit failed: {e}")
        app.logger.error(f"[DEBUG-gmpost] Meal plan DB commit failed: {e}")
        flash(f'Error generating meal plan: {str(e)}', 'error')
        return redirect(url_for('dashboard'))

@app.route('/shopping_list')
@login_required
def shopping_list_redirect():
    return redirect(url_for('shopping_list'))

@app.route('/generate-shopping-list', methods=['GET', 'POST'])
@login_required
def generate_shopping_list():
    print("[PRINT-gsl] Called generate_shopping_list()")
    app.logger.debug("[DEBUG-gsl] Called generate_shopping_list()")
    app.logger.debug("[DEBUG-gsl] generate_shopping_list() called.")

    # Get the current user's account
    account = current_user.accounts.first()
    app.logger.debug(f"[DEBUG-gsl] account: {account}")
    if not account:
        flash('No account found. Please create an account first.', 'error')
        app.logger.debug("[DEBUG-gsl] No account found, aborting.")
        return redirect(url_for('dashboard'))
    
    # Get the current meal plan from the session
    plan_ids = session.get('current_plan_ids', {})
    app.logger.debug(f"[DEBUG-gsl] session['current_plan_ids']: {plan_ids}")
    if not plan_ids:
        flash('No meal plan found. Please generate a meal plan first.', 'error')
        app.logger.debug("[DEBUG-gsl] No plan_ids found in session, aborting.")
        return redirect(url_for('dashboard'))
    
    # Generate shopping list data
    shopping_list_data = generate_shopping_list_data(plan_ids)
    app.logger.debug(f"[DEBUG-gsl] shopping_list_data: {shopping_list_data}")
    
    # Clear existing shopping list items for this account
    ShoppingListItem.query.filter_by(account_id=account.id).delete()
    
    # Add new items to the shopping list
    for aisle, items in shopping_list_data.items():
        for item in items:
            shopping_item = ShoppingListItem(
                account_id=account.id,
                name=item['name'],
                quantity=item['quantity'],
                unit=item['unit'],
                aisle=aisle,
                is_checked=False,  # Reset checked status
                updated_at=datetime.utcnow()
            )
            db.session.add(shopping_item)
    
    try:
        db.session.commit()
        flash('Shopping list generated successfully from your meal plan.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error generating shopping list: {str(e)}', 'error')
        app.logger.error(f"Error generating shopping list: {str(e)}")
    
    return redirect(url_for('shopping_list'))

@app.route('/check-shopping-list-updates')
@login_required
def check_shopping_list_updates():

    account = current_user.accounts.first()
    if not account:
        return jsonify({'needs_update': False})
    
    # Get the last update timestamp from the session
    last_update = session.get('shopping_list_last_update', 0)
    current_time = time.time()
    
    # Check if any items have been modified since the last update
    latest_item = ShoppingListItem.query.filter_by(account_id=account.id).order_by(ShoppingListItem.updated_at.desc()).first()
    
    if latest_item and latest_item.updated_at and latest_item.updated_at.timestamp() > last_update:
        session['shopping_list_last_update'] = current_time
        return jsonify({'needs_update': True})
    
    return jsonify({'needs_update': False})

@app.route('/get-shopping-list-content')
@login_required
def get_shopping_list_content():

    account = current_user.accounts.first()
    if not account:
        return render_template('shopping_list_empty.html')
    
    items = ShoppingListItem.query.filter_by(account_id=account.id).order_by(ShoppingListItem.aisle, ShoppingListItem.name).all()
    items_by_aisle = {}
    
    for item in items:
        if item.aisle not in items_by_aisle:
            items_by_aisle[item.aisle] = []
        items_by_aisle[item.aisle].append(item)
    
    return render_template('shopping_list_content.html', items_by_aisle=items_by_aisle)

@app.route('/regenerate-shopping-list', methods=['POST'])
@login_required
def regenerate_shopping_list():

    # Get the current user's account
    account = current_user.accounts.first()
    if not account:
        flash('No account found. Please create an account first.', 'error')
        return redirect(url_for('shopping_list'))
    
    # Get the current meal plan from the session
    plan_ids = session.get('current_plan_ids', {})
    if not plan_ids:
        flash('No meal plan found. Please generate a meal plan first.', 'error')
        return redirect(url_for('shopping_list'))
    
    # Generate shopping list data
    shopping_list_data = generate_shopping_list_data(plan_ids)
    
    # Clear existing shopping list items for this account
    ShoppingListItem.query.filter_by(account_id=account.id).delete()
    
    # Add new items to the shopping list
    for aisle, items in shopping_list_data.items():
        for item in items:
            shopping_item = ShoppingListItem(
                account_id=account.id,
                name=item['name'],
                quantity=item['quantity'],
                unit=item['unit'],
                aisle=aisle,
                is_checked=False
            )
            db.session.add(shopping_item)
    
    try:
        db.session.commit()
        flash('Shopping list regenerated successfully with updated aisle assignments.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error regenerating shopping list: {str(e)}', 'error')
        app.logger.error(f"Error regenerating shopping list: {str(e)}")
    
    return redirect(url_for('shopping_list'))

# --- WebSocket Event Handlers ---
@socketio.on('connect')
def handle_connect():
    app.logger.debug(f'[WEBSOCKET] Client connected: {request.sid}')

@socketio.on('disconnect')
def handle_disconnect():
    app.logger.debug(f'[WEBSOCKET] Client disconnected: {request.sid}')

@socketio.on('join_shopping_list')
def on_join_shopping_list():
    """When a user opens the shopping list page"""
    account = current_user.accounts.first()
    if account:
        room = f'shopping_list_{account.id}'
        join_room(room)
        app.logger.debug(f'[WEBSOCKET] Client {request.sid} joined room {room}')

@socketio.on('leave_shopping_list')
def on_leave_shopping_list():
    """When a user leaves the shopping list page"""
    account = current_user.accounts.first()
    if account:
        room = f'shopping_list_{account.id}'
        leave_room(room)
        app.logger.debug(f'[WEBSOCKET] Client {request.sid} left room {room}')

# --- Main Execution ---
if __name__ == '__main__':
    # Create database tables if they don't exist.
    def create_tables():
        with app.app_context():
            # Check if the database file exists before creating tables
            # This is a simple check; migrations are better for managing changes.
            if not os.path.exists(DATABASE_PATH):
                print("Database file not found, creating tables...")
                db.create_all()
                print("Tables created.")
            else:
                print("Tables already exist.")

    # Run the Flask development server with Socket.IO support
    # host='0.0.0.0' makes it accessible on your network
    # debug=True enables interactive debugger and auto-reloading (DISABLE IN PRODUCTION)
    print("Starting Flask development server with Socket.IO support...")
    socketio.run(app, host='0.0.0.0', port=5000, debug=True) # Set debug=False for production!
