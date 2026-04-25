from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.schemas.schemas import UserOut
from app.db.models import UserDB, UserUsage
from app.deps.deps import get_current_user
from app.db.database import get_db
from app.schemas.schemas import SubscriptionOut
router = APIRouter(prefix="/users", tags=["users"])


@router.get("/me")
def me(
    current_user: UserDB = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    usage = db.query(UserUsage).filter(
        UserUsage.user_id == current_user.id
    ).first()

    # 🔹 Default values
    is_paid = False
    plan = "free"

    if usage:
        is_paid = bool(usage.is_paid)
        plan = usage.plan_type or "free"

    user_data = UserOut.from_orm(current_user)

    user_data.subscription = SubscriptionOut(
        is_paid=is_paid,
        plan_type=plan
    )    

    return {
        "status": True,
        "message": "User profile fetched successfully",
        "user": user_data
    }