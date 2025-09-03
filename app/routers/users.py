from fastapi import APIRouter, Depends
from app.schemas.schemas import UserOut
from app.db.models import UserDB
from app.deps.deps import get_current_user

router = APIRouter(prefix="/users", tags=["users"])

@router.get("/me", response_model=UserOut)
def me(current_user: UserDB = Depends(get_current_user)):
    return current_user