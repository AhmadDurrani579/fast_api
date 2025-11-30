# app/routers/auth.py
from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.orm import Session
import random, string

from app.db.database import get_db
from app.db.models import UserAccount, UserRole
from app.schemas.schemas import SignupHead, SignupMember
from app.core.security import hash_password, verify_password, create_access_token

router = APIRouter(prefix="/auth", tags=["Auth"])


# Generate a random family code → Example: "A7KD92"
def generate_family_code():
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))


# -------------------------------------------------------
# 1️⃣ SIGNUP – FAMILY HEAD
# -------------------------------------------------------
@router.post("/signup/head")
def signup_head(payload: SignupHead, db: Session = Depends(get_db)):

    # Check if email exists
    existing = db.query(UserAccount).filter(UserAccount.email == payload.email).first()
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered.")

    # Generate unique family code for the head
    family_code = generate_family_code()

    user = UserAccount(
        full_name=payload.full_name,
        email=payload.email,
        password=hash_password(payload.password),
        role=UserRole.head,
        family_code=family_code,
    )

    db.add(user)
    db.commit()
    db.refresh(user)

    # Create JWT token
    token = create_access_token(
        {"id": user.id, "email": user.email, "role": user.role.value}
    )

    return {
        "status": True,
        "message": "Family Head signup successful",
        "token": token,
        "user": {
            "id": user.id,
            "email": user.email,
            "role": user.role.value,
            "family_code": user.family_code
        }
    }



# -------------------------------------------------------
# 2️⃣ SIGNUP – FAMILY MEMBER
# -------------------------------------------------------
@router.post("/signup/member")
def signup_member(payload: SignupMember, db: Session = Depends(get_db)):

    # Check if family code belongs to a REAL family head
    head = db.query(UserAccount).filter(
        UserAccount.family_code == payload.family_code,
        UserAccount.role == UserRole.head
    ).first()

    if not head:
        raise HTTPException(status_code=400, detail="Invalid family code.")

    # Check if email exists
    existing = db.query(UserAccount).filter(UserAccount.email == payload.email).first()
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered.")

    user = UserAccount(
        full_name=payload.full_name,
        email=payload.email,
        password=hash_password(payload.password),
        role=UserRole.member,
        family_code=payload.family_code,
    )

    db.add(user)
    db.commit()
    db.refresh(user)

    # Create JWT token
    token = create_access_token(
        {"id": user.id, "email": user.email, "role": user.role.value}
    )

    return {
        "status": True,
        "message": "Family Member signup successful",
        "token": token,
        "user": {
            "id": user.id,
            "email": user.email,
            "role": user.role.value,
            "family_code": user.family_code
        }
    }


# @router.post("/login", response_model=TokenOut)
# def login(payload: UserLogin, db: Session = Depends(get_db)):
#     user = db.query(UserDB).filter(UserDB.email == payload.email).first()
#     if not user or not verify_password(payload.password, user.password):
#         raise HTTPException(status_code=400, detail="Invalid email or password")

#     token = create_access_token({"sub": str(user.id)})
#     return {
#         "user": UserOut.model_validate(user),
#         "access_token": token,
#         "token_type": "bearer",
#         "expires_in_minutes": settings.ACCESS_TOKEN_EXPIRE_MINUTES,
#     }