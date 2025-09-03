from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.db.database import get_db
from app.db.models import PostDB, CommentDB, UserDB
from app.schemas.schemas import CommentCreate, CommentOut
from app.deps.deps import get_current_user

router = APIRouter(prefix="/comments", tags=["comments"])

@router.post("", response_model=CommentOut, status_code=201)
def create_comment(
    payload: CommentCreate,
    db: Session = Depends(get_db),
    current_user: UserDB = Depends(get_current_user),
):
    # Ensure the post exists
    post = db.get(PostDB, payload.post_id)
    if not post:
        raise HTTPException(404, "Post not found")

    # Create the comment with the user_id from the token
    c = CommentDB(
        content=payload.content,
        post_id=payload.post_id,
        user_id=current_user.id
    )
    db.add(c)
    db.commit()
    db.refresh(c)

    # hydrate relationship for response
    _ = c.user
    return c