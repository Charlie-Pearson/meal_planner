import unittest
from app import app, db, User, Account, AccountUser
from flask import url_for
import os

class TestAuthentication(unittest.TestCase):
    def setUp(self):
        app.config['TESTING'] = True
        app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///test.db'
        app.config['WTF_CSRF_ENABLED'] = False
        self.app = app.test_client()
        
        with app.app_context():
            db.create_all()
    
    def tearDown(self):
        with app.app_context():
            db.session.remove()
            db.drop_all()
        os.remove('test.db')
    
    def test_registration_valid(self):
        response = self.app.post('/register', data={
            'name': 'Test User',
            'email': 'test@example.com',
            'password': 'password123',
            'confirm_password': 'password123'
        }, follow_redirects=True)
        
        self.assertIn(b'Registration successful', response.data)
        
        with app.app_context():
            user = User.query.filter_by(email='test@example.com').first()
            self.assertIsNotNone(user)
            self.assertEqual(user.name, 'Test User')
            self.assertTrue(user.accounts.count() == 1)
            account_user = AccountUser.query.filter_by(user_id=user.id).first()
            self.assertEqual(account_user.role, 'admin')
    
    def test_registration_invalid_email(self):
        response = self.app.post('/register', data={
            'name': 'Test User',
            'email': 'invalid-email',
            'password': 'password123',
            'confirm_password': 'password123'
        }, follow_redirects=True)
        
        self.assertIn(b'Invalid email address', response.data)
    
    def test_registration_password_mismatch(self):
        response = self.app.post('/register', data={
            'name': 'Test User',
            'email': 'test@example.com',
            'password': 'password123',
            'confirm_password': 'different123'
        }, follow_redirects=True)
        
        self.assertIn(b'Passwords must match', response.data)
    
    def test_login_valid(self):
        # First register a user
        self.app.post('/register', data={
            'name': 'Test User',
            'email': 'test@example.com',
            'password': 'password123',
            'confirm_password': 'password123'
        })
        
        # Then try to login
        response = self.app.post('/login', data={
            'email': 'test@example.com',
            'password': 'password123'
        }, follow_redirects=True)
        
        self.assertIn(b'Welcome back', response.data)
    
    def test_login_invalid(self):
        response = self.app.post('/login', data={
            'email': 'test@example.com',
            'password': 'wrongpassword'
        }, follow_redirects=True)
        
        self.assertIn(b'Invalid email or password', response.data)
    
    def test_account_creation(self):
        response = self.app.post('/register', data={
            'name': 'Test User',
            'email': 'test@example.com',
            'password': 'password123',
            'confirm_password': 'password123'
        }, follow_redirects=True)
        
        with app.app_context():
            user = User.query.filter_by(email='test@example.com').first()
            self.assertIsNotNone(user)
            self.assertTrue(user.accounts.count() == 1)
            account = user.accounts.first()
            self.assertEqual(account.name, "Test User's Account")
            account_user = AccountUser.query.filter_by(user_id=user.id).first()
            self.assertEqual(account_user.role, 'admin')

if __name__ == '__main__':
    unittest.main() 