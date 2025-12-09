from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List

from app.db.database import get_db
from app.db.models import UserDB
from app.db.models_family import Family, FamilyMember, FamilyMonthly
from app.deps.deps import get_current_user
from app.schemas.schemas import FamilySetupRequest, UpdateFamilyMemberRequest
from datetime import datetime
from app.db.models_expenses import ExpenseDB
import calendar

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
    if current_user.role != "head":
        raise HTTPException(403, "Only family head can create family")

    # Prevent duplicate setup
    existing = db.query(Family).filter(Family.head_id == current_user.id).first()
    if existing:
        raise HTTPException(400, "Family already created")

    # 1️⃣ Create Family
    fam = Family(
        family_code=current_user.family_code,
        head_id=current_user.id,
        total_balance=payload.total_balance,
        expected_members=",".join(payload.members)
    )

    db.add(fam)
    db.commit()
    db.refresh(fam)

    # 2️⃣ Insert Family Members
    for name in payload.members:
        db.add(FamilyMember(
            family_code=fam.family_code,
            name=name,
            role="member",
            allocated_budget=0,
            spent_amount=0
        ))
    db.commit()

    # 3️⃣ Create Monthly Budget & Income Record
    monthly = FamilyMonthly(
        family_id=fam.id,
        year=payload.year,
        month=payload.month,
        monthly_income=payload.monthly_income,
        monthly_budget=payload.monthly_budget
    )

    db.add(monthly)
    db.commit()

    return {
        "status": True,
        "message": "Family + Monthly Budget setup completed",
        "family": {
            "family_code": fam.family_code,
            "members": payload.members,
            "monthly_budget": payload.monthly_budget,
            "monthly_income": payload.monthly_income,
            "year": payload.year,
            "month": payload.month
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

    # 1️⃣ Get family
    family = db.query(Family).filter(
        Family.family_code == current_user.family_code
    ).first()

    if not family:
        raise HTTPException(404, "Family not found")

    # 2️⃣ Get latest monthly record
    monthly = (
        db.query(FamilyMonthly)
        .filter(FamilyMonthly.family_id == family.id)
        .order_by(FamilyMonthly.year.desc(), FamilyMonthly.month.desc())
        .first()
    )

    if not monthly:
        raise HTTPException(404, "Monthly budget not set yet")

    # 3️⃣ Load all family members
    members = db.query(FamilyMember).filter(
        FamilyMember.family_code == family.family_code
    ).all()

    # 4️⃣ Build member summary
    member_data = []
    for m in members:
        member_data.append({
            "member_id": m.id,
            "user_id": m.user_id,
            "name": m.name,
            "role": m.role,
            "allocated": m.allocated_budget,
            "spent": m.spent_amount,
            "remaining": m.allocated_budget - m.spent_amount
        })

    # 5️⃣ Calculate family expenses for this month
    year = monthly.year
    month = monthly.month

    # Last day of THAT month
    last_day = calendar.monthrange(year, month)[1]

    start_date = f"{year}-{month:02d}-01"
    end_date = f"{year}-{month:02d}-{last_day:02d}"

    month_expenses = (
        db.query(ExpenseDB)
        .filter(
            ExpenseDB.family_code == family.family_code,
            ExpenseDB.created_at.between(start_date, end_date)
        )
        .all()
    )
    total_expenses = sum(e.amount for e in month_expenses)

    remaining_budget = monthly.monthly_income - total_expenses

    return {
        "status": True,
        "message": "Dashboard loaded",
        "monthly_income": monthly.monthly_income,
        "monthly_budget": monthly.monthly_budget,
        "year": monthly.year,
        "month": monthly.month,
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