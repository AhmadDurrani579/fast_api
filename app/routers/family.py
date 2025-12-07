from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List

from app.db.database import get_db
from app.db.models import UserDB
from app.db.models_family import Family, FamilyMember
from app.deps.deps import get_current_user
from app.schemas.schemas import FamilySetupRequest, UpdateFamilyMemberRequest

router = APIRouter(prefix="/family", tags=["family"])


# -------------------------------------------------
# 1. Family Setup API (HEAD ONLY)
# -------------------------------------------------
@router.post("/setup")
def family_setup(
    payload: FamilySetupRequest,
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

    # Create main family record
    fam = Family(
        family_code=current_user.family_code,
        head_id=current_user.id,
        total_balance=payload.total_balance,
        total_income=payload.total_income,
        monthly_budget=payload.monthly_budget,
        expected_members=",".join(payload.members),
    )
    db.add(fam)
    db.commit()
    db.refresh(fam)

    # ✅ INSERT MEMBERS INTO family_members TABLE
    for name in payload.members:
        member_row = FamilyMember(
            family_code=current_user.family_code,
            name=name,
            role="member",          # or "", doesn’t matter for now
            allocated_budget=0.0,   # starts at 0; you will update later
            spent_amount=0.0,
        )
        db.add(member_row)

    db.commit()

    return {
        "status": True,
        "message": "Family profile created successfully",
        "family": {
            "family_code": fam.family_code,
            "members": payload.members,
            "total_balance": fam.total_balance,
            "total_income": fam.total_income,
        },
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

    # Build member summary list with ID + role
    member_data = []
    for m in members:
        member_data.append({
            "member_id": m.id,      # always exists
            "user_id": m.user_id,   # real user, null if dummy
            "name": m.name,
            "role": m.role,
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
        "monthly_budget": family.monthly_budget,
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

@router.post("/update-member")
def update_member(
    payload: UpdateFamilyMemberRequest,
    current_user: UserDB = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    # Only head can update members
    if current_user.role != "head":
        raise HTTPException(
            status_code=403,
            detail="Only family head can update members"
        )

    # Find family of head
    family = db.query(Family).filter(Family.head_id == current_user.id).first()
    if not family:
        raise HTTPException(status_code=404, detail="Family not found")

    # ============================
    # 1️⃣ Find member (BY ID first)
    # ============================
    member = None

    if payload.member_id is not None:
        member = (
            db.query(FamilyMember)
            .filter(
                FamilyMember.id == payload.member_id,
                FamilyMember.family_code == family.family_code
            )
            .first()
        )

    # ============================
    # 2️⃣ If ID not found → find by NAME
    # ============================
    if member is None and payload.name is not None:
        member = (
            db.query(FamilyMember)
            .filter(
                FamilyMember.name == payload.name,
                FamilyMember.family_code == family.family_code
            )
            .first()
        )

    if not member:
        raise HTTPException(status_code=404, detail="Family member not found")

    # ============================
    # 3️⃣ Apply updates
    # ============================
    if payload.allocated_budget is not None:
        member.allocated_budget = payload.allocated_budget

    if payload.role is not None:
        member.role = payload.role

    db.commit()
    db.refresh(member)

    return {
        "status": True,
        "message": "Family member updated",
        "member": {
            "id": member.id,
            "name": member.name,
            "role": member.role,
            "allocated": member.allocated_budget,
            "spent": member.spent_amount,
            "remaining": member.allocated_budget - member.spent_amount,
        },
    }