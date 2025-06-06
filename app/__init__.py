import os
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_login import LoginManager
from flask_wtf.csrf import CSRFProtect
from flask_socketio import SocketIO

# Instantiate extensions
csrf = CSRFProtect()
socketio = SocketIO(cors_allowed_origins="*", async_mode='threading')
db = SQLAlchemy()
migrate = Migrate()
login_manager = LoginManager()

ALL_DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
meal_types = ["Breakfast", "Lunch", "Dinner"]


def create_app():
    app = Flask(__name__)
    BASE_DIR = os.path.abspath(os.path.dirname(os.path.dirname(__file__)))
    DATABASE_PATH = os.path.join(BASE_DIR, 'database.db')

    app.secret_key = os.environ.get('FLASK_SECRET_KEY', 'your-secret-key-here')
    app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{DATABASE_PATH}'
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

    # init extensions
    csrf.init_app(app)
    socketio.init_app(app)
    db.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)
    login_manager.login_view = 'auth.login'
    login_manager.login_message = 'Please log in to access this page.'
    login_manager.login_message_category = 'info'

    from .models import User

    @login_manager.user_loader
    def load_user(user_id):
        return db.session.get(User, int(user_id))

    # register blueprints
    from .routes import auth_bp, dashboard_bp, shopping_bp
    app.register_blueprint(auth_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(shopping_bp)

    # websocket handlers
    from . import websocket
    websocket.register_handlers(socketio)

    return app
