from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.orm import Session
import random, string

from app.db.database import get_db
from app.db.models import UserDB
from app.schemas.schemas import SignupHead, SignupMember, LoginSchema, SendCodeRequest, VerifyOTPRequest, ResetPasswordRequest
from app.core.security import hash_password, create_access_token, verify_password, generate_otp
from app.utils.email_utils import send_email
from datetime import datetime, timedelta

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
    # 1) Check family head exists with that family_code
    head = db.query(UserDB).filter(
        UserDB.family_code == payload.family_code,
        UserDB.role == "head"
    ).first()

    if not head:
        raise HTTPException(status_code=400, detail="Invalid family code.")

    # 2) Check email not already used
    existing = db.query(UserDB).filter(UserDB.email == payload.email).first()
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered.")

    # 3) Create the user as member
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

    # 4) 🔗 Try to connect this account to a FamilyMember row
    from app.db.models_family import FamilyMember  # local import to avoid cycles

    member_row = db.query(FamilyMember).filter(
        FamilyMember.family_code == payload.family_code,
        FamilyMember.name == payload.full_name  # match by name
    ).first()

    if member_row:
        member_row.user_id = user.id
        db.commit()
        db.refresh(member_row)

    # 5) Issue token
    token = create_access_token(
        {"id": user.id, "email": user.email, "role": user.role}
    )
    return {
        "status": True,
        "message": "Family Member signup successful",
        "user": {
            "id": user.id,
            "email": user.email,
            "full_name": user.full_name,
            "role": user.role,
            "family_code": user.family_code
        },
        "token": token
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
    send_email(payload.email, "Your OTP Code", f"Your OTP is {otp}")

    # 4. Save OTP + expiry in database (THIS PART WAS MISSING)
    user.otp_code = otp
    user.otp_expiry = datetime.utcnow() + timedelta(minutes=10)
    db.commit()
    db.refresh(user)

    # 5. Return success message
    return {
        "status": True,
        "message": "Verification code sent to email."
    }

from datetime import datetime, timedelta, timezone
from fastapi import HTTPException, Depends
from sqlalchemy.orm import Session

@router.post("/verify-code")
def verify_code(payload: VerifyOTPRequest, db: Session = Depends(get_db)):
    user = db.query(UserDB).filter(UserDB.email == payload.email).first()
    if not user:
        raise HTTPException(status_code=404, detail="Email not found")

    # 1. No OTP sent
    if not user.otp_code or not user.otp_expiry:
        raise HTTPException(status_code=400, detail="No OTP sent. Please request again.")

    # 2. OTP expired (timezone-aware)
    if user.otp_expiry < datetime.now(timezone.utc):
        raise HTTPException(status_code=400, detail="OTP expired. Request a new one.")

    # 3. Wrong OTP
    if user.otp_code != payload.otp:
        raise HTTPException(status_code=400, detail="Incorrect OTP")

    # 4. OTP is correct → clear it
    user.otp_code = None
    user.otp_expiry = None
    db.commit()

    return {"status": True, "message": "OTP verified successfully"}


@router.post("/reset-password")
def reset_password(payload: ResetPasswordRequest, db: Session = Depends(get_db)):
    user = db.query(UserDB).filter(UserDB.email == payload.email).first()
    if not user:
        raise HTTPException(status_code=404, detail="Email not found")

    # Require OTP verification first
    if user.otp_code is not None:
        raise HTTPException(status_code=400, detail="OTP not verified yet")

    # Update password
    user.password = hash_password(payload.new_password)

    # Clear OTP fields just in case
    user.otp_code = None
    user.otp_expiry = None

    db.commit()

    return {
        "status": True,
        "message": "Password reset successfully"
    }