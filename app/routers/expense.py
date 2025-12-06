from fastapi import APIRouter
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.db.models import UserDB
from app.db.models_family import Family, FamilyMember
from app.db.models_expenses import ExpenseDB
from app.deps.deps import get_current_user
from app.schemas.schemas import AddExpenseRequest


router = APIRouter(prefix="/expense", tags=["expense"])

CATEGORIES = [
    {"name": "Groceries", "icon": "🛒"},
    {"name": "Food", "icon": "🍽"},
    {"name": "Transport", "icon": "🚌"},
    {"name": "Health", "icon": "💊"},
    {"name": "Gifts", "icon": "🎁"},
    {"name": "Rent", "icon": "🏠"},
    {"name": "Utilities", "icon": "⚡"},
    {"name": "Entertainment", "icon": "🎉"},
    {"name": "Education", "icon": "📚"},
    {"name": "Insurance", "icon": "🛡"},
]

@router.get("/categories")
def get_categories():
    return {"status": True, "categories": CATEGORIES}


@router.post("/add")
def add_expense(
    payload: AddExpenseRequest,
    current_user: UserDB = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    # Get family via user
    family = db.query(Family).filter(
        Family.family_code == current_user.family_code
    ).first()

    if not family:
        raise HTTPException(404, "Family not found")

    # --- CATEGORY VALIDATION ---
    allowed_categories = [c["name"] for c in CATEGORIES]
    if payload.category not in allowed_categories:
        raise HTTPException(400, "Invalid category")

    # --- AMOUNT VALIDATION ---
    if payload.amount <= 0:
        raise HTTPException(400, "Amount must be greater than 0")

    member_id = None

    # -----------------------------
    # CASE 1: MEMBER ADDING EXPENSE
    # -----------------------------
    if current_user.role == "member":
        fm = db.query(FamilyMember).filter(
            FamilyMember.family_code == family.family_code,
            FamilyMember.user_id == current_user.id
        ).first()

        if not fm:
            raise HTTPException(400, "Member record not found")

        member_id = fm.id  # Member can ONLY add for themselves

    # -----------------------------
    # CASE 2: HEAD ASSIGNING EXPENSE
    # -----------------------------
    if current_user.role == "head" and payload.member_id is not None:

        member_exists = db.query(FamilyMember).filter(
            FamilyMember.id == payload.member_id,
            FamilyMember.family_code == family.family_code
        ).first()

        if not member_exists:
            raise HTTPException(404, "Member not found in this family")

        member_id = payload.member_id

    # -----------------------------
    # CREATE EXPENSE
    # -----------------------------
    exp = ExpenseDB(
        family_code=family.family_code,
        member_id=member_id,
        name=payload.name,
        category=payload.category,
        amount=payload.amount
    )

    db.add(exp)
    db.commit()
    db.refresh(exp)

    return {
        "status": True,
        "message": "Expense added successfully",
        "expense": {
            "id": exp.id,
            "name": exp.name,
            "category": exp.category,
            "amount": exp.amount,
            "member_id": exp.member_id
        }
    }