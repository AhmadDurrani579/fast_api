from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.db.models import UserDB
from app.db.categories_budget import CategoryBudget   # <-- import
from app.deps.deps import get_current_user
from app.schemas.schemas import UpdateCategoryBudgetRequest  # <-- import
from app.db.models_family import Family, FamilyMember

router = APIRouter(prefix="/categories", tags=["categories"])


@router.post("/update-budget")
def update_category_budget(
    payload: UpdateCategoryBudgetRequest,
    current_user: UserDB = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    family_code = current_user.family_code

    # ---------------- DETERMINE SCOPE ----------------
    if current_user.role == "head":
        scope = "family"
        owner_id = None

    elif current_user.role == "member":
        fm = db.query(FamilyMember).filter(
            FamilyMember.family_code == family_code,
            FamilyMember.user_id == current_user.id
        ).first()

        if not fm:
            raise HTTPException(400, "Member record not found")

        scope = "member"
        owner_id = fm.id

    else:
        raise HTTPException(403, "Invalid role")

    # ---------------- UPDATE BUDGETS ----------------
    for item in payload.budgets:
        row = db.query(CategoryBudget).filter(
            CategoryBudget.family_code == family_code,
            CategoryBudget.category_name == item.category,
            CategoryBudget.scope == scope,
            CategoryBudget.owner_id == owner_id
        ).first()

        if row:
            row.budget = item.budget
        else:
            row = CategoryBudget(
                family_code=family_code,
                category_name=item.category,
                scope=scope,
                owner_id=owner_id,
                budget=item.budget,
                spent=0
            )
            db.add(row)

    db.commit()

    return {
        "status": True,
        "message": "Category budgets updated successfully",
        "scope": scope
    }