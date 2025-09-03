# app/routers/likes.py
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from app.db.database import get_db
from app.db.models import UserDB, PostDB, LikeDB
from app.schemas.schemas import PostWithComments
from app.deps.deps import get_current_user
from app.routers.posts import load_post_full

router = APIRouter(prefix="/likes", tags=["likes"])

@router.post("/toggle/{post_id}", response_model=PostWithComments)
def like_toggle(
    post_id: int,
    db: Session = Depends(get_db),
    current_user: UserDB = Depends(get_current_user),
):
    # Ensure post exists
    post = db.get(PostDB, post_id)
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")

    # Toggle like for the authenticated user
    existing = (
        db.query(LikeDB)
          .filter_by(user_id=current_user.id, post_id=post_id)
          .first()
    )
    if existing:
        db.delete(existing)
        db.commit()
        return load_post_full(db, post_id, viewer_id=current_user.id)

    try:
        db.add(LikeDB(user_id=current_user.id, post_id=post_id))
        db.commit()
    except IntegrityError:
        db.rollback()

    return load_post_full(db, post_id, viewer_id=current_user.id)