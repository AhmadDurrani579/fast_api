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
    monthly_budget: float
    total_expenses: float
    remaining_budget: float
    family_members: list[FamilySummaryMember]
    needs_monthly_setup: bool

class FamilySetupRequest(BaseModel):
    starting_balance: float      # 🔑 renamed from opening_balance
    monthly_income: float
    monthly_budget: float
    year: int
    month: int                   # 1–12
    members: List[str]

class UpdateFamilyMemberRequest(BaseModel):
    member_id: Optional[int] = None
    name: Optional[str] = None     # used only when member_id is missing
    allocated_budget: Optional[float] = None
    role: Optional[str] = None

class AddExpenseRequest(BaseModel):
    name: str
    category: str
    amount: float
    member_id: int | None = None   # optional

    month: int 
    year: int   

class SingleCategoryBudget(BaseModel):
    category: str
    budget: float

class UpdateCategoryBudgetRequest(BaseModel):
    month: int    
    year: int      
    budgets: List[SingleCategoryBudget] 

class MonthlySetupRequest(BaseModel):
    year: int
    month: int
    opening_balance: float   # ✅ REQUIRED
    monthly_income: float
    monthly_budget: float


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


class VerifyPaymentRequest(BaseModel):
    payment_id: str