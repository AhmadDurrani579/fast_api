from fastapi import APIRouter
from app.services.vaults_pay import VaultsPayService

router = APIRouter()

vault_service = VaultsPayService()

@router.get("/vaults/token")
def get_vaults_token():
    try:
        token = vault_service.get_token()
        return {
            "status": "success",
            "access_token": token
        }
    except Exception as e:
        return {
            "status": "error",
            "message": str(e)
        }