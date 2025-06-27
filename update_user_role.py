from app import app, db
from app.models import User, Account, AccountUser

def update_user_to_admin():
    with app.app_context():
        # Find the user by email
        user = User.query.filter_by(email='charlie12pearson@gmail.com').first()
        if not user:
            print("User not found with email: charlie12pearson@gmail.com")
            return
            
        # Find the account
        account = Account.query.get(2)  # ID 2 is 'charlies' account
        if not account:
            print("Account with ID 2 not found")
            return
            
        # Check if user is already associated with the account
        account_user = AccountUser.query.filter_by(
            account_id=account.id, 
            user_id=user.id
        ).first()
        
        if account_user:
            # Update existing association
            account_user.role = 'admin'
        else:
            # Create new association
            account_user = AccountUser(
                account_id=account.id,
                user_id=user.id,
                role='admin'
            )
            db.session.add(account_user)
        
        # Also set user as admin in the User model
        user.is_admin = True
        
        # Commit changes
        db.session.commit()
        print(f"Successfully set {user.email} as admin for account '{account.name}' (ID: {account.id})")

if __name__ == '__main__':
    update_user_to_admin()
