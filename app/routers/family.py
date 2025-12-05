from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.db.models import UserDB
from app.db.models_family import Family, FamilyMember
from app.deps.deps import get_current_user
from app.schemas.schemas import FamilySummaryMember, FamilySummary
router = APIRouter(prefix="/family", tags=["family"])

# -------------------------------------------------
# 1. Family Setup API (HEAD ONLY)
# -------------------------------------------------
@router.post("/setup")
def family_setup(total_balance: float,
                 total_income: float,
                 members: list[str],
                 current_user: UserDB = Depends(get_current_user),
                 db: Session = Depends(get_db)):

    # Only head can create
    if current_user.role != "head":
        raise HTTPException(403, "Only family head can create family")

    # Check if already created
    existing = db.query(Family).filter(Family.head_id == current_user.id).first()
    if existing:
        raise HTTPException(400, "Family already created")

    fam = Family(
        family_code=current_user.family_code,
        head_id=current_user.id,
        total_balance=total_balance,
        total_income=total_income,
        expected_members=",".join(members)
    )

    db.add(fam)
    db.commit()
    db.refresh(fam)

    return {
        "status": True,
        "message": "Family profile created successfully",
        "family": {
            "family_code": fam.family_code,
            "members": members,
            "total_balance": fam.total_balance,
            "total_income": fam.total_income
        }
    }

# -------------------------------------------------
# 2. Get Family Info
# -------------------------------------------------
@router.get("/info")
def get_family(current_user: UserDB = Depends(get_current_user),
               db: Session = Depends(get_db)):

    fam = db.query(Family).filter(Family.family_code == current_user.family_code).first()

    if not fam:
        raise HTTPException(404, "Family not found")

    return {
        "status": True,
        "message": "Family info loaded",
        "family": {
            "family_code": fam.family_code,
            "head_id": fam.head_id,
            "total_balance": fam.total_balance,
            "total_income": fam.total_income,
            "expected_members": fam.expected_members.split(",") if fam.expected_members else []
        }
    }

@router.get("/summary")
def get_family_summary(current_user: UserDB = Depends(get_current_user),
                       db: Session = Depends(get_db)):
    
    # Get the family record
    family = db.query(Family).filter(
        (Family.head_id == current_user.id) |
        (Family.family_code == current_user.family_code)
    ).first()

    if not family:
        raise HTTPException(404, "Family not found")

    # Get members
    members = db.query(FamilyMember).filter(
        FamilyMember.family_code == family.family_code
    ).all()

    # Calculate totals
    total_expenses = sum(m.spent_amount for m in members)
    remaining_budget = family.total_income - total_expenses

    family_data = []
    for m in members:
        family_data.append({
            "name": m.name,
            "role": m.role,
            "allocated": m.allocated_budget,
            "spent": m.spent_amount,
            "remaining": m.allocated_budget - m.spent_amount
        })

    return {
        "status": True,
        "message": "Dashboard loaded",
        "total_balance": family.total_balance,
        "total_income": family.total_income,
        "total_expenses": total_expenses,
        "remaining_budget": remaining_budget,
        "family_members": family_data
    }