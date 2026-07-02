from pydantic import BaseModel, EmailStr


class RegisterIn(BaseModel):
    email: EmailStr
    password: str


class LoginIn(BaseModel):
    email: EmailStr
    password: str


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user_id: str
    calibration_done: bool = False


class SSOExchangeIn(BaseModel):
    token: str


class ClerkExchangeIn(BaseModel):
    clerk_token: str
