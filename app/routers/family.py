from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List

from app.db.database import get_db
from app.db.models import UserDB
from app.db.models_family import Family, FamilyMember, FamilyMonthly
from app.deps.deps import get_current_user
from app.schemas.schemas import FamilySetupRequest, UpdateFamilyMemberRequest, MonthlySetupRequest
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

    # ❗ Prevent duplicate family creation
    existing = db.query(Family).filter(
        Family.head_id == current_user.id
    ).first()

    if existing:
        raise HTTPException(400, "Family already created")

    # ---------------- 1️⃣ CREATE FAMILY (ONE TIME) ----------------
    family = Family(
        family_code=current_user.family_code,
        head_id=current_user.id,
        total_balance=payload.starting_balance,
        expected_members=",".join(payload.members)
    )

    db.add(family)
    db.commit()
    db.refresh(family)

    # ---------------- 2️⃣ CREATE FAMILY MEMBERS ----------------
    for name in payload.members:
        db.add(
            FamilyMember(
                family_code=family.family_code,
                name=name.strip(),
                role="member",
                allocated_budget=0,
                spent_amount=0
            )
        )
    db.commit()

    # ---------------- 3️⃣ CREATE FIRST MONTHLY RECORD ----------------
    closing_balance = payload.starting_balance + payload.monthly_income

    monthly = FamilyMonthly(
        family_id=family.id,
        year=payload.year,
        month=payload.month,
        starting_balance=payload.starting_balance,
        monthly_income=payload.monthly_income,
        monthly_budget=payload.monthly_budget,
        closing_balance=closing_balance
    )

    db.add(monthly)
    db.commit()

    return {
        "status": True,
        "message": "Family setup completed successfully",
        "family": {
            "family_code": family.family_code,
            "members": payload.members
        },
        "monthly": {
            "year": payload.year,
            "month": payload.month,
            "starting_balance": payload.starting_balance,
            "monthly_income": payload.monthly_income,
            "monthly_budget": payload.monthly_budget,
            "closing_balance": closing_balance
        }
    }


@router.post("/monthly-setup")
def monthly_setup(
    payload: MonthlySetupRequest,
    current_user: UserDB = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    if current_user.role != "head":
        raise HTTPException(403, "Only family head can update monthly setup")

    family = db.query(Family).filter(
        Family.head_id == current_user.id
    ).first()

    if not family:
        raise HTTPException(404, "Family not found")

    # Prevent duplicate month
    existing_month = db.query(FamilyMonthly).filter(
        FamilyMonthly.family_id == family.id,
        FamilyMonthly.year == payload.year,
        FamilyMonthly.month == payload.month
    ).first()

    if existing_month:
        raise HTTPException(400, "Monthly setup already exists")

    # Create new monthly record
    monthly = FamilyMonthly(
        family_id=family.id,
        year=payload.year,
        month=payload.month,
        monthly_income=payload.monthly_income,
        monthly_budget=payload.monthly_budget
    )

    db.add(monthly)

    # Reset member spent
    db.query(FamilyMember).filter(
        FamilyMember.family_code == family.family_code
    ).update({"spent_amount": 0})

    db.commit()

    return {
        "status": True,
        "message": "Monthly setup completed",
        "year": payload.year,
        "month": payload.month
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
    family = db.query(Family).filter(
        Family.family_code == current_user.family_code
    ).first()

    if not family:
        raise HTTPException(404, "Family not found")

    now = datetime.utcnow()
    current_year = now.year
    current_month = now.month

    # 🔍 Check if current month setup exists
    current_monthly = db.query(FamilyMonthly).filter(
        FamilyMonthly.family_id == family.id,
        FamilyMonthly.year == current_year,
        FamilyMonthly.month == current_month
    ).first()

    needs_monthly_setup = current_monthly is None

    # If exists → use it, else fallback to latest (read-only)
    monthly = (
        current_monthly or
        db.query(FamilyMonthly)
        .filter(FamilyMonthly.family_id == family.id)
        .order_by(FamilyMonthly.year.desc(), FamilyMonthly.month.desc())
        .first()
    )

    if not monthly:
        raise HTTPException(404, "Monthly budget not set yet")

    members = db.query(FamilyMember).filter(
        FamilyMember.family_code == family.family_code
    ).all()

    member_data = [{
        "member_id": m.id,
        "user_id": m.user_id,
        "name": m.name,
        "role": m.role,
        "allocated": m.allocated_budget,
        "spent": m.spent_amount,
        "remaining": m.allocated_budget - m.spent_amount
    } for m in members]

    last_day = calendar.monthrange(monthly.year, monthly.month)[1]
    start_date = f"{monthly.year}-{monthly.month:02d}-01"
    end_date = f"{monthly.year}-{monthly.month:02d}-{last_day:02d}"

    month_expenses = db.query(ExpenseDB).filter(
        ExpenseDB.family_code == family.family_code,
        ExpenseDB.created_at.between(start_date, end_date)
    ).all()

    total_expenses = sum(e.amount for e in month_expenses)
    remaining_budget = monthly.monthly_budget - total_expenses

    return {
        "status": True,
        "message": "Dashboard loaded",
        "monthly_income": monthly.monthly_income,
        "monthly_budget": monthly.monthly_budget,
        "year": monthly.year,
        "month": monthly.month,
        "total_expenses": total_expenses,
        "remaining_budget": remaining_budget,
        "family_members": member_data,

        # ✅ NEW FLAG
        "needs_monthly_setup": needs_monthly_setup
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


@router.get("/member/{member_id}")
def get_member_details(
    member_id: int,
    current_user: UserDB = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    # --- Load member ---
    member = db.query(FamilyMember).filter(
        FamilyMember.id == member_id,
        FamilyMember.family_code == current_user.family_code
    ).first()

    if not member:
        raise HTTPException(404, "Member not found")

    # --- Load expenses ---
    expenses = db.query(ExpenseDB).filter(
        ExpenseDB.member_id == member_id
    ).order_by(ExpenseDB.created_at.desc()).all()

    total_spent = sum(e.amount for e in expenses)
    allocated = member.allocated_budget or 0

    return {
        "status": True,
        "member": {
            "member_id": member.id,
            "name": member.name,
            "role": member.role,
            "allocated_budget": allocated,
            "total_spent": total_spent,
            "remaining": max(allocated - total_spent, 0),
        },
        "expenses": [
            {
                "id": e.id,
                "name": e.name,
                "category": e.category,
                "amount": e.amount,
                "date": e.created_at
            }
            for e in expenses
        ]
    }