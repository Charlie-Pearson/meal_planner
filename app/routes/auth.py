from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_user, logout_user, current_user, login_required
from datetime import datetime
import re

from .. import db
from ..forms import LoginForm
from ..models import User, Account, AccountUser

auth_bp = Blueprint('auth', __name__)

@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard.index'))
    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(email=form.email.data).first()
        if user and user.check_password(form.password.data):
            remember = request.form.get('remember_me') == 'on'
            login_user(user, remember=remember)
            user.last_login = datetime.utcnow()
            db.session.commit()
            return redirect(url_for('dashboard.index'))
        flash('Invalid email or password', 'error')
    return render_template('login.html', form=form)

@auth_bp.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        name = request.form.get('name')
        email = request.form.get('email')
        password = request.form.get('password')
        confirm_password = request.form.get('confirm_password')
        if not re.match(r"[^@]+@[^@]+\.[^@]+", email):
            flash('Invalid email address', 'error')
            return redirect(url_for('auth.register'))
        if password != confirm_password:
            flash('Passwords must match', 'error')
            return redirect(url_for('auth.register'))
        existing_user = User.query.filter_by(email=email).first()
        if existing_user:
            flash('Email already registered', 'error')
            return redirect(url_for('auth.register'))
        try:
            account = Account(name=f"{name}'s Account")
            db.session.add(account)
            db.session.flush()
            user = User(name=name, email=email)
            user.set_password(password)
            db.session.add(user)
            db.session.flush()
            account_user = AccountUser(account_id=account.id, user_id=user.id, role='admin')
            db.session.add(account_user)
            db.session.commit()
            flash('Registration successful! Please login.', 'success')
            return redirect(url_for('auth.login'))
        except Exception:
            db.session.rollback()
            flash('An error occurred during registration. Please try again.', 'error')
            return redirect(url_for('auth.register'))
    return render_template('register.html')

@auth_bp.route('/logout')
@login_required
def logout():
    logout_user()
    flash('You have been logged out.', 'info')
    return redirect(url_for('auth.login'))
