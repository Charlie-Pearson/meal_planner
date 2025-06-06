from datetime import datetime
import bcrypt
from flask_login import UserMixin
from . import db

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(128))
    name = db.Column(db.String(100), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_login = db.Column(db.DateTime)
    is_active = db.Column(db.Boolean, default=True)

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

    account = db.relationship('Account', back_populates='account_users',
                              overlaps="users")
    user = db.relationship('User', back_populates='account_users',
                           overlaps="accounts")

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

    invited_by = db.relationship('User', foreign_keys=[created_by], backref=db.backref('invitations_sent', lazy='dynamic'))

    def __repr__(self):
        return f'<Invitation {self.email} to {self.account_id}>'

class Recipe(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), nullable=False, unique=True)
    source_link = db.Column(db.String(500), nullable=True)
    method = db.Column(db.Text, nullable=True)
    servings = db.Column(db.Integer, nullable=False)
    is_breakfast = db.Column(db.Boolean, default=False, nullable=False)
    is_lunch = db.Column(db.Boolean, default=False, nullable=False)
    is_dinner = db.Column(db.Boolean, default=False, nullable=False)
    ingredients = db.relationship('Ingredient', backref='recipe', lazy=True, cascade="all, delete-orphan")
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
    id = db.Column(db.Integer, primary_key=True)
    day = db.Column(db.String(10), nullable=False)
    meal_type = db.Column(db.String(20), nullable=False)
    recipe_id = db.Column(db.Integer, db.ForeignKey('recipe.id'), nullable=True)
    manual_text = db.Column(db.String(200), nullable=True)
    is_manual = db.Column(db.Boolean, default=False)
    is_default = db.Column(db.Boolean, default=False)
    lock_type = db.Column(db.String(20), default='user')

    __table_args__ = (
        db.UniqueConstraint('day', 'meal_type', name='unique_day_meal'),
    )

    def __repr__(self):
        return f'<LockedMeal {self.day} {self.meal_type}>'

class AccountSettings(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    account_id = db.Column(db.Integer, db.ForeignKey('account.id'), nullable=False)
    num_people = db.Column(db.Integer, default=1)
    meal_plan_start_day = db.Column(db.String(10), default='Monday')
    meal_plan_duration = db.Column(db.Integer, default=7)
    meal_repeat_interval = db.Column(db.Integer, default=0)
    default_breakfast_id = db.Column(db.Integer, db.ForeignKey('recipe.id'))
    default_lunch_id = db.Column(db.Integer, db.ForeignKey('recipe.id'))
    default_dinner_id = db.Column(db.Integer, db.ForeignKey('recipe.id'))

    account = db.relationship('Account', backref=db.backref('settings', uselist=False))
    default_breakfast = db.relationship('Recipe', foreign_keys=[default_breakfast_id])
    default_lunch = db.relationship('Recipe', foreign_keys=[default_lunch_id])
    default_dinner = db.relationship('Recipe', foreign_keys=[default_dinner_id])

class ShoppingListItem(db.Model):
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
