from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.orm import Session
import random, string

from app.db.database import get_db
from app.db.models import UserDB
from app.schemas.schemas import SignupHead, SignupMember, LoginSchema, SendCodeRequest, VerifyOTPRequest
from app.core.security import hash_password, create_access_token, verify_password, generate_otp
from app.utils.email_utils import send_email

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

@router.post("/login")
def login(payload: LoginSchema, db: Session = Depends(get_db)):
    # Find user by email
    user = db.query(UserDB).filter(UserDB.email == payload.email).first()

    if not user:
        raise HTTPException(status_code=400, detail="Invalid email or password")

    # Verify password
    if not verify_password(payload.password, user.password):
        raise HTTPException(status_code=400, detail="Invalid email or password")

    # Create JWT token
    token = create_access_token(
        {"id": user.id, "email": user.email, "role": user.role}
    )

    return {
        "status": True,
        "message": "Login successful",
        "token": token,
        "user": {
            "id": user.id,
            "full_name": user.full_name,
            "email": user.email,
            "role": user.role,
            "family_code": user.family_code
        }
    }

@router.post("/send-code")
def send_code(payload: SendCodeRequest, db: Session = Depends(get_db)):
    # 1. Check if email exists
    user = db.query(UserDB).filter(UserDB.email == payload.email).first()
    if not user:
        raise HTTPException(status_code=404, detail="Email not found")

    # 2. Generate OTP
    otp = generate_otp()

    # 3. Send the OTP by email
    subject = "Your FamFin Verification Code"
    body = f"Your verification code is: {otp}"
    send_email(payload.email, "Your OTP Code", f"Your OTP is {otp}")
    # 4. Return success message (do NOT return OTP)
    return {
        "status": True,
        "message": "Verification code sent to email."
    }

@router.post("/verify-code")
def verify_code(payload: VerifyOTPRequest, db: Session = Depends(get_db)):

    user = db.query(UserDB).filter(UserDB.email == payload.email).first()

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if not user.otp_code:
        raise HTTPException(status_code=400, detail="No OTP sent. Please request again.")

    # CHECK OTP
    if user.otp_code != payload.otp:
        raise HTTPException(status_code=400, detail="Invalid OTP")

    # CHECK EXPIRY
    if user.otp_expiry < datetime.utcnow():
        raise HTTPException(status_code=400, detail="OTP expired")

    # SUCCESS — CLEAR OTP
    user.otp_code = None
    user.otp_expiry = None
    db.commit()

    return {
        "status": True,
        "message": "OTP verified successfully"
    }