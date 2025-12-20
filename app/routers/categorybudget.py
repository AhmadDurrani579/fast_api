from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.db.models import UserDB
from app.db.categories_budget import CategoryBudget   # <-- import
from app.deps.deps import get_current_user
from app.schemas.schemas import UpdateCategoryBudgetRequest  # <-- import
from app.db.models_family import Family, FamilyMember
from app.utils.member_utils import get_or_assign_member
from app.constants.categories import HEAD_CATEGORIES, MEMBER_CATEGORIES
router = APIRouter(prefix="/categories", tags=["categories"])


@router.post("/update-budget")
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
        allowed_categories = [c["name"] for c in HEAD_CATEGORIES]

    elif current_user.role == "member":
        # 🔥 auto-link or fetch member slot
        fm = get_or_assign_member(
            db=db,
            family_code=family_code,
            user_id=current_user.id
        )

        scope = "member"
        owner_id = fm.id
        allowed_categories = [c["name"] for c in MEMBER_CATEGORIES]

    else:
        raise HTTPException(403, "Invalid role")

    # ---------------- UPDATE BUDGETS ----------------
    for item in payload.budgets:

        # 🔒 category-level security
        if item.category not in allowed_categories:
            raise HTTPException(
                status_code=400,
                detail=f"Category '{item.category}' not allowed for this role"
            )

        if item.budget < 0:
            raise HTTPException(
                status_code=400,
                detail="Budget must be >= 0"
            )

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