from app import db, User, Account, Recipe  # or whatever models you defined

# Check number of users
print(User.query.all())        # Show all users
print(User.query.count())      # How many users?

# Check sample account
account = Account.query.first()
print(account)

# Check recipes
for r in Recipe.query.all():
    print(r.name)
