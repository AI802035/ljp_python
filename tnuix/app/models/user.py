from pydantic import BaseModel
from typing import Optional

class User(BaseModel):
    username: str
    password_hash: str
    full_name: str

class UserSession(BaseModel):
    username: str
    created_at: float
    expires_at: float

class UserInDB(User):
    disabled: Optional[bool] = False 