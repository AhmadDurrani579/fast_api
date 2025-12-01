from fastapi import Depends, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from jose import jwt, JWTError

from app.core.config import settings
from app.db.database import get_db
from app.db.models import UserDB

bearer_scheme = HTTPBearer()
credentials_exception = HTTPException(
    status_code=401,
    detail="Invalid or expired token",
)

def get_current_user(
    token: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    db: Session = Depends(get_db)
):
    try:
        payload = jwt.decode(
            token.credentials,
            settings.JWT_SECRET,
            algorithms=[settings.JWT_ALGORITHM]
        )
        user_id = payload.get("id")

        if not user_id:
            raise credentials_exception

    except JWTError:
        raise credentials_exception

    user = db.query(UserDB).filter(UserDB.id == user_id).first()

    if not user:
        raise credentials_exception

    return user