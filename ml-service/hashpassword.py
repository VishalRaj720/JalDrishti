import bcrypt

# Step 1: Encode the password into bytes
password = b"analyst123"

# Step 2: Generate a salt
salt = bcrypt.gensalt()

# Step 3: Hash the password with the salt
hashed_password = bcrypt.hashpw(password, salt)

print("Salt:", salt)
print("Hashed password:", hashed_password)