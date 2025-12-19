from fastapi import APIRouter
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.db.models import UserDB
from app.db.models_family import Family, FamilyMember
from app.db.models_expenses import ExpenseDB
from app.deps.deps import get_current_user
from app.schemas.schemas import AddExpenseRequest
from app.db.categories_budget import CategoryBudget
# from app.constants import CATEGORIES 

router = APIRouter(prefix="/expense", tags=["expense"])

HEAD_CATEGORIES = [
    {"name": "Groceries", "icon": "🛒", "budget": 0, "spent": 0, "remaining": 0},
    {"name": "Food", "icon": "🍽", "budget": 0, "spent": 0, "remaining": 0},
    {"name": "Transport", "icon": "🚌", "budget": 0, "spent": 0, "remaining": 0},
    {"name": "Health", "icon": "💊", "budget": 0, "spent": 0, "remaining": 0},
    {"name": "Gifts", "icon": "🎁", "budget": 0, "spent": 0, "remaining": 0},
    {"name": "Rent", "icon": "🏠", "budget": 0, "spent": 0, "remaining": 0},
    {"name": "Utilities", "icon": "⚡", "budget": 0, "spent": 0, "remaining": 0},
    {"name": "Entertainment", "icon": "🎉", "budget": 0, "spent": 0, "remaining": 0},
    {"name": "Education", "icon": "📚", "budget": 0, "spent": 0, "remaining": 0},
    {"name": "Insurance", "icon": "🛡", "budget": 0, "spent": 0, "remaining": 0},
]

MEMBER_CATEGORIES = [
    {"name": "Food", "icon": "🍽", "budget": 0, "spent": 0, "remaining": 0},
    {"name": "Transport", "icon": "🚌", "budget": 0, "spent": 0, "remaining": 0},
    {"name": "Entertainment", "icon": "🎉", "budget": 0, "spent": 0, "remaining": 0},
    {"name": "Education", "icon": "📚", "budget": 0, "spent": 0, "remaining": 0},
    {"name": "Gifts", "icon": "🎁", "budget": 0, "spent": 0, "remaining": 0},
    {"name": "Rent", "icon": "🏠", "budget": 0, "spent": 0, "remaining": 0},

]


@router.get("/categories")
def get_categories(
    current_user: UserDB = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    family_code = current_user.family_code

    # ---------------- ROLE CHECK ----------------
    if current_user.role == "member":
        fm = db.query(FamilyMember).filter(
            FamilyMember.family_code == family_code,
            FamilyMember.user_id == current_user.id
        ).first()

        if not fm:
            raise HTTPException(400, "Member record not found")

        scope = "member"
        owner_id = fm.id
        base_categories = MEMBER_CATEGORIES

    else:  # head
        scope = "family"
        owner_id = None
        base_categories = HEAD_CATEGORIES

    # ---------------- FETCH BUDGETS ----------------
    rows = db.query(CategoryBudget).filter(
        CategoryBudget.family_code == family_code,
        CategoryBudget.scope == scope,
        CategoryBudget.owner_id == owner_id
    ).all()

    # Safe lookup
    db_map = {row.category_name: row for row in rows}

    # ---------------- BUILD RESPONSE ----------------
    result = []

    for cat in base_categories:
        name = cat["name"]
        icon = cat["icon"]

        row = db_map.get(name)
        budget = row.budget if row else 0
        spent = row.spent if row else 0

        result.append({
            "name": name,
            "icon": icon,
            "budget": budget,
            "spent": spent,
            "remaining": max(budget - spent, 0),
        })

    return {
        "status": True,
        "role": current_user.role,
        "categories": result
    }

@router.post("/add")
def add_expense(
    payload: AddExpenseRequest,
    current_user: UserDB = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    # ---------------- FAMILY ----------------
    family = db.query(Family).filter(
        Family.family_code == current_user.family_code
    ).first()

    if not family:
        raise HTTPException(404, "Family not found")

    # ---------------- VALIDATION ----------------
    if current_user.role == "member":
        allowed_categories = [c["name"] for c in MEMBER_CATEGORIES]
    else:
        allowed_categories = [c["name"] for c in HEAD_CATEGORIES]
    
    if payload.category not in allowed_categories:
        raise HTTPException(400, "Invalid category")

    if payload.amount <= 0:
        raise HTTPException(400, "Amount must be greater than 0")

    member_id = None
    scope = "family"
    owner_id = None

    # ---------------- MEMBER ----------------
    if current_user.role == "member":
        fm = db.query(FamilyMember).filter(
            FamilyMember.family_code == family.family_code,
            FamilyMember.user_id == current_user.id
        ).first()

        if not fm:
            raise HTTPException(400, "Member record not found")

        member_id = fm.id
        scope = "member"
        owner_id = fm.id

    # ---------------- HEAD ----------------
    elif current_user.role == "head":
        if payload.member_id:
            chosen = db.query(FamilyMember).filter(
                FamilyMember.id == payload.member_id,
                FamilyMember.family_code == family.family_code
            ).first()

            if not chosen:
                raise HTTPException(404, "Member not found in this family")

            member_id = chosen.id
        # scope stays "family"

    # ---------------- CREATE EXPENSE ----------------
    exp = ExpenseDB(
        family_code=family.family_code,
        member_id=member_id,
        name=payload.name,
        category=payload.category,
        amount=payload.amount
    )

    db.add(exp)

    # ---------------- UPDATE CATEGORY BUDGET ----------------
    row = db.query(CategoryBudget).filter(
        CategoryBudget.family_code == family.family_code,
        CategoryBudget.category_name == payload.category,
        CategoryBudget.scope == scope,
        CategoryBudget.owner_id == owner_id
    ).first()

    if not row:
        row = CategoryBudget(
            family_code=family.family_code,
            category_name=payload.category,
            scope=scope,
            owner_id=owner_id,
            budget=0,
            spent=payload.amount
        )
        db.add(row)
    else:
        row.spent += payload.amount

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