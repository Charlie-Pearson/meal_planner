import unittest
from flask import url_for
from app import app, db, User, Account, AccountUser, Recipe, LockedMeal
from datetime import datetime, timedelta
import json
import os

class TestAccountManagement(unittest.TestCase):
    def setUp(self):
        app.config['TESTING'] = True
        app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///test.db'
        app.config['WTF_CSRF_ENABLED'] = False
        self.app = app.test_client()
        
        with app.app_context():
            db.create_all()
            
            # Create test user
            self.user = User(
                email='test@example.com',
                name='Test User'
            )
            self.user.set_password('password123')
            db.session.add(self.user)
            
            # Create test account
            self.account = Account(name='Test Account')
            db.session.add(self.account)
            
            # Create account-user relationship
            self.account_user = AccountUser(
                account=self.account,
                user=self.user,
                role='admin'
            )
            db.session.add(self.account_user)
            
            db.session.commit()
            
            # Login the user
            with self.app.session_transaction() as sess:
                sess['user_id'] = self.user.id
                sess['account_id'] = self.account.id

    def tearDown(self):
        with app.app_context():
            db.session.remove()
            db.drop_all()
        # Clean up test database file
        if os.path.exists('test.db'):
            os.remove('test.db')

    def test_account_creation(self):
        with app.app_context():
            # Create new account
            new_account = Account(name='New Account')
            db.session.add(new_account)
            db.session.commit()
            
            # Verify account was created
            self.assertIsNotNone(new_account.id)
            self.assertEqual(new_account.name, 'New Account')
            
            # Refresh session to avoid DetachedInstanceError
            db.session.refresh(new_account)
            
            # Test account-user relationship
            account_user = AccountUser(
                account=new_account,
                user=self.user,
                role='admin'
            )
            db.session.add(account_user)
            db.session.commit()
            
            # Verify relationship
            self.assertEqual(len(new_account.users.all()), 1)
            self.assertEqual(new_account.users.first(), self.user)

    def test_account_user_roles(self):
        with app.app_context():
            # Create another user
            other_user = User(
                email='other@example.com',
                name='Other User'
            )
            other_user.set_password('password123')
            db.session.add(other_user)
            
            # Add user to account with member role
            account_user = AccountUser(
                account=self.account,
                user=other_user,
                role='member'
            )
            db.session.add(account_user)
            db.session.commit()
            
            # Verify roles
            admin_users = self.account.account_users.filter_by(role='admin').all()
            member_users = self.account.account_users.filter_by(role='member').all()
            
            self.assertEqual(len(admin_users), 1)
            self.assertEqual(len(member_users), 1)
            self.assertEqual(admin_users[0].user, self.user)
            self.assertEqual(member_users[0].user, other_user)

    def test_account_deactivation(self):
        with app.app_context():
            # Deactivate account
            self.account.is_active = False
            db.session.commit()
            
            # Refresh session
            db.session.refresh(self.account)
            
            # Verify account is deactivated
            self.assertFalse(self.account.is_active)
            
            # Verify users can't access deactivated account
            with self.app.session_transaction() as sess:
                sess['account_id'] = self.account.id
            
            response = self.app.get('/dashboard')
            self.assertEqual(response.status_code, 302)  # Should redirect

    def test_create_recipe_with_account(self):
        """Test creating a recipe associated with an account"""
        with app.app_context():
            recipe = Recipe(
                name='Test Recipe',
                account_id=self.account.id,
                created_by=self.user.id,
                is_public=False
            )
            db.session.add(recipe)
            db.session.commit()

            # Verify recipe was created with correct account
            saved_recipe = Recipe.query.filter_by(name='Test Recipe').first()
            self.assertIsNotNone(saved_recipe)
            self.assertEqual(saved_recipe.account_id, self.account.id)
            self.assertEqual(saved_recipe.created_by, self.user.id)
            self.assertFalse(saved_recipe.is_public)

    def test_locked_meal_with_account(self):
        """Test creating a locked meal associated with an account"""
        with app.app_context():
            locked_meal = LockedMeal(
                account_id=self.account.id,
                meal_type='dinner',
                day_of_week=1,
                recipe_id=1
            )
            db.session.add(locked_meal)
            db.session.commit()

            # Verify locked meal was created with correct account
            saved_locked_meal = LockedMeal.query.filter_by(account_id=self.account.id).first()
            self.assertIsNotNone(saved_locked_meal)
            self.assertEqual(saved_locked_meal.meal_type, 'dinner')
            self.assertEqual(saved_locked_meal.day_of_week, 1)

    def test_account_data_access(self):
        """Test data access restrictions based on account"""
        with app.app_context():
            # Create another account and recipe
            other_account = Account(name='Other Account')
            db.session.add(other_account)
            db.session.flush()

            # Create recipes for both accounts
            recipe1 = Recipe(
                name='Account 1 Recipe',
                account_id=self.account.id,
                created_by=self.user.id,
                is_public=False
            )
            recipe2 = Recipe(
                name='Account 2 Recipe',
                account_id=other_account.id,
                created_by=self.user.id,
                is_public=False
            )
            db.session.add_all([recipe1, recipe2])
            db.session.commit()

            # Verify recipes are only accessible to correct account
            account1_recipes = Recipe.query.filter_by(account_id=self.account.id).all()
            self.assertEqual(len(account1_recipes), 1)
            self.assertEqual(account1_recipes[0].name, 'Account 1 Recipe')

            account2_recipes = Recipe.query.filter_by(account_id=other_account.id).all()
            self.assertEqual(len(account2_recipes), 1)
            self.assertEqual(account2_recipes[0].name, 'Account 2 Recipe')

    def test_account_user_removal(self):
        """Test removing a user from an account"""
        with app.app_context():
            # Create user to remove
            user_to_remove = User(name='Remove Me', email='remove@example.com')
            user_to_remove.set_password('SecurePass123!')
            db.session.add(user_to_remove)
            db.session.flush()

            # Add user to account
            account_user = AccountUser(
                account_id=self.account.id,
                user_id=user_to_remove.id,
                role='member'
            )
            db.session.add(account_user)
            db.session.commit()

            # Verify user is in account
            self.assertEqual(len(self.account.users), 2)

            # Remove user
            AccountUser.query.filter_by(
                account_id=self.account.id,
                user_id=user_to_remove.id
            ).delete()
            db.session.commit()

            # Verify user is removed
            self.assertEqual(len(self.account.users), 1)

if __name__ == '__main__':
    unittest.main() 