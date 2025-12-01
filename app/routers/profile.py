# app/routers/profile.py
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.models import UserDB
from app.schemas.schemas import EditProfile
from app.deps.deps import get_current_user
from app.db.database import get_db

router = APIRouter(prefix="/profile", tags=["Profile"])


@router.put("/edit")
def edit_profile(
    payload: EditProfile,
    db: Session = Depends(get_db),
    current_user: UserDB = Depends(get_current_user)
):
    current_user.full_name = payload.full_name
    db.commit()
    db.refresh(current_user)

    return {
        "status": True,
        "message": "Profile updated successfully",
        "user": {
            "id": current_user.id,
            "full_name": current_user.full_name,
            "email": current_user.email,
            "role": current_user.role,
            "family_code": current_user.family_code
        }
    }