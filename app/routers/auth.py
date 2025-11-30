from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.orm import Session
import random, string

from app.db.database import get_db
from app.db.models import UserDB
from app.schemas.schemas import SignupHead, SignupMember
from app.core.security import hash_password, create_access_token

router = APIRouter(prefix="/auth", tags=["Auth"])


def generate_family_code():
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))


@router.post("/signup/head")
def signup_head(payload: SignupHead, db: Session = Depends(get_db)):
    existing = db.query(UserDB).filter(UserDB.email == payload.email).first()
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered.")

    family_code = generate_family_code()

    user = UserDB(
        full_name=payload.full_name,
        email=payload.email,
        password=hash_password(payload.password),
        role="head",
        family_code=family_code,
    )

    db.add(user)
    db.commit()
    db.refresh(user)

    token = create_access_token(
        {"id": user.id, "email": user.email, "role": user.role}
    )

    return {
        "status": True,
        "message": "Family Head signup successful",
        "token": token,
        "user": {
            "id": user.id,
            "email": user.email,
            "role": user.role,
            "family_code": user.family_code
        }
    }


@router.post("/signup/member")
def signup_member(payload: SignupMember, db: Session = Depends(get_db)):
    head = db.query(UserDB).filter(
        UserDB.family_code == payload.family_code,
        UserDB.role == "head"
    ).first()

    if not head:
        raise HTTPException(status_code=400, detail="Invalid family code.")

    existing = db.query(UserDB).filter(UserDB.email == payload.email).first()
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered.")

    user = UserDB(
        full_name=payload.full_name,
        email=payload.email,
        password=hash_password(payload.password),
        role="member",
        family_code=payload.family_code,
    )

    db.add(user)
    db.commit()
    db.refresh(user)

    token = create_access_token(
        {"id": user.id, "email": user.email, "role": user.role}
    )

    return {
        "status": True,
        "message": "Family Member signup successful",
        "token": token,
        "user": {
            "id": user.id,
            "email": user.email,
            "role": user.role,
            "family_code": user.family_code
        }
    }