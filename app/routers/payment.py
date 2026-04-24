from fastapi import APIRouter
from app.services.vaults_pay import VaultsPayService
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.db.database import get_db
from app.db.models import UserUsage, UserDB
from app.schemas.schemas import VerifyPaymentRequest
from app.deps.deps import get_current_user

vault_service = VaultsPayService()

router = APIRouter(prefix="/payment", tags=["Payment"])
@router.post("/initiate")
def initiate_payment(
    amount: float,
    current_user: UserDB = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    return vault_service.initiate_payment(amount)


@router.post("/verify")
def verify_payment(
    payload: VerifyPaymentRequest,
    current_user: UserDB = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    usage = db.query(UserUsage).filter_by(user_id=current_user.id).first()

    if not usage:
        usage = UserUsage(user_id=current_user.id)
        db.add(usage)

    from datetime import datetime
    now = datetime.utcnow()

    # 🔥 Unlock user
    usage.is_paid = True
    usage.plan_type = "pro"
    usage.request_count = 0
    usage.month = now.month
    usage.year = now.year

    db.commit()

    return {
        "status": "success",
        "message": "User upgraded successfully",
        "payment_id": payload.payment_id
    }