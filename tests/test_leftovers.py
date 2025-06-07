import os
import sys
from pathlib import Path
import pytest
from flask_login import login_user

os.environ["EVENTLET_NO_GREENDNS"] = "yes"

# Ensure repository root is on the Python path when running via the pytest CLI
ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app import app, db, Recipe, User, Account, generate_meal_plan


@pytest.fixture
def test_app():
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///:memory:"
    app.config["TESTING"] = True
    with app.app_context():
        db.create_all()
        user = User(email="test@example.com", name="Test")
        user.password_hash = "x"
        account = Account(name="TestAccount")
        account.users.append(user)
        recipe_dinner = Recipe(name="Dinner1", servings=6, is_dinner=True)
        recipe_breakfast = Recipe(name="Breakfast1", servings=4, is_breakfast=True)
        db.session.add_all([user, account, recipe_dinner, recipe_breakfast])
        db.session.commit()
        yield user, recipe_dinner
        db.session.remove()
        db.drop_all()


def _generate(user, locked=None, days=None):
    if locked is None:
        locked = {}
    if days is None:
        days = ["Monday", "Tuesday", "Wednesday", "Thursday"]
    with app.test_request_context("/"):
        login_user(user)
        return generate_meal_plan(2, locked, days=days)


def test_first_meal_leftover_label(test_app):
    user, recipe = test_app
    plan = _generate(user)
    assert plan["Tuesday"]["Dinner"]["status"] == "leftover"
    assert plan["Tuesday"]["Dinner"]["manual_text"] == "Leftover from Monday's dinner"


def test_correct_number_of_leftovers(test_app):
    user, recipe = test_app
    plan = _generate(user)
    leftovers = [
        plan[day]["Dinner"]
        for day in ["Tuesday", "Wednesday"]
        if plan[day]["Dinner"]["status"] == "leftover"
    ]
    assert len(leftovers) == 2


def test_skip_locked_slot(test_app):
    user, recipe = test_app
    locked = {
        "Tuesday_Dinner": {
            "recipe_id": recipe.id,
            "manual": False,
            "default": False,
            "lock_type": "user",
        }
    }
    plan = _generate(user, locked=locked)
    assert plan["Tuesday"]["Dinner"]["status"] == "locked"
    assert plan["Wednesday"]["Dinner"]["status"] == "leftover"
    assert plan["Thursday"]["Dinner"]["status"] == "leftover"
