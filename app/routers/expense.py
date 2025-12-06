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
    # Load family
    family = db.query(Family).filter(
        Family.family_code == current_user.family_code
    ).first()

    if not family:
        raise HTTPException(404, "Family not found")

    # --- Validate category ---
    allowed_categories = [c["name"] for c in CATEGORIES]
    if payload.category not in allowed_categories:
        raise HTTPException(400, "Invalid category")

    # --- Validate amount ---
    if payload.amount <= 0:
        raise HTTPException(400, "Amount must be greater than 0")

    member_id = None  # default case = head personal expense

    # --------------------------------------------------------------------
    # CASE 1: MEMBER adding expense (never allowed to choose member_id)
    # --------------------------------------------------------------------
    if current_user.role == "member":
        fm = db.query(FamilyMember).filter(
            FamilyMember.family_code == family.family_code,
            FamilyMember.user_id == current_user.id
        ).first()

        if not fm:
            raise HTTPException(400, "Member record not found")

        member_id = fm.id   # locked to this user only

    # --------------------------------------------------------------------
    # CASE 2: HEAD adding an expense
    # --------------------------------------------------------------------
    elif current_user.role == "head":

        # If head DID NOT send member_id → head’s own expense
        if payload.member_id is None:
            member_id = None

        else:
            # Validate chosen member belongs to family
            chosen = db.query(FamilyMember).filter(
                FamilyMember.id == payload.member_id,
                FamilyMember.family_code == family.family_code
            ).first()

            if not chosen:
                raise HTTPException(404, "Member not found in this family")

            member_id = chosen.id

    # --------------------------------------------------------------------
    # CREATE EXPENSE
    # --------------------------------------------------------------------
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


@router.get("/list")
def list_expenses(
    current_user: UserDB = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    # Get family via current user
    family = db.query(Family).filter(
        Family.family_code == current_user.family_code
    ).first()

    if not family:
        raise HTTPException(404, "Family not found")

    # If member → show only their expenses
    if current_user.role == "member":
        member = db.query(FamilyMember).filter(
            FamilyMember.user_id == current_user.id,
            FamilyMember.family_code == family.family_code
        ).first()

        if not member:
            raise HTTPException(400, "Member record not found")

        expenses = db.query(ExpenseDB).filter(
            ExpenseDB.member_id == member.id
        ).all()

    # If head → show all expenses
    else:
        expenses = db.query(ExpenseDB).filter(
            ExpenseDB.family_code == family.family_code
        ).all()

    # Convert results
    response_list = []
    for exp in expenses:
        # Find member name (if exists)
        member_name = None
        if exp.member_id:
            mem = db.query(FamilyMember).filter(
                FamilyMember.id == exp.member_id
            ).first()
            if mem:
                member_name = mem.name

        response_list.append({
            "id": exp.id,
            "name": exp.name,
            "category": exp.category,
            "amount": exp.amount,
            "member_id": exp.member_id,
            "member_name": member_name,
            "created_at": exp.created_at,
        })

    return {
        "status": True,
        "message": "Expenses loaded",
        "expenses": response_list
    }