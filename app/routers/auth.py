# app/routers/auth.py
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.db.database import get_db
from app.db.models import UserDB
from app.schemas.schemas import UserSignup, UserLogin, UserOut, TokenOut
from app.core.security import hash_password, verify_password, create_access_token
from app.core.config import settings

router = APIRouter(prefix="/auth", tags=["auth"])

@router.post("/signup", response_model=UserOut)
def signup(payload: UserSignup, db: Session = Depends(get_db)):
    if db.query(UserDB).filter(UserDB.email == payload.email).first():
        raise HTTPException(status_code=400, detail="Email already registered")
    user = UserDB(
        full_name=payload.full_name,
        email=payload.email,
        password=hash_password(payload.password),
    )
    db.add(user); db.commit(); db.refresh(user)
    return user

@router.post("/login", response_model=TokenOut)
def login(payload: UserLogin, db: Session = Depends(get_db)):
    user = db.query(UserDB).filter(UserDB.email == payload.email).first()
    if not user or not verify_password(payload.password, user.password):
        raise HTTPException(status_code=400, detail="Invalid email or password")

    token = create_access_token({"sub": str(user.id)})
    return {
        "user": UserOut.model_validate(user),
        "access_token": token,
        "token_type": "bearer",
        "expires_in_minutes": settings.ACCESS_TOKEN_EXPIRE_MINUTES,
    }