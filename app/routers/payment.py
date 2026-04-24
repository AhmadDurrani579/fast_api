from fastapi import APIRouter
from app.services.vaults_pay import VaultsPayService

router = APIRouter()

vault_service = VaultsPayService()

router = APIRouter(prefix="/payment", tags=["Payment"])
@router.post("/initiate")

def initiate_payment(amount: float):
    return vault_service.initiate_payment(amount)