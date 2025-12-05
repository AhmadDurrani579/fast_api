from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.db.models import UserDB
from app.db.model_family import Family
from app.deps.deps import get_current_user

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