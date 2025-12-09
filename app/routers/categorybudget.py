from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.db.models import UserDB
from app.db.categories_budget import CategoryBudget   # <-- import
from app.deps.deps import get_current_user
from app.schemas.schemas import UpdateCategoryBudgetRequest  # <-- import

router = APIRouter(prefix="/categories", tags=["categories"])


@router.post("/update-budget")
def update_category_budget(
    payload: UpdateCategoryBudgetRequest,
    current_user: UserDB = Depends(get_current_user),
    db: Session = Depends(get_db)
):

    # Only head can update budgets
    if current_user.role != "head":
        raise HTTPException(status_code=403, detail="Only family head can update category budgets")

    family_code = current_user.family_code

    for item in payload.budgets:   # <-- FIXED
        # check if row already exists
        row = db.query(CategoryBudget).filter(
            CategoryBudget.family_code == family_code,
            CategoryBudget.category_name == item.category   # <-- FIXED
        ).first()

        if row:
            # update existing budget
            row.budget = item.budget
        else:
            # create new row
            row = CategoryBudget(
                family_code=family_code,
                category_name=item.category,
                budget=item.budget,
                spent=0
            )
            db.add(row)

    db.commit()

    return {
        "status": True,
        "message": "Category budgets updated successfully"
    }