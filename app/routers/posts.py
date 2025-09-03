from fastapi import APIRouter, Depends, HTTPException, File, UploadFile, Form
from sqlalchemy.orm import Session, selectinload
from datetime import datetime
from typing import Optional, List
import os
from app.db.database import get_db
from app.db.models import UserDB, PostDB, CommentDB, LikeDB
from app.schemas.schemas import PostWithComments
from app.deps.deps import get_current_user
from app.utils.files import save_upload
from fastapi import Query

router = APIRouter(prefix="/posts", tags=["posts"])

UPLOAD_DIR = os.path.join(os.getcwd(), "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)

def load_post_full(db: Session, post_id: int, viewer_id: int | None = None) -> PostDB:
    post = (
        db.query(PostDB)
          .options(
              selectinload(PostDB.user),
              selectinload(PostDB.comments).selectinload(CommentDB.user),
              selectinload(PostDB.likes),
          )
          .filter(PostDB.id == post_id)
          .first()
    )
    if not post: raise HTTPException(404, "Post not found")
    post.like_count = len(post.likes)
    if viewer_id is not None:
        post.is_liked_by_user = db.query(LikeDB).filter(LikeDB.user_id == viewer_id, LikeDB.post_id == post_id).first() is not None
    else:
        post.is_liked_by_user = None
    post.comments.sort(key=lambda c: c.created_at or datetime.min, reverse=True)
    return post

@router.post("", response_model=PostWithComments, status_code=201)
def create_post(
    content: Optional[str] = Form(None),
    image: Optional[UploadFile] = File(None),
    db: Session = Depends(get_db),
    current_user: UserDB = Depends(get_current_user),
):
    # normalize content -> None if empty/whitespace
    content = (content or "").strip() or None

    # will return None if no file was actually chosen / empty payload
    image_url = save_upload(UPLOAD_DIR, image)

    # must have at least one of content or image
    if content is None and image_url is None:
        raise HTTPException(status_code=400, detail="Provide content or an image")

    post = PostDB(user_id=current_user.id, content=content, image_url=image_url)
    db.add(post); db.commit(); db.refresh(post)

    # hydrate fields for your response model
    post.user = current_user
    post.comments = []
    post.likes = []
    post.like_count = 0
    post.is_liked_by_user = None
    return post


@router.get("/", response_model=List[PostWithComments])
def list_posts(
    db: Session = Depends(get_db),
    current_user: UserDB = Depends(get_current_user),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    posts: List[PostDB] = (
        db.query(PostDB)
          .options(
              selectinload(PostDB.user),
              selectinload(PostDB.comments).selectinload(CommentDB.user),
              selectinload(PostDB.likes),  # still needed if you want to count likes directly
          )
          .order_by(PostDB.created_at.desc())
          .offset(offset)
          .limit(limit)
          .all()
    )

    post_ids = [p.id for p in posts]
    liked_set = set()
    if post_ids:
        liked_rows = (
            db.query(LikeDB.post_id)
              .filter(LikeDB.user_id == current_user.id, LikeDB.post_id.in_(post_ids))
              .all()
        )
        liked_set = {pid for (pid,) in liked_rows}

    result: List[PostWithComments] = []
    for p in posts:
        p.comments.sort(key=lambda c: c.created_at or datetime.min, reverse=True)
        result.append(PostWithComments(
            id=p.id,
            user_id=p.user_id,
            content=p.content,
            image_url=p.image_url,
            created_at=p.created_at,
            user=p.user,
            comments=p.comments,
            like_count=len(p.likes),
            is_liked_by_user=(p.id in liked_set)
        ))

    return result


@router.get("/{post_id}", response_model=PostWithComments)
def get_post(post_id: int, viewer_id: int | None = None, db: Session = Depends(get_db)):
    return load_post_full(db, post_id, viewer_id)