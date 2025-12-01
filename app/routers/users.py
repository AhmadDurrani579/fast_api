from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.schemas.schemas import UserOut
from app.db.models import UserDB
from app.deps.deps import get_current_user

router = APIRouter(prefix="/users", tags=["users"])

@router.get("/me")
def me(current_user: UserDB = Depends(get_current_user)):
    return {
        "status": True,
        "message": "User profile fetched successfully",
        "user": UserOut.from_orm(current_user)
    }