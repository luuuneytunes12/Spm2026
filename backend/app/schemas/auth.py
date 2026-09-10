from pydantic import BaseModel, EmailStr, Field

# Import for its side effect: widens EmailStr's accepted domains.
import app.schemas.types  # noqa: F401


class RegisterRequest(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    email: EmailStr
    password: str = Field(min_length=8, max_length=72)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
