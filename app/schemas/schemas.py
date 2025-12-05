from pydantic import BaseModel, EmailStr, ConfigDict
from datetime import datetime
from typing import Optional, List
from enum import Enum

# ------------------------
# Signup Schemas
# ------------------------

class SignupHead(BaseModel):
    full_name: str
    email: EmailStr
    password: str


class SignupMember(BaseModel):
    full_name: str
    email: EmailStr
    password: str
    family_code: str


# ------------------------
# Login Schema
# ------------------------

class LoginSchema(BaseModel):
    email: EmailStr
    password: str

class SendCodeRequest(BaseModel):
    email: EmailStr


class VerifyOTPRequest(BaseModel):
    email: EmailStr
    otp: str

class ResetPasswordRequest(BaseModel):
    email: EmailStr
    new_password: str


class FamilySummaryMember(BaseModel):
    name: str
    role: str
    allocated_budget: float
    spent_amount: float
    remaining: float

class FamilySummary(BaseModel):
    total_balance: float
    total_income: float
    total_expenses: float
    remaining_budget: float
    family_members: list[FamilySummaryMember]

    
# ------------------------
# Token Output Schema
# ------------------------

# class TokenOut(BaseModel):
#     access_token: str
#     token_type: str = "bearer"
#     user_id: int
#     expires_in_minutes: int


# ------------------------
# User Output Schema
# ------------------------

class UserOut(BaseModel):
    id: int
    full_name: str
    email: EmailStr
    family_code: Optional[str] = None
    role: str

    class Config:
        from_attributes = True


class EditProfile(BaseModel):
    full_name: str

# # users
# class UserSignup(BaseModel):
#     full_name: str
#     email: EmailStr
#     password: str

# class UserLogin(BaseModel):
#     email: EmailStr
#     password: str

# class UserOut(BaseModel):
#     id: int
#     full_name: str
#     email: EmailStr
#     model_config = ConfigDict(from_attributes=True)

# class TokenOut(BaseModel):
#     user: UserOut
#     access_token: str
#     token_type: str = "bearer"
#     expires_in_minutes: int


# class UserLite(BaseModel):
#     id: int
#     full_name: str
#     email: EmailStr

#     class Config:
#         from_attributes = True


# class LoginResponse(BaseModel):
#     user: UserLite
#     access_token: str
#     token_type: str = "bearer"
#     expires_in_minutes: int


# # posts & comments
# class CommentCreate(BaseModel):
#     content: str
#     post_id: int

# class CommentOut(BaseModel):
#     id: int
#     content: str
#     user_id: int
#     post_id: int
#     created_at: datetime
#     user: UserLite
#     model_config = ConfigDict(from_attributes=True)

# class PostWithComments(BaseModel):
#     id: int
#     user_id: int
#     content: Optional[str] = None
#     image_url: Optional[str] = None
#     created_at: datetime
#     user: UserLite
#     comments: List[CommentOut] = []
#     like_count: int = 0
#     is_liked_by_user: bool | None = None
#     model_config = ConfigDict(from_attributes=True)

# # likes
# class LikeRequest(BaseModel):
#     user_id: int