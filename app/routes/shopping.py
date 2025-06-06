from flask import Blueprint, render_template
from flask_login import login_required

shopping_bp = Blueprint('shopping', __name__)

@shopping_bp.route('/shopping-list')
@login_required
def shopping_list():
    return render_template('shopping_list.html')
