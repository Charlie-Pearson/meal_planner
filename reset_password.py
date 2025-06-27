from app import app, db, User

def reset_password(email, new_password):
    with app.app_context():
        user = User.query.filter_by(email=email).first()
        if user:
            user.set_password(new_password)
            db.session.commit()
            print(f"Password has been reset for {email}")
            return True
        else:
            print(f"No account found with email: {email}")
            return False

if __name__ == "__main__":
    email = "charlie12pearson@gmail.com"
    new_password = "Ginger21"
    reset_password(email, new_password)
