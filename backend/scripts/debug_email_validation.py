
from pydantic import BaseModel, EmailStr, ValidationError

class UserMain(BaseModel):
    email: EmailStr

try:
    print("Validating 'admin@jaldrishti.local'...")
    u = UserMain(email="admin@jaldrishti.local")
    print(f"Success: {u.email}")
except ValidationError as e:
    print(f"Validation Error: {e}")

try:
    print("Validating 'user@example.com'...")
    u = UserMain(email="user@example.com")
    print(f"Success: {u.email}")
except ValidationError as e:
    print(f"Validation Error: {e}")
