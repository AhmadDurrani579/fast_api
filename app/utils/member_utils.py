from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models.family_member import FamilyMember


def get_or_assign_member(db: Session, family_code: str, user_id: int) -> FamilyMember:
    # Try already linked member
    fm = db.query(FamilyMember).filter(
        FamilyMember.family_code == family_code,
        FamilyMember.user_id == user_id
    ).first()

    if fm:
        return fm

    # Assign to empty member slot
    fm = db.query(FamilyMember).filter(
        FamilyMember.family_code == family_code,
        FamilyMember.user_id.is_(None)
    ).first()

    if not fm:
        raise HTTPException(400, "No available member slot")

    fm.user_id = user_id
    db.commit()
    db.refresh(fm)
    return fm