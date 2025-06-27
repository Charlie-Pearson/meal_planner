from app import app, db, User, Account, AccountUser, Recipe

def update_user_and_recipes():
    with app.app_context():
        try:
            # Start a transaction
            db.session.begin()
            
            # 1. Verify account and user exist
            account = Account.query.get(2)
            user = User.query.get(2)
            
            if not account or not user:
                print("Error: Could not find account or user")
                return
                
            print(f"Found account: {account.name} (ID: {account.id})")
            print(f"Found user: {user.email} (ID: {user.id})")
            
            # 2. Ensure user is part of account 2
            account_user = AccountUser.query.filter_by(account_id=2, user_id=2).first()
            if not account_user:
                print("Adding user to account...")
                account_user = AccountUser(account_id=2, user_id=2, role='owner')
                db.session.add(account_user)
            
            # 3. Update all recipes to belong to account 2 and created by user 2
            updated = Recipe.query.update({
                Recipe.account_id: 2,
                Recipe.created_by: 2
            })
            
            # Commit the transaction
            db.session.commit()
            print(f"Successfully updated {updated} recipes to account_id=2 and created_by=2")
            
            # Verify the changes
            recipes = Recipe.query.all()
            print("\nUpdated recipes:")
            for r in recipes:
                print(f"- {r.name}: account_id={r.account_id}, created_by={r.created_by}")
                
        except Exception as e:
            db.session.rollback()
            print(f"An error occurred: {str(e)}")
            raise

if __name__ == "__main__":
    update_user_and_recipes()
