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
import click
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
    is_admin = db.Column(db.Boolean, default=False, nullable=False)
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
    recipe_ingredients = db.relationship('RecipeIngredient', backref='recipe', lazy=True, cascade="all, delete-orphan")
    
    # New fields for account and privacy
    account_id = db.Column(db.Integer, db.ForeignKey('account.id'), nullable=True)
    is_public = db.Column(db.Boolean, default=False, nullable=False)
    created_by = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    def __repr__(self):
        return f'<Recipe {self.name}>'

class RecipeIngredient(db.Model):
    __tablename__ = 'recipe_ingredients'
    id = db.Column(db.Integer, primary_key=True)
    recipe_id = db.Column(db.Integer, db.ForeignKey('recipe.id'), nullable=False)
    ingredient_id = db.Column(db.Integer, db.ForeignKey('ingredients.id'), nullable=False)
    quantity = db.Column(db.String(50), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    
    # Relationships
    ingredient = db.relationship('Ingredient')
    
    def __repr__(self):
        return f'<RecipeIngredient {self.quantity} {self.ingredient.name if self.ingredient else "Unknown"}>'

class PantryItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    quantity = db.Column(db.String(50))
    unit = db.Column(db.String(50))
    aisle = db.Column(db.String(50))
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __repr__(self):
        return f'<PantryItem {self.name}>'

class Aisle(db.Model):
    __tablename__ = 'aisles'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False, unique=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    
    def __repr__(self):
        return f'<Aisle {self.name}>'

class Ingredient(db.Model):
    __tablename__ = 'ingredients'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False, unique=True)
    unit = db.Column(db.String(50), nullable=False)
    aisle_id = db.Column(db.Integer, db.ForeignKey('aisles.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    recipe_id = db.Column(db.Integer, db.ForeignKey('recipe.id'))

    # Relationships
    aisle = db.relationship('Aisle', backref='ingredients')
    
    def __repr__(self):
        return f'<Ingredient {self.name} ({self.unit})>'

class MealPlan(db.Model):
    """Model for storing the complete meal plan in the database."""
    id = db.Column(db.Integer, primary_key=True)
    day = db.Column(db.String(10), nullable=False)
    meal_type = db.Column(db.String(20), nullable=False)
    recipe_id = db.Column(db.Integer, db.ForeignKey('recipe.id'), nullable=True)
    account_id = db.Column(db.Integer, db.ForeignKey('account.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    is_locked = db.Column(db.Boolean, default=False, nullable=False)
    is_leftover = db.Column(db.Boolean, default=False, nullable=False)
    leftover_from_day = db.Column(db.String(10), nullable=True)
    leftover_from_meal_type = db.Column(db.String(20), nullable=True)
    
    # Relationships
    recipe = db.relationship('Recipe')
    account = db.relationship('Account')
    
    __table_args__ = (
        db.UniqueConstraint('day', 'meal_type', 'account_id', name='unique_day_meal_account'),
    )

    def __repr__(self):
        return f'<MealPlan {self.day} {self.meal_type} for account {self.account_id}>'

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
    # Query distinct aisles from Aisles table
    aisle_names = db.session.query(Aisle.name).filter(
        Aisle.name.isnot(None),
        Aisle.name != ''
    ).distinct().all()
    
    # Extract names from the result
    return sorted([name[0] for name in aisle_names if name[0]])

def get_meal_plan(account_id: int) -> Dict[str, Dict[str, Any]]:
    """Get the current meal plan for an account from the database."""
    plan = {}
    for entry in MealPlan.query.filter_by(account_id=account_id).all():
        day = entry.day
        meal_type = entry.meal_type
        
        if day not in plan:
            plan[day] = {}
            
        # Only include basic recipe info that's JSON serializable
        recipe_info = None
        if entry.recipe:
            recipe_info = {
                'id': entry.recipe.id,
                'name': entry.recipe.name,
                'servings': entry.recipe.servings,
                'is_breakfast': entry.recipe.is_breakfast,
                'is_lunch': entry.recipe.is_lunch,
                'is_dinner': entry.recipe.is_dinner,
                'method': entry.recipe.method,
                'source_link': entry.recipe.source_link
            }
            
        plan[day][meal_type] = {
            'recipe_id': entry.recipe_id,
            'is_locked': entry.is_locked,
            'recipe': recipe_info,
            'status': 'leftover' if entry.is_leftover else ('locked' if entry.is_locked else 'new'),
            'is_leftover': entry.is_leftover,
            'leftover_from_day': entry.leftover_from_day,
            'leftover_from_meal_type': entry.leftover_from_meal_type,
            'leftover_from': f"{entry.leftover_from_day}_{entry.leftover_from_meal_type}" 
                               if entry.is_leftover and entry.leftover_from_day and entry.leftover_from_meal_type 
                               else None
        }
    app.logger.info(f"Retrieved meal plan for account {account_id} with {len(plan)} days")
    return plan

def update_meal_plan(account_id: int, day: str, meal_type: str, recipe_id: Optional[int], is_locked: bool = False,
                    is_leftover: bool = False, leftover_from_day: Optional[str] = None, 
                    leftover_from_meal_type: Optional[str] = None) -> None:
    """
    Update or create a meal plan entry in the database.

    Args:
        account_id: ID of the account
        day: Day of the week (e.g., 'Monday')
        meal_type: Type of meal (e.g., 'Breakfast')
        recipe_id: ID of the recipe or None if not set
        is_locked: Whether the meal is locked
        is_leftover: Whether this is a leftover meal
        leftover_from_day: Day the original meal was from (for leftovers)
        leftover_from_meal_type: Type of the original meal (for leftovers)
    """
    try:
        # Try to find existing entry
        entry = MealPlan.query.filter_by(
            account_id=account_id,
            day=day,
            meal_type=meal_type
        ).first()
        
        if entry:
            # Update existing entry
            entry.recipe_id = recipe_id
            entry.is_locked = is_locked
            entry.is_leftover = is_leftover
            if is_leftover:
                entry.leftover_from_day = leftover_from_day
                entry.leftover_from_meal_type = leftover_from_meal_type
            else:
                entry.leftover_from_day = None
                entry.leftover_from_meal_type = None
        else:
            # Create new entry
            entry = MealPlan(
                account_id=account_id,
                day=day,
                meal_type=meal_type,
                recipe_id=recipe_id,
                is_locked=is_locked,
                is_leftover=is_leftover,
                leftover_from_day=leftover_from_day if is_leftover else None,
                leftover_from_meal_type=leftover_from_meal_type if is_leftover else None
            )
            db.session.add(entry)
            
        db.session.commit()
        app.logger.info(f"Updated meal plan for {day} {meal_type}: recipe_id={recipe_id}, locked={is_locked}")
    except Exception as e:
        db.session.rollback()
        app.logger.error(f"Error updating meal plan: {str(e)}", exc_info=True)
        raise

def sync_session_locks_with_db() -> None:
    """Sync session locks with database locks."""
    db_locks = get_persistent_locks()
    app.logger.info(f"Syncing session locks with database. Found {len(db_locks)} locks in database.")
    # Update session with database locks
    session['locked_meals'] = db_locks
    session.modified = True

def sync_meal_plan_with_session(account_id: int) -> None:
    """
    Sync the meal plan from database to session.
    Ensures the session contains a serializable version of the meal plan.
    """
    # Always sync from database to ensure we have the latest data
    meal_plan = get_meal_plan(account_id)
    
    # Update the session
    session['meal_plan'] = meal_plan
    session.modified = True
    app.logger.info("Synced meal plan from database to session")

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
            if meal_info and meal_info.get('recipe_id') not in (None, -1):
                unique_recipe_ids.add(meal_info['recipe_id'])
    app.logger.debug(f"[SHOPLIST] Unique recipe IDs for aggregation: {unique_recipe_ids}")
    
    # --- 2. Aggregate ingredients ---
    ingredient_map = defaultdict(lambda: {'quantity': 0, 'unit': None, 'aisle': None, 'recipes': set()})
    if unique_recipe_ids:
        # Eager load recipe_ingredients and their related ingredients
        recipes = Recipe.query.options(
            db.joinedload(Recipe.recipe_ingredients)
            .joinedload(RecipeIngredient.ingredient)
        ).filter(Recipe.id.in_(unique_recipe_ids)).all()
        
        for recipe in recipes:
            for recipe_ingredient in recipe.recipe_ingredients:
                ing = recipe_ingredient.ingredient
                key = (ing.name.strip().lower(), (ing.unit or '').strip().lower())
                try:
                    ingredient_map[key]['quantity'] += float(recipe_ingredient.quantity or 0)
                except (ValueError, TypeError):
                    ingredient_map[key]['quantity'] = 0
                ingredient_map[key]['unit'] = ing.unit
                ingredient_map[key]['aisle'] = ing.aisle.name if ing.aisle else 'Other'
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
            except (ValueError, TypeError):
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
@csrf.exempt
def toggle_meal_lock():
    data = request.get_json()
    
    slot_id = data.get('slot_id')
    locked = data.get('locked')
    
    # Force locked to boolean
    if isinstance(locked, str):
        locked = locked.lower() == 'true'
    
    if not slot_id or locked is None:
        return jsonify({'success': False, 'error': 'Missing slot_id or locked'}), 400
    
    # Get the current user's account
    account = current_user.accounts.first()
    if not account:
        return jsonify({'success': False, 'error': 'No account found'}), 400
    
    try:
        day, meal_type = slot_id.split('_')
        
        # Find the meal plan entry
        entry = MealPlan.query.filter_by(
            account_id=account.id,
            day=day,
            meal_type=meal_type
        ).first()
        
        if entry:
            # Update the lock status
            entry.is_locked = locked
            db.session.commit()
            app.logger.info(f"Updated lock status for {slot_id} to {locked}")
            
            # Update session
            if 'meal_plan' in session and day in session['meal_plan'] and meal_type in session['meal_plan'][day]:
                session['meal_plan'][day][meal_type]['is_locked'] = locked
                session.modified = True
                
            return jsonify({'success': True})
        else:
            return jsonify({'success': False, 'error': 'Meal plan entry not found'}), 404
            
    except Exception as e:
        db.session.rollback()
        app.logger.error(f"Error toggling meal lock: {str(e)}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500

def generate_meal_plan(num_people: int, locked_meals: LockedMealsDict, days: Optional[List[str]] = None) -> PlanIdsDict:
    app.logger.info("=== generate_meal_plan function called ===")
    
    try:
        flash('Meal plan generated successfully.', 'success')
        app.logger.info("Flash message set in generate_meal_plan")
    except Exception as e:
        app.logger.error(f"Error setting flash message in generate_meal_plan: {str(e)}")

    """
    Generates a meal plan for the specified days, considering locked meals and user default settings.
    Meals are generated in order: all breakfasts, then all lunches, then all dinners.
    Leftovers are handled by propagating them to the next day's same meal type.
    """
    print("=== MEAL PLAN GENERATION STARTED ===")
    print(f"Number of people: {num_people}")
    app.logger.info(f"Meal plan generation started for {num_people} people")
    print(f"Locked meals: {locked_meals}")
    
    if days is None:
        days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    print(f"Planning for days: {', '.join(days)}")
    
    # Initialize empty plan with all slots as None
    plan_ids: PlanIdsDict = {day: {meal_type: None for meal_type in meal_types} for day in days}
    
    # Track which slots are locked (these won't be modified by leftovers)
    locked_slots = set()
    
    # Fetch user default meal settings
    account = current_user.accounts.first()
    settings = getattr(account, 'settings', None)
    default_meals = {
        'Breakfast': getattr(settings, 'default_breakfast_id', None),
        'Lunch': getattr(settings, 'default_lunch_id', None),
        'Dinner': getattr(settings, 'default_dinner_id', None)
    }
    print(f"Default meals: {default_meals}")
    
    # Fetch all recipes once for efficiency
    all_recipes = Recipe.query.all()
    recipes_by_type = {
        meal_type: [r for r in all_recipes if getattr(r, f'is_{meal_type.lower()}', False)]
        for meal_type in meal_types
    }
    print(f"Found {len(all_recipes)} total recipes")
    for meal_type, recipes in recipes_by_type.items():
        print(f"  - {meal_type}: {len(recipes)} recipes")
    
    # --- PHASE 1: Process locked meals (highest priority) ---
    print("\n=== PROCESSING LOCKED MEALS ===")
    for slot_id, lock_info in locked_meals.items():
        try:
            day, meal_type = slot_id.split('_', 1)
            if day not in days or meal_type not in meal_types:
                print(f"  ! Invalid slot format or day/meal type: {slot_id}")
                continue
                
            if isinstance(lock_info, dict) and 'recipe_id' in lock_info:
                recipe_id = lock_info['recipe_id']
                if recipe_id == -1:  # Manual entry
                    plan_ids[day][meal_type] = {
                        'recipe_id': -1,
                        'manual_text': lock_info.get('text', 'Manual Entry'),
                        'status': 'locked',
                        'locked_by_main': True
                    }
                    print(f"  [LOCKED] {day} {meal_type}: Manual Entry")
                elif db.session.get(Recipe, recipe_id):  # Valid recipe
                    plan_ids[day][meal_type] = {
                        'recipe_id': recipe_id,
                        'status': 'locked',
                        'locked_by_main': True,
                        'default_lock': False
                    }
                    print(f"  [LOCKED] {day} {meal_type}: Recipe ID {recipe_id}")
                    locked_slots.add((day, meal_type))
                else:
                    print(f"  [WARNING] Recipe ID {recipe_id} not found for slot {slot_id}")
        except Exception as e:
            print(f"  [ERROR] Error processing locked meal {slot_id}: {str(e)}")
            app.logger.error(f"Error processing locked meal {slot_id}: {e}")
    
    # Track used recipe IDs to prevent duplicates (except for leftovers and defaults)
    used_recipe_ids = set()
    
    # Add locked recipe IDs to used set
    for day in days:
        for meal_type in meal_types:
            meal = plan_ids[day][meal_type]
            if meal and meal.get('recipe_id') and meal.get('recipe_id') != -1:
                used_recipe_ids.add(meal['recipe_id'])
    
    # Track all recipes that have been used in the plan
    all_used_recipe_ids = set(used_recipe_ids)  # Start with locked recipes
    
    # Create a mapping of default recipe IDs to their meal types
    default_recipe_to_meal_type = {int(recipe_id): meal_type 
                                 for meal_type, recipe_id in default_meals.items() 
                                 if recipe_id}
    
    # --- PHASE 2: Generate meals by type ---
    print("\n[GENERATING] MEALS")
    
    # First, create a list of all days and meal types that need to be filled
    meals_to_fill = []
    for day in days:
        for meal_type in meal_types:
            # Skip if already locked or assigned
            if (day, meal_type) in locked_slots or plan_ids[day][meal_type] is not None:
                continue
            meals_to_fill.append((day, meal_type))
    
    # Shuffle the meals to fill to ensure randomness
    random.shuffle(meals_to_fill)
    
    # Process each meal that needs to be filled
    for day, meal_type in meals_to_fill:
        print(f"\n[PROCESSING] {day} {meal_type}...")
        
        # Get the default recipe for this meal type (if any)
        default_recipe_id = default_meals.get(meal_type)
        
        # Filter available recipes for this meal type
        available_recipes = []
        for recipe in recipes_by_type[meal_type]:
            # Always include the default recipe for this meal type (even if used in other meal types)
            if recipe.id == default_recipe_id:
                available_recipes.append(recipe)
            # Include non-default recipes that haven't been used in any meal type
            elif recipe.id not in all_used_recipe_ids and recipe.id not in default_recipe_to_meal_type:
                available_recipes.append(recipe)
        
        # Fallback to all recipes if needed (shouldn't be necessary with default recipes)
        if not available_recipes and recipes_by_type[meal_type]:
            available_recipes = [r for r in recipes_by_type[meal_type] 
                              if r.id not in all_used_recipe_ids]
        
        print(f"  Available {meal_type} recipes: {len(available_recipes)} (excluding {len(all_used_recipe_ids)} used recipes)")
        
        # Step 1: Try to assign default meal if available
        if default_recipe_id:
            # Only use default meal if it's the default for this specific meal type
            if int(default_recipe_id) in default_recipe_to_meal_type.get(meal_type, []):
                plan_ids[day][meal_type] = {
                    'recipe_id': int(default_recipe_id),
                    'status': 'default',
                    'locked_by_main': False,
                    'default_lock': True
                }
                # Don't add default recipes to used set to allow multiple instances in this meal type
                print(f"  [ADDED] {day} {meal_type} to default recipe {default_recipe_id}")
                continue
        
        # Step 2: Assign random meal if available
        if available_recipes:
            # Filter out recipes that are default for any meal type (unless it's the current meal type's default)
            valid_recipes = [r for r in available_recipes 
                           if r.id not in default_recipe_to_meal_type or 
                           (default_meals.get(meal_type) and r.id == int(default_meals[meal_type]))]
            
            if valid_recipes:
                chosen_recipe = random.choice(valid_recipes)
                plan_ids[day][meal_type] = {
                    'recipe_id': chosen_recipe.id,
                    'status': 'new',
                    'locked_by_main': False
                }
                # Only add to used set if it's not a default recipe
                if chosen_recipe.id not in default_recipe_to_meal_type:
                    all_used_recipe_ids.add(chosen_recipe.id)
                print(f"  [ASSIGNED] Random {meal_type} to {day}: {chosen_recipe.name} (ID: {chosen_recipe.id})")
            else:
                print(f"  [WARNING] No valid non-default recipes available for {day} {meal_type}")
        else:
            print(f"  [WARNING] No available recipes for {day} {meal_type}")
            
        # If we couldn't assign a recipe, mark the slot as empty
        if plan_ids[day][meal_type] is None:
            print(f"  [ERROR] Failed to assign a recipe to {day} {meal_type}")
            plan_ids[day][meal_type] = {
                'recipe_id': -1,
                'status': 'empty',
                'manual_text': 'No recipe available',
                'locked_by_main': False
            }
    
    # --- PHASE 3: Process leftovers ---
    print("\n[PROCESSING] LEFTOVERS")
    # Create a list to track which days already have leftovers assigned
    leftover_days = {day: set() for day in days}
    
    # Process each day in order
    for day_idx, day in enumerate(days):
        for meal_type in meal_types:
            # Skip if already a leftover (but don't skip locked meals)
            if plan_ids[day][meal_type] and plan_ids[day][meal_type].get('status') == 'leftover':
                continue
                
            meal = plan_ids[day][meal_type]
            if not meal or meal.get('recipe_id') is None or meal.get('recipe_id') == -1:
                continue
                
            try:
                recipe = db.session.get(Recipe, meal['recipe_id'])
                if not recipe or not recipe.servings or not num_people or recipe.servings <= num_people:
                    continue
                
                # Calculate how many extra full meals we can make
                extra_meals = (recipe.servings // num_people) - 1
                if extra_meals <= 0:
                    continue
                    
                print(f"  [INFO] {day} {meal_type} has {recipe.servings} servings for {num_people} people -> {extra_meals} extra meal(s) possible")
                
                # Find the next available day for leftovers of this meal type
                leftovers_assigned = 0
                for next_day_idx in range(day_idx + 1, min(day_idx + 1 + extra_meals, len(days))):
                    next_day = days[next_day_idx]
                    
                    # Skip if this day already has leftovers for this meal type
                    if meal_type in leftover_days[next_day]:
                        continue
                        
                    # Skip if locked (unless it's the same meal we're propagating from)
                    if (next_day, meal_type) in locked_slots:
                        # If this is the same recipe as the locked meal, count it as used
                        next_meal = plan_ids[next_day][meal_type]
                        if next_meal and next_meal.get('recipe_id') == recipe.id:
                            print(f"    [INFO] Found matching locked meal at {next_day} {meal_type}, counting as leftover usage")
                            leftovers_assigned += 1
                            # If we've used up all extra meals, break the loop
                            if leftovers_assigned >= extra_meals:
                                break
                        continue
                    
                    # Assign the leftover with origin information
                    plan_ids[next_day][meal_type] = {
                        'recipe_id': recipe.id,
                        'status': 'leftover',
                        'locked_by_main': False,
                        'leftover_from': f"{day}_{meal_type}",
                        'leftover_from_day': day,
                        'leftover_from_meal': meal_type,
                        'servings_used': num_people
                    }
                    leftover_days[next_day].add(meal_type)
                    leftovers_assigned += 1
                    print(f"    [ASSIGNED] Set {next_day} {meal_type} as leftover from {day} {meal_type}")
                    
                    # Stop if we've assigned all possible leftovers
                    if leftovers_assigned >= extra_meals:
                        break
                        
            except Exception as e:
                print(f"    [ERROR] Error processing leftovers for {day} {meal_type}: {str(e)}")
                app.logger.error(f"Error processing leftovers for {day} {meal_type}: {e}")
    
    # --- FINAL VALIDATION AND LOGGING ---
    print("\n[COMPLETE] MEAL PLAN GENERATION FINISHED\n")
    print("\n[MEAL PLAN] Final Meal Plan Summary:")
    
    # Count stats
    stats = {
        'total_meals': 0,
        'locked': 0,
        'default': 0,
        'random': 0,
        'leftover': 0,
        'empty': 0
    }
    
    for day in days:
        print(f"\n{day}:")
        for meal_type in meal_types:
            meal = plan_ids[day][meal_type]
            if not meal:
                print(f"  {meal_type}: Not assigned")
                stats['empty'] += 1
                continue
                
            status_emoji = {
                'locked': '*',
                'default': '+',
                'new': '~',
                'leftover': '^',
                'manual': '#'
            }.get(meal.get('status', ''), '?')
            
            if meal.get('recipe_id') == -1:  # Manual entry
                print(f"  {meal_type}: {status_emoji} Manual Entry: {meal.get('manual_text', '')}")
                stats['locked'] += 1
            else:
                recipe = db.session.get(Recipe, meal['recipe_id']) if meal['recipe_id'] else None
                name = recipe.name if recipe else f"Unknown Recipe (ID: {meal['recipe_id']})"
                status = meal.get('status', 'unknown')
                print(f"  {meal_type}: {status_emoji} {name} (ID: {meal['recipe_id']}, Status: {status})")
                if meal.get('leftover_from'):
                    print(f"    -> Leftover from: {meal['leftover_from']}")
                
                # Update stats
                if status == 'locked':
                    stats['locked'] += 1
                elif status == 'default':
                    stats['default'] += 1
                elif status == 'new':
                    stats['random'] += 1
                elif status == 'leftover':
                    stats['leftover'] += 1
                else:
                    stats['empty'] += 1
            
            stats['total_meals'] += 1
    
    # Print summary
    print("\n=== MEAL PLAN STATISTICS ===")
    print(f"Total meals: {stats['total_meals']}")
    print(f"  - Locked meals: {stats['locked']}")
    print(f"  - Default meals: {stats['default']}")
    print(f"  - Random meals: {stats['random']}")
    print(f"  - Leftovers planned: {stats['leftover']} meals")
    print(f"Empty slots: {stats['empty']}")
    
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
    # Get the current user's account
    account = current_user.accounts.first()
    if not account:
        flash('No account found. Please contact support.', 'error')
        return redirect(url_for('logout'))
    
    # Get account settings
    settings = getattr(account, 'settings', None)
    if not settings:
        # Create default settings if they don't exist
        settings = AccountSettings(account=account)
        db.session.add(settings)
        db.session.commit()
    
    # Get meal plan settings with defaults
    meal_plan_start_day = getattr(settings, 'meal_plan_start_day', 'Monday')
    meal_plan_duration = getattr(settings, 'meal_plan_duration', 7)
    num_people = getattr(settings, 'num_people', 2)
    
    # Validate and sanitize settings
    try:
        meal_plan_duration = max(1, min(31, int(meal_plan_duration)))
    except (ValueError, TypeError):
        meal_plan_duration = 7
    
    try:
        num_people = max(1, int(num_people))
    except (ValueError, TypeError):
        num_people = 2
    
    # Compute the days for the plan, starting from meal_plan_start_day
    start_idx = ALL_DAYS.index(meal_plan_start_day) if meal_plan_start_day in ALL_DAYS else 0
    days = [ALL_DAYS[(start_idx + i) % 7] for i in range(meal_plan_duration)]
    
    # Sync meal plan with session
    sync_meal_plan_with_session(account.id)
    
    # Get the current meal plan from session
    meal_plan = session.get('meal_plan', {})
    
    # Handle POST request (form submission for generating a new meal plan)
    if request.method == 'POST':
        # Get locked meals from the database
        locked_meals = {}
        for day in days:
            for meal_type in meal_types:
                slot_id = f"{day}_{meal_type}"
                meal_entry = MealPlan.query.filter_by(
                    account_id=account.id,
                    day=day,
                    meal_type=meal_type,
                    is_locked=True
                ).first()
                
                if meal_entry and meal_entry.recipe_id:
                    locked_meals[slot_id] = {
                        'recipe_id': meal_entry.recipe_id,
                        'is_locked': True
                    }
        
        try:
            # Generate a new meal plan
            new_plan = generate_meal_plan(num_people, locked_meals, days)
            
            # Start a transaction to update the meal plan
            try:
                # Delete existing meal plan entries for this account
                MealPlan.query.filter_by(account_id=account.id).delete()
                
                # Create new meal plan entries
                for day, meals in new_plan.items():
                    for meal_type, meal_info in meals.items():
                        is_locked = locked_meals.get(f"{day}_{meal_type}", {}).get('is_locked', False)
                        is_leftover = meal_info.get('status') == 'leftover'
                        leftover_from_day = meal_info.get('leftover_from_day') if is_leftover else None
                        leftover_from_meal_type = meal_info.get('leftover_from_meal') if is_leftover else None
                        
                        entry = MealPlan(
                            account_id=account.id,
                            day=day,
                            meal_type=meal_type,
                            recipe_id=meal_info.get('recipe_id'),
                            is_locked=is_locked,
                            is_leftover=is_leftover,
                            leftover_from_day=leftover_from_day,
                            leftover_from_meal_type=leftover_from_meal_type
                        )
                        db.session.add(entry)
                
                db.session.commit()
                
                # Update session with the new plan
                session['meal_plan'] = get_meal_plan(account.id)
                session.modified = True
                
                flash('Meal plan generated successfully!', 'success')
                
            except Exception as e:
                db.session.rollback()
                app.logger.error(f"Error saving meal plan to database: {str(e)}", exc_info=True)
                flash('Error saving meal plan. Please try again.', 'error')
            
            return redirect(url_for('dashboard'))
            
        except Exception as e:
            app.logger.error(f"Error generating meal plan: {str(e)}", exc_info=True)
            flash(f'Error generating meal plan: {str(e)}', 'error')
    
    # Fetch all recipes for the manual selection dropdown
    all_recipes = Recipe.query.filter(
        (Recipe.account_id == account.id) | (Recipe.is_public == True)
    ).all()
    
    # Get the current meal plan from the database
    meal_plan = get_meal_plan(account.id)
    
    return render_template(
        'dashboard.html',
        days=days,
        meal_types=meal_types,
        all_recipes=all_recipes,
        num_people=num_people,
        meal_plan=meal_plan
    )


@app.route('/api/ingredients', methods=['GET'])
@login_required
def get_all_ingredients():
    """API endpoint to get all ingredients with their details for autocomplete."""
    try:
        ingredients = Ingredient.query.options(joinedload(Ingredient.aisle)).all()
        return jsonify([{
            'id': ing.id,
            'name': ing.name,
            'unit': ing.unit or 'unit',
            'aisle': ing.aisle.name if ing.aisle else 'Misc'
        } for ing in ingredients])
    except Exception as e:
        current_app.logger.error(f"Error fetching ingredients: {str(e)}")
        return jsonify({'error': 'Failed to fetch ingredients'}), 500

@app.route('/api/ingredients', methods=['POST'])
@login_required
def add_ingredient_api():
    try:
        import traceback
        print("Received request data:", request.get_json())  # Debug log
        data = request.get_json()
        name = data.get('name', '').strip()
        unit = data.get('unit', '').strip()
        aisle_name = data.get('aisle', '').strip()
        
        print(f"Processing new ingredient - Name: {name}, Unit: {unit}, Aisle: {aisle_name}")  # Debug log
        
        # Validate input
        if not all([name, unit, aisle_name]):
            error_msg = f"Missing required fields. Name: {name}, Unit: {unit}, Aisle: {aisle_name}"
            print(error_msg)  # Debug log
            return jsonify({'success': False, 'message': 'All fields are required'}), 400
            
        # Check if ingredient already exists (case-insensitive)
        existing = Ingredient.query.filter(func.lower(Ingredient.name) == name.lower()).first()
        if existing:
            print(f"Ingredient already exists: {name}")  # Debug log
            return jsonify({
                'success': False, 
                'message': f'Ingredient "{name}" already exists',
                'ingredient': {
                    'id': existing.id,
                    'name': existing.name,
                    'unit': existing.unit,
                    'aisle': existing.aisle.name if existing.aisle else ''
                }
            }), 400
            
        # Find or create aisle
        print(f"Looking for aisle: {aisle_name}")  # Debug log
        aisle = Aisle.query.filter(func.lower(Aisle.name) == aisle_name.lower()).first()
        if not aisle:
            print(f"Creating new aisle: {aisle_name}")  # Debug log
            try:
                aisle = Aisle(name=aisle_name)
                db.session.add(aisle)
                db.session.flush()  # Get the new aisle ID
                print(f"Created new aisle with ID: {aisle.id}")  # Debug log
            except Exception as e:
                print(f"Error creating aisle: {str(e)}")  # Debug log
                raise
            
        # Create new ingredient
        print(f"Creating new ingredient: {name}")  # Debug log
        try:
            new_ingredient = Ingredient(
                name=name,
                unit=unit,
                aisle_id=aisle.id
            )
            db.session.add(new_ingredient)
            db.session.commit()
            print(f"Successfully created ingredient with ID: {new_ingredient.id}")  # Debug log
            
            return jsonify({
                'success': True,
                'message': 'Ingredient added successfully',
                'ingredient': {
                    'id': new_ingredient.id,
                    'name': new_ingredient.name,
                    'unit': new_ingredient.unit,
                    'aisle': aisle_name
                }
            })
            
        except Exception as e:
            print(f"Error creating ingredient: {str(e)}")  # Debug log
            db.session.rollback()
            raise
        
    except Exception as e:
        db.session.rollback()
        error_traceback = traceback.format_exc()
        print(f"Error in add_ingredient_api: {error_traceback}")  # Debug log
        return jsonify({
            'success': False,
            'message': f'Failed to add ingredient. Error: {str(e)}',
            'debug': error_traceback if app.debug else None
        }), 500

@app.route('/add', methods=['GET', 'POST'])
@login_required
def add_recipe():
    # Get all distinct aisle names from the Aisle table
    distinct_aisles = db.session.query(Aisle.name).distinct().all()
    distinct_aisles = [str(aisle[0]) for aisle in distinct_aisles if aisle[0] and (isinstance(aisle[0], str) and aisle[0].strip())]
    
    # Get all ingredients for the dropdown with their details
    all_ingredients = db.session.query(
        Ingredient.id,
        Ingredient.name,
        Ingredient.unit,
        Aisle.name.label('aisle_name')
    ).join(Aisle, Ingredient.aisle_id == Aisle.id)\
     .order_by(Ingredient.name).all()
    
    # Convert to list of dictionaries for JSON serialization
    ingredients_data = [{
        'id': ing[0],  # First item is id
        'name': ing[1],  # Second item is name
        'unit': ing[2] or 'unit',  # Third item is unit
        'aisle': ing[3] or 'Misc'  # Fourth item is aisle_name
    } for ing in all_ingredients]
    
    # Convert all_ingredients to a list of dictionaries for JSON serialization
    all_ingredients = [{
        'id': ing[0],
        'name': ing[1],
        'unit': ing[2] or 'unit',
        'aisle': ing[3] or 'Misc'
    } for ing in all_ingredients]
    
    # Initialize form data for GET request
    form_ingredients = [{'id': '', 'name': '', 'quantity': '', 'unit': '', 'aisle': ''}]
    
    if request.method == 'POST':
        try:
            # Determine if the request is JSON or form data
            if request.is_json:
                data = request.get_json()
                name = data.get('name', '').strip()
                method = data.get('method', '').strip()
                servings_str = str(data.get('servings', '1')).strip()
                source_link = data.get('source_link', '').strip() or None
                is_breakfast = data.get('is_breakfast', False)
                is_lunch = data.get('is_lunch', False)
                is_dinner = data.get('is_dinner', False)
                
                # Get ingredients from the JSON data
                ingredients = data.get('ingredients', [])
                ingredient_ids = [ing.get('ingredient_id') for ing in ingredients]
                ingredient_quantities = [ing.get('quantity') for ing in ingredients]
                ingredient_units = [ing.get('unit', '') for ing in ingredients]
                ingredient_aisles = [ing.get('aisle', '') for ing in ingredients]
                ingredient_names = [ing.get('name', '') for ing in ingredients]
            else:
                # Get form data from form submission
                name = request.form.get('name', '').strip()
                method = request.form.get('method', '').strip()
                servings_str = request.form.get('servings', '1').strip()
                source_link = request.form.get('source_link', '').strip() or None
                is_breakfast = 'is_breakfast' in request.form
                is_lunch = 'is_lunch' in request.form
                is_dinner = 'is_dinner' in request.form

                # Get ingredient data from form - new format with arrays
                ingredient_ids = request.form.getlist('ingredient_ids[]')
                ingredient_quantities = request.form.getlist('ingredient_quantities[]')
                ingredient_units = request.form.getlist('ingredient_units[]')
                ingredient_aisles = request.form.getlist('ingredient_aisles[]')
                ingredient_names = request.form.getlist('ingredient_names[]')

            # --- Validation ---
            errors = False
            if not name:
                if request.is_json:
                    return jsonify({
                        'success': False,
                        'message': 'Recipe name is required.'
                    }), 400
                flash("Recipe name is required.", "danger")
                errors = True
                
            if not servings_str:
                if request.is_json:
                    return jsonify({
                        'success': False,
                        'message': 'Servings is required.'
                    }), 400
                flash("Servings is required.", "danger")
                errors = True
            
            # Check for at least one valid ingredient
            if not any(iid.strip() or name.strip() for iid, name in zip(ingredient_ids, ingredient_names) if iid and iid.strip()):
                if request.is_json:
                    return jsonify({
                        'success': False,
                        'message': 'At least one ingredient is required.'
                    }), 400
                flash("At least one ingredient is required.", "danger")
                errors = True

            # Validate servings
            servings_int = 1
            if servings_str:
                try:
                    servings_int = int(servings_str)
                    if servings_int <= 0:
                        if request.is_json:
                            return jsonify({
                                'success': False,
                                'message': 'Servings must be a positive whole number.'
                            }), 400
                        flash("Servings must be a positive whole number.", "danger")
                        errors = True
                except ValueError:
                    if request.is_json:
                        return jsonify({
                            'success': False,
                            'message': 'Servings must be a valid whole number.'
                        }), 400
                    flash("Servings must be a valid whole number.", "danger")
                    errors = True

            # Check for duplicate recipe name (case-insensitive) across user's accounts
            if name and Recipe.query.filter(
                func.lower(Recipe.name) == name.lower(),
                Recipe.account_id.in_([acc.id for acc in current_user.accounts])
            ).first():
                error_msg = f"A recipe named '{name}' already exists in your account. Please choose a different name."
                if request.is_json:
                    return jsonify({
                        'success': False,
                        'message': error_msg
                    }), 400
                flash(error_msg, "warning")
                errors = True

            if errors:
                if request.is_json:
                    return jsonify({
                        'success': False,
                        'message': 'Please correct the errors in the form.'
                    }), 400
                return render_template('add_recipe_V1.html',
                                   form_ingredients=form_ingredients,
                                   ingredients_data=ingredients_data,
                                   all_ingredients=all_ingredients,
                                   distinct_aisles=distinct_aisles,
                                   name=name,
                                   source_link=source_link or '',
                                   servings=servings_str,
                                   method=method,
                                   is_breakfast=is_breakfast,
                                   is_lunch=is_lunch,
                                   is_dinner=is_dinner)

            # --- Save the recipe ---
            # Get the first account the user is associated with
            account_id = current_user.accounts.first().id if current_user.accounts.first() else None
            
            # Create new recipe
            new_recipe = Recipe(
                name=name,
                method=method,
                servings=servings_int,
                source_link=source_link,
                is_breakfast=is_breakfast,
                is_lunch=is_lunch,
                is_dinner=is_dinner,
                account_id=account_id,
                created_by=current_user.id
            )
            
            db.session.add(new_recipe)
            db.session.flush()  # This will assign an ID to new_recipe without committing
            
            # Process ingredients
            for i in range(len(ingredient_ids)):
                ing_id = ingredient_ids[i] if i < len(ingredient_ids) else ''
                qty = ingredient_quantities[i] if i < len(ingredient_quantities) else ''
                unit = ingredient_units[i] if i < len(ingredient_units) else ''
                aisle = ingredient_aisles[i] if i < len(ingredient_aisles) else ''
                ing_name = ingredient_names[i] if i < len(ingredient_names) else ''
                
                # Skip if no ingredient ID or name
                if not ing_id and not ing_name:
                    continue
                    
                # If we have an ingredient ID, use it
                if ing_id and ing_id.strip():
                    ingredient = Ingredient.query.get(ing_id)
                    if not ingredient:
                        # If ingredient doesn't exist, skip or create a new one
                        continue
                else:
                    # Create a new ingredient
                    # First, find or create the aisle
                    aisle_obj = Aisle.query.filter_by(name=aisle).first()
                    if not aisle_obj and aisle:
                        aisle_obj = Aisle(name=aisle)
                        db.session.add(aisle_obj)
                        db.session.flush()
                    
                    # Create the ingredient
                    ingredient = Ingredient(
                        name=ing_name,
                        unit=unit or 'unit',
                        aisle_id=aisle_obj.id if aisle_obj else None
                    )
                    db.session.add(ingredient)
                    db.session.flush()
                
                # Add recipe ingredient
                if ingredient:
                    recipe_ingredient = RecipeIngredient(
                        recipe_id=new_recipe.id,
                        ingredient_id=ingredient.id,
                        quantity=str(qty) if qty else '1'
                    )
                    db.session.add(recipe_ingredient)
            
            # Commit all changes
            db.session.commit()
            
            if request.is_json:
                return jsonify({
                    'success': True,
                    'message': 'Recipe added successfully!',
                    'redirect': url_for('dashboard')
                })
                
            flash('Recipe added successfully!', 'success')
            return redirect(url_for('dashboard'))
            
        except Exception as e:
            db.session.rollback()
            error_msg = f'Error saving recipe: {str(e)}'
            print(error_msg)  # Log the error
            
            if request.is_json:
                return jsonify({
                    'success': False,
                    'message': error_msg
                }), 500
            
            flash(error_msg, 'danger')
            return render_template('add_recipe_V1.html',
                               form_ingredients=form_ingredients,
                               ingredients_data=ingredients_data,
                               all_ingredients=all_ingredients,
                               distinct_aisles=distinct_aisles,
                               name=request.form.get('name', ''),
                               source_link=request.form.get('source_link', ''),
                               servings=request.form.get('servings', ''),
                               method=request.form.get('method', ''),
                               is_breakfast='is_breakfast' in request.form,
                               is_lunch='is_lunch' in request.form,
                               is_dinner='is_dinner' in request.form)

            # Start a transaction
            try:
                # --- Create Recipe ---
                new_recipe = Recipe(
                    name=name,
                    source_link=source_link,
                    method=method,
                    servings=servings_int,
                    is_breakfast=is_breakfast,
                    is_lunch=is_lunch,
                    is_dinner=is_dinner,
                    account_id=current_user.accounts[0].id,  # Use the first account
                    created_by=current_user.id
                )
                db.session.add(new_recipe)
                db.session.flush()  # Get the new_recipe.id

                # --- Process Ingredients ---
                for ing_data in ingredients:
                    # Find or create ingredient
                    if ing_data['id'] and ing_data['id'].isdigit():
                        # Existing ingredient
                        ingredient = Ingredient.query.get(int(ing_data['id']))
                        if not ingredient:
                            raise ValueError(f"Ingredient with ID {ing_data['id']} not found")
                    else:
                        # New ingredient - find or create
                        ingredient = Ingredient.query.filter(
                            func.lower(Ingredient.name) == ing_data['name'].lower()
                        ).first()
                        
                        if not ingredient:
                            # Create new aisle if needed
                            aisle = None
                            if ing_data['aisle']:
                                aisle = Aisle.query.filter(
                                    func.lower(Aisle.name) == ing_data['aisle'].lower()
                                ).first()
                                
                                if not aisle:
                                    aisle = Aisle(name=ing_data['aisle'])
                                    db.session.add(aisle)
                                    db.session.flush()
                            
                            # Create new ingredient
                            ingredient = Ingredient(
                                name=ing_data['name'],
                                unit=ing_data['unit'] or 'unit',
                                aisle_id=aisle.id if aisle else None
                            )
                            db.session.add(ingredient)
                            db.session.flush()
                    
                    # Create recipe ingredient
                    recipe_ingredient = RecipeIngredient(
                        recipe_id=new_recipe.id,
                        ingredient_id=ingredient.id,
                        quantity=str(ing_data['quantity'])
                    )
                    db.session.add(recipe_ingredient)
                
                # Commit all changes
                db.session.commit()
                flash('Recipe added successfully!', 'success')
                return redirect(url_for('view_recipe', recipe_id=new_recipe.id))
                
            except Exception as e:
                db.session.rollback()
                app.logger.error(f'Error adding recipe: {str(e)}', exc_info=True)
                flash(f'An error occurred while adding the recipe: {str(e)}', 'danger')
                
                # Reconstruct form data for repopulation using the ingredients list we built
                form_ingredients = []
                for ing in ingredients:
                    form_ingredients.append({
                        'id': ing['id'],
                        'name': ing['name'],
                        'quantity': ing['quantity'],
                        'unit': ing['unit'],
                        'aisle': ing['aisle']
                    })
                
                # Add empty row if no ingredients yet
                if not form_ingredients:
                    form_ingredients.append({
                        'id': '',
                        'name': '',
                        'quantity': '',
                        'unit': '',
                        'aisle': ''
                    })
                
                return render_template('add_recipe_V1.html',
                                   form_ingredients=form_ingredients,
                                   all_ingredients=all_ingredients,
                                   distinct_aisles=distinct_aisles,
                                   name=name,
                                   source_link=source_link or '',
                                   servings=servings_str,
                                   method=method,
                                   is_breakfast=is_breakfast,
                                   is_lunch=is_lunch,
                                   is_dinner=is_dinner)

        except Exception as e:
            db.session.rollback()
            app.logger.error(f'Error in add_recipe: {str(e)}', exc_info=True)
            flash(f'An error occurred while processing your request: {str(e)}', 'danger')
            
            # Reconstruct form data for repopulation using the ingredients list we built
            form_ingredients = []
            if 'ingredients' in locals():
                for ing in ingredients:
                    form_ingredients.append({
                        'id': ing.get('id', ''),
                        'name': ing.get('name', ''),
                        'quantity': ing.get('quantity', ''),
                        'unit': ing.get('unit', ''),
                        'aisle': ing.get('aisle', '')
                    })
            
            # Add empty row if no ingredients yet
            if not form_ingredients:
                form_ingredients.append({
                    'id': '',
                    'name': '',
                    'quantity': '',
                    'unit': '',
                    'aisle': ''
                })
            
            return render_template('add_recipe_V1.html',
                               form_ingredients=form_ingredients,
                               all_ingredients=all_ingredients,
                               distinct_aisles=distinct_aisles,
                               name=name,
                               source_link=source_link or '',
                               servings=servings_str,
                               method=method,
                               is_breakfast=is_breakfast,
                               is_lunch=is_lunch,
                               is_dinner=is_dinner)

    # --- GET Request ---
    # For a new recipe, start with one empty ingredient row
    form_ingredients = [{
        'id': '',
        'name': '',
        'quantity': '',
        'unit': '',
        'aisle': ''
    }]
    
    # Convert all_ingredients to the format expected by the frontend
    ingredients_data = []
    if all_ingredients:
        ingredients_data = [{
            'id': ing.get('id', ''),
            'name': ing.get('name', ''),
            'unit': ing.get('unit', ''),
            'aisle': ing.get('aisle', '')
        } for ing in all_ingredients]
    
    # Debug logging
    print("\n=== DEBUG: Ingredients Data ===")
    print(f"Number of ingredients: {len(ingredients_data)}")
    if ingredients_data:
        print("Sample ingredients:", ingredients_data[:3])
    print("\n=== DEBUG: Distinct Aisles ===")
    print(distinct_aisles)
    print("=" * 30 + "\n")
    
    return render_template('add_recipe_V1.html',
                         form_ingredients=form_ingredients,
                         ingredients_data=ingredients_data,
                         all_ingredients=all_ingredients,
                         distinct_aisles=distinct_aisles,
                         name='',
                         source_link='',
                         servings='',
                         method='',
                         is_breakfast=False,
                         is_lunch=False,
                         is_dinner=False)


@app.route('/view_recipe/<int:recipe_id>')
def view_recipe(recipe_id: int):
    # Use get_or_404 for robust fetching by ID
    recipe = Recipe.query.options(
        joinedload(Recipe.recipe_ingredients)
        .joinedload(RecipeIngredient.ingredient)
        .joinedload(Ingredient.aisle)
    ).get_or_404(recipe_id)
    return render_template('view_recipe.html', recipe=recipe)

@app.route('/edit_recipe/<int:recipe_id>', methods=['GET', 'POST'])
@login_required
def edit_recipe(recipe_id: int):
    """Edit an existing recipe."""
    # Get all ingredients for autocomplete
    all_ingredients = [{
        'id': ing.id,
        'name': ing.name,
        'unit': ing.unit or 'unit',
        'aisle': ing.aisle.name if ing.aisle else 'Misc'
    } for ing in Ingredient.query.options(joinedload(Ingredient.aisle)).all()]
    
    # Get the recipe with its ingredients
    recipe = Recipe.query.options(
        joinedload(Recipe.recipe_ingredients).joinedload(RecipeIngredient.ingredient)
    ).get_or_404(recipe_id)
    
    # Check if user has permission to edit this recipe
    if not current_user.is_admin and (not recipe.account_id or 
                                    not any(acc.id == recipe.account_id for acc in current_user.accounts)):
        flash("You don't have permission to edit this recipe.", "danger")
        return redirect(url_for('dashboard'))
    
    # Get distinct aisles for the ingredient modal
    distinct_aisles = get_distinct_aisles()
    
    if request.method == 'POST':
        # Get form data
        name = request.form.get('name', '').strip()
        source_link = request.form.get('source_link', '').strip()
        servings = request.form.get('servings', '1').strip()
        method = request.form.get('method', '').strip()
        is_breakfast = 'is_breakfast' in request.form
        is_lunch = 'is_lunch' in request.form
        is_dinner = 'is_dinner' in request.form
        
        # Get ingredient data
        ingredient_ids = request.form.getlist('ingredient_ids[]')
        ingredient_quantities = request.form.getlist('ingredient_quantities[]')
        ingredient_units = request.form.getlist('ingredient_units[]')
        ingredient_aisles = request.form.getlist('ingredient_aisles[]')
        ingredient_names = request.form.getlist('ingredient_names[]')
        
        # Validate form data
        errors = False
        
        # Validate recipe name
        if not name:
            flash('Recipe name is required.', 'danger')
            errors = True
        else:
            # Check for duplicate recipe name (case-insensitive, excluding current recipe)
            existing_recipe = Recipe.query.filter(
                func.lower(Recipe.name) == func.lower(name),
                Recipe.id != recipe_id,
                Recipe.account_id.in_([acc.id for acc in current_user.accounts])
            ).first()
            if existing_recipe:
                flash('A recipe with this name already exists in your account.', 'danger')
                errors = True
        
        # Validate servings
        try:
            servings_int = int(servings)
            if servings_int < 1:
                flash('Servings must be at least 1.', 'danger')
                errors = True
        except (ValueError, TypeError):
            flash('Invalid number of servings.', 'danger')
            errors = True
        
        # Validate at least one meal type is selected
        if not (is_breakfast or is_lunch or is_dinner):
            flash('Please select at least one meal type.', 'danger')
            errors = True
        
        # Validate ingredients
        ingredients = []
        for i in range(max(len(ingredient_ids), len(ingredient_names))):
            ing_id = ingredient_ids[i] if i < len(ingredient_ids) else ''
            qty = ingredient_quantities[i] if i < len(ingredient_quantities) else ''
            unit = ingredient_units[i] if i < len(ingredient_units) else ''
            aisle = ingredient_aisles[i] if i < len(ingredient_aisles) else ''
            ing_name = ingredient_names[i] if i < len(ingredient_names) else ''

            # Skip empty rows
            if not (ing_id.strip() or ing_name.strip()):
                continue

            # Validate quantity
            try:
                qty_float = float(qty) if qty else 0.0
                if qty_float <= 0:
                    flash("Quantity must be a positive number.", "danger")
                    errors = True
                    break
            except ValueError:
                flash(f"Invalid quantity for ingredient: {ing_name or 'Unknown'}", "danger")
                errors = True
                break

            ingredients.append({
                'id': ing_id,
                'name': ing_name,
                'quantity': qty,
                'unit': unit,
                'aisle': aisle
            })

        if not ingredients:
            flash("At least one valid ingredient is required.", "danger")
            errors = True
        
        # If there are validation errors, re-render the form with the entered data
        if errors:
            return render_template('edit_recipe_v1.html', 
                                recipe=recipe,
                                form_ingredients=ingredients or [{'id': '', 'name': '', 'quantity': '', 'unit': '', 'aisle': ''}],
                                all_ingredients=all_ingredients,
                                distinct_aisles=distinct_aisles,
                                name=name,
                                source_link=source_link,
                                servings=servings,
                                method=method,
                                is_breakfast=is_breakfast,
                                is_lunch=is_lunch,
                                is_dinner=is_dinner)
        
        # Update recipe details in a transaction
        try:
            recipe.name = name
            recipe.source_link = source_link or None
            recipe.servings = servings_int
            recipe.method = method or None
            recipe.is_breakfast = is_breakfast
            recipe.is_lunch = is_lunch
            recipe.is_dinner = is_dinner
            
            # Update recipe ingredients
            # First, delete existing recipe ingredients
            RecipeIngredient.query.filter_by(recipe_id=recipe.id).delete()
            
            # Process each ingredient
            for ing_data in ingredients:
                # Find or create ingredient
                if ing_data['id'] and ing_data['id'].isdigit():
                    # Existing ingredient
                    ingredient = Ingredient.query.get(int(ing_data['id']))
                    if not ingredient:
                        raise ValueError(f"Ingredient with ID {ing_data['id']} not found")
                else:
                    # New ingredient - find or create
                    ingredient = Ingredient.query.filter(
                        func.lower(Ingredient.name) == ing_data['name'].lower()
                    ).first()
                    
                    if not ingredient:
                        # Create new aisle if needed
                        aisle = None
                        if ing_data['aisle']:
                            aisle = Aisle.query.filter(
                                func.lower(Aisle.name) == ing_data['aisle'].lower()
                            ).first()
                            
                            if not aisle:
                                aisle = Aisle(name=ing_data['aisle'])
                                db.session.add(aisle)
                                db.session.flush()
                        
                        # Create new ingredient
                        ingredient = Ingredient(
                            name=ing_data['name'],
                            unit=ing_data['unit'] or 'unit',
                            aisle_id=aisle.id if aisle else None
                        )
                        db.session.add(ingredient)
                        db.session.flush()
                
                # Create recipe ingredient
                recipe_ingredient = RecipeIngredient(
                    recipe_id=recipe.id,
                    ingredient_id=ingredient.id,
                    quantity=str(ing_data['quantity'])
                )
                db.session.add(recipe_ingredient)
            
            db.session.commit()
            flash('Recipe updated successfully!', 'success')
            return redirect(url_for('view_recipe', recipe_id=recipe.id))
            
        except Exception as e:
            db.session.rollback()
            app.logger.error(f'Error updating recipe: {str(e)}', exc_info=True)
            flash(f'An error occurred while updating the recipe: {str(e)}', 'danger')
            
            # Re-render form with current data on error
            return render_template('edit_recipe_v1.html', 
                                recipe=recipe,
                                form_ingredients=ingredients or [{'id': '', 'name': '', 'quantity': '', 'unit': '', 'aisle': ''}],
                                all_ingredients=all_ingredients,
                                distinct_aisles=distinct_aisles,
                                name=name,
                                source_link=source_link,
                                servings=servings,
                                method=method,
                                is_breakfast=is_breakfast,
                                is_lunch=is_lunch,
                                is_dinner=is_dinner)
    
    # For GET request, show the edit form with current recipe data
    # Prepare form data for the template
    form_ingredients = []
    for ri in recipe.recipe_ingredients:
        form_ingredients.append({
            'id': ri.ingredient.id,
            'name': ri.ingredient.name,
            'quantity': ri.quantity,
            'unit': ri.ingredient.unit or '',
            'aisle': ri.ingredient.aisle.name if ri.ingredient.aisle else ''
        })
    
    # If no ingredients, add one empty row
    if not form_ingredients:
        form_ingredients.append({'id': '', 'name': '', 'quantity': '', 'unit': '', 'aisle': ''})
    
    return render_template('edit_recipe_v1.html', 
                         recipe=recipe,
                         form_ingredients=form_ingredients,
                         all_ingredients=all_ingredients,
                         distinct_aisles=distinct_aisles,
                         name=recipe.name,
                         source_link=recipe.source_link or '',
                         servings=recipe.servings,
                         method=recipe.method or '',
                         is_breakfast=recipe.is_breakfast,
                         is_lunch=recipe.is_lunch,
                         is_dinner=recipe.is_dinner)

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

# The add_ingredient_api function is defined earlier in the file (around line 1220)

@app.route('/manage_ingredients', methods=['GET', 'POST'])
@login_required
def manage_ingredients():
    # Initialize ingredients list
    ingredients = []
    
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
            new_ingredients = []
            
            # Handle existing ingredient updates
            for key, value in form_data.items():
                if key.startswith('ingredient_'):
                    # Format is 'ingredient_[id]_[field]'
                    parts = key.split('_')
                    if len(parts) != 3:
                        continue
                        
                    ing_id = int(parts[1])
                    field = parts[2]
                    
                    # Find or create update entry for this ingredient
                    update = next((u for u in updates if u['id'] == ing_id), None)
                    if not update:
                        update = {'id': ing_id}
                        updates.append(update)
                    
                    # Store the field value, ensuring unit is never None
                    if field == 'unit' and (value == '' or value is None):
                        update[field] = 'unit'  # Default value
                    else:
                        update[field] = value if value != '' else None
            
            # Handle new ingredient
            new_name = request.form.get('new_ingredient_name', '').strip()
            new_aisle = request.form.get('new_ingredient_aisle', '').strip() or None
            
            if new_name:
                # Check if ingredient already exists
                existing = Ingredient.query.filter(
                    or_(
                        func.lower(Ingredient.name) == new_name.lower(),
                        func.lower(Ingredient.name) == new_name.lower() + 's',
                        func.lower(Ingredient.name) == new_name.lower()[:-1] if new_name.endswith('s') else None
                    )
                ).first()
                
                if existing:
                    flash(f'Ingredient similar to "{new_name}" already exists as "{existing.name}"', 'warning')
                else:
                    new_ingredients.append({
                        'name': new_name,
                        'aisle': new_aisle
                    })
            
            # Process updates for existing ingredients
            for update in updates:
                ingredient = Ingredient.query.get(update['id'])
                if not ingredient:
                    continue
                    
                # Update name if changed
                if 'name' in update and update['name'] != ingredient.name:
                    # Check if new name already exists
                    existing = Ingredient.query.filter(
                        Ingredient.name.ilike(update['name']),
                        Ingredient.id != ingredient.id
                    ).first()
                    if existing:
                        flash(f'Ingredient "{update['name']}" already exists. Skipping update.', 'warning')
                        continue
                    ingredient.name = update['name']
                
                # Update unit if changed, ensuring it's never None
                if 'unit' in update:
                    new_unit = update['unit'] or 'unit'  # Default to 'unit' if empty or None
                    if new_unit != ingredient.unit:
                        ingredient.unit = new_unit
                
                # Update aisle if changed
                if 'aisle' in update and update['aisle'] != ingredient.aisle_id:
                    # Find or create aisle
                    if update['aisle']:
                        aisle = Aisle.query.filter_by(name=update['aisle']).first()
                        if not aisle:
                            aisle = Aisle(name=update['aisle'])
                            db.session.add(aisle)
                            db.session.flush()
                        ingredient.aisle_id = aisle.id
                    else:
                        ingredient.aisle_id = None
                
                ingredient.updated_at = datetime.utcnow()
                
                # Update related tables (pantry and shopping list)
                if 'name' in update or 'aisle' in update:
                    update_shopping_list_aisles(ingredient.name, update.get('aisle'))
            
            # Add new ingredients
            new_ing_name = request.form.get('new_ingredient_name', '').strip()
            new_ing_unit = request.form.get('new_ingredient_unit', '').strip()
            new_ing_aisle = request.form.get('new_ingredient_aisle', '').strip()
            
            if new_ing_name:
                # Check if ingredient already exists (case insensitive and plural forms)
                existing = Ingredient.query.filter(
                    or_(
                        func.lower(Ingredient.name) == new_ing_name.lower(),
                        func.lower(Ingredient.name) == new_ing_name.lower() + 's',
                        func.lower(Ingredient.name) == new_ing_name.lower()[:-1] if new_ing_name.endswith('s') else None
                    )
                ).first()
                
                if existing:
                    flash(f'Ingredient similar to "{new_ing_name}" already exists as "{existing.name}"', 'warning')
                else:
                    # Create new Aisle if it doesn't exist
                    aisle = Aisle.query.filter_by(name=new_aisle).first()
                    if not aisle:
                        aisle = Aisle(name=new_aisle)
                        db.session.add(aisle)
                        db.session.commit()
                    
                    # Create new ingredient
                    ingredient = Ingredient(
                        name=new_ing_name,
                        unit=ingredient_unit,
                        aisle_id=aisle.id
                    )
                    db.session.add(ingredient)
                    db.session.commit()
                    flash(f'Ingredient "{new_ing_name}" added successfully!', 'success')
            
            # Commit the transaction if we got here
            db.session.commit()
            
        except Exception as e:
            db.session.rollback()
            app.logger.error(f'Error processing ingredient changes: {str(e)}')
            flash(f'Error processing changes: {str(e)}', 'error')
        
        # Get all ingredients with their aisle information
        try:
            ingredients = db.session.query(
                Ingredient.id,
                Ingredient.name,
                Ingredient.unit,
                Aisle.name.label('aisle_name'),
                Aisle.id.label('aisle_id')
            ).outerjoin(
                Aisle, Ingredient.aisle_id == Aisle.id
            ).order_by(
                Ingredient.name
            ).all()
            
            # Convert to list of dicts for template
            ingredients = [{
                'id': i.id,
                'name': i.name, 
                'unit': i.unit,
                'aisle': i.aisle_name,
                'aisle_id': i.aisle_id
            } for i in ingredients]
            
        except Exception as e:
            # Log the error for debugging
            app.logger.error(f'Error loading ingredients: {str(e)}')
            # Initialize empty ingredients list to prevent template errors
            ingredients = []
            # Show error message but still render the page
            flash(f'Error loading ingredients: {str(e)}', 'error')
    
    return render_template(
        'ingredients.html',
        ingredients=ingredients,
        distinct_aisles=distinct_aisles
    )

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
    
    # Get recipes for default meal selection
    breakfast_recipes = Recipe.query.filter_by(is_breakfast=True).all()
    lunch_recipes = Recipe.query.filter_by(is_lunch=True).all()
    dinner_recipes = Recipe.query.filter_by(is_dinner=True).all()
    
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
            app.logger.error(f"Error updating settings: {str(e)}")
            flash('Error updating settings. Please try again.', 'error')
    
    return render_template('settings.html', 
                         settings=settings,
                         breakfast_recipes=breakfast_recipes,
                         lunch_recipes=lunch_recipes,
                         dinner_recipes=dinner_recipes)

@app.route('/generate_meal_plan', methods=['GET', 'POST'])
@login_required
def generate_meal_plan_route():
    flash("Entered Generate_meal_plan_route function","success")
    if request.method == 'POST':
        flash("Entered Generate_meal_plan_route function POST","success")
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
                    available_recipes = [r for r in recipes if r.meal_type == meal_type]
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

    flash("Generating shopping list...",'success')
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
@login_required
def on_join_shopping_list():
    """When a user opens the shopping list page"""
    if not current_user.is_authenticated:
        app.logger.warning(f'[WEBSOCKET] Unauthenticated client {request.sid} attempted to join shopping list')
        return
        
    try:
        account = current_user.accounts.first()
        if not account:
            app.logger.warning(f'[WEBSOCKET] User {current_user.id} has no account')
            return
            
        room = f'shopping_list_{account.id}'
        join_room(room)
        app.logger.debug(f'[WEBSOCKET] Client {request.sid} joined room {room}')
    except Exception as e:
        app.logger.error(f'[WEBSOCKET] Error in on_join_shopping_list: {str(e)}', exc_info=True)

@socketio.on('leave_shopping_list')
@login_required
def on_leave_shopping_list():
    """When a user leaves the shopping list page"""
    if not current_user.is_authenticated:
        return
        
    try:
        account = current_user.accounts.first()
        if not account:
            return
        room = f'shopping_list_{account.id}'
        leave_room(room)
        app.logger.debug(f'[WEBSOCKET] Client {request.sid} left room {room}')
    except Exception as e:
        app.logger.error(f'[WEBSOCKET] Error in on_leave_shopping_list: {str(e)}', exc_info=True)

# --- Custom Commands ---
@app.cli.command('set-admin')
@click.argument('user_id')
def set_admin(user_id):
    """Set a user as admin."""
    user = User.query.get(user_id)
    if not user:
        print(f"User with ID {user_id} not found.")
        return
    user.is_admin = True
    db.session.commit()
    print(f"User {user.email} is now an admin.")

# --- Main Execution ---
if __name__ == '__main__':
    # Create database tables if they don't exist.
    def create_tables():
        with app.app_context():
            db.create_all()
            # Create default admin user if no users exist
            if not User.query.first():
                admin = User(
                    email='admin@example.com',
                    name='Admin',
                    is_admin=True
                )
                admin.set_password('admin123')
                db.session.add(admin)
                db.session.commit()
                print("Created default admin user with email 'admin@example.com' and password 'admin123'")
    
    # Create tables before starting the server
    create_tables()
    
    # Run the Flask development server with Socket.IO support
    # host='0.0.0.0' makes it accessible on your network
    # debug=True enables interactive debugger and auto-reloading (DISABLE IN PRODUCTION)
    print("Starting Flask development server with Socket.IO support...")
    socketio.run(app, host='0.0.0.0', port=5000, debug=True)  # Set debug=False for production!