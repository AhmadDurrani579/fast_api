from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List

from app.db.database import get_db
from app.db.models import UserDB
from app.db.models_family import Family, FamilyMember
from app.deps.deps import get_current_user

router = APIRouter(prefix="/family", tags=["family"])


# -------------------------------------------------
# 1. Family Setup API (HEAD ONLY)
# -------------------------------------------------
@router.post("/setup")
def family_setup(
    total_balance: float,
    total_income: float,
    members: List[str],
    current_user: UserDB = Depends(get_current_user),
    db: Session = Depends(get_db)
):

    # Only head can create
    if current_user.role != "head":
        raise HTTPException(status_code=403, detail="Only family head can create family")

    # Check if already created
    existing = db.query(Family).filter(Family.head_id == current_user.id).first()
    if existing:
        raise HTTPException(status_code=400, detail="Family already created")

    # Create family record
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

    # -------------------------------------------------
    # AUTO-CREATE FamilyMember rows (allocated_budget = 0, spent = 0)
    # -------------------------------------------------
    for name in members:
        member = FamilyMember(
            family_code=current_user.family_code,
            name=name,
            role="member",
            allocated_budget=0.0,
            spent_amount=0.0
        )
        db.add(member)

    db.commit()

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
def get_family(
    current_user: UserDB = Depends(get_current_user),
    db: Session = Depends(get_db)
):

    fam = (
        db.query(Family)
        .filter(Family.family_code == current_user.family_code)
        .first()
    )

    if not fam:
        raise HTTPException(status_code=404, detail="Family not found")

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


# -------------------------------------------------
# 3. Dashboard Summary (SHOW MEMBERS)
# -------------------------------------------------
@router.get("/summary")
def get_family_summary(
    current_user: UserDB = Depends(get_current_user),
    db: Session = Depends(get_db)
):

    # Find family
    family = (
        db.query(Family)
        .filter(
            (Family.head_id == current_user.id)
            | (Family.family_code == current_user.family_code)
        )
        .first()
    )

    if not family:
        raise HTTPException(status_code=404, detail="Family not found")

    # Fetch all members for this family_code
    members = (
        db.query(FamilyMember)
        .filter(FamilyMember.family_code == family.family_code)
        .all()
    )

    # Build member summary list
    member_data = []
    for m in members:
        member_data.append({
            "name": m.name,
            "allocated": m.allocated_budget,
            "spent": m.spent_amount,
            "remaining": m.allocated_budget - m.spent_amount
        })

    total_expenses = sum(m.spent_amount for m in members)
    remaining_budget = family.total_income - total_expenses

    return {
        "status": True,
        "message": "Dashboard loaded",
        "total_balance": family.total_balance,
        "total_income": family.total_income,
        "total_expenses": total_expenses,
        "remaining_budget": remaining_budget,
        "family_members": member_data
    }


# -------------------------------------------------
# 4. Optional: Add Member Manually
# -------------------------------------------------
@router.post("/add-member")
def add_member(
    name: str,
    allocated_budget: float = 0.0,
    role: str = "member",
    current_user: UserDB = Depends(get_current_user),
    db: Session = Depends(get_db)
):

    # Only head can add members
    if current_user.role != "head":
        raise HTTPException(403, "Only family head can add members")

    family = db.query(Family).filter(Family.head_id == current_user.id).first()
    if not family:
        raise HTTPException(404, "Family not found")

    new_member = FamilyMember(
        family_code=family.family_code,
        name=name,
        role=role,
        allocated_budget=allocated_budget,
        spent_amount=0.0
    )

    db.add(new_member)
    db.commit()
    db.refresh(new_member)

    return {
        "status": True,
        "message": "Family member added",
        "member": {
            "name": new_member.name,
            "allocated_budget": new_member.allocated_budget
        }
    }