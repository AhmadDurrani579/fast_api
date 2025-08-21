from fastapi import FastAPI, Depends, HTTPException
from pydantic import BaseModel, EmailStr
from sqlalchemy import create_engine, Column, Integer, String
from sqlalchemy.orm import sessionmaker, declarative_base, Session
import bcrypt
from starlette.middleware.cors import CORSMiddleware
from sqlalchemy import ForeignKey, DateTime, Text
from sqlalchemy.orm import relationship
from datetime import datetime

import os, uuid
from typing import Optional, List
from fastapi import File, UploadFile, Form
from starlette.staticfiles import StaticFiles
from pydantic import BaseModel as PModel
from typing import Optional, List

# ----------------- MySQL Connection -----------------
DATABASE_URL = "postgresql+psycopg2://city_university_db_user:au84DXp5L55SYrir23DzrezulwqSJZzc@dpg-d2gitojuibrs73ed7s00-a.oregon-postgres.render.com:5432/city_university_db"
engine = create_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
# ----------------- ORM Model (matches user_accounts table) -----------------


app = FastAPI()



Base = declarative_base()
UPLOAD_DIR = "uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=UPLOAD_DIR), name="uploads")


app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],          # allow all origins
    allow_credentials=False,      # must be False when using "*"
    allow_methods=["*"],          # GET, POST, PUT, DELETE, OPTIONS, ...
    allow_headers=["*"],          # Authorization, Content-Type, etc.
)


class UserDB(Base):
    __tablename__ = "user_accounts"
    id = Column(Integer, primary_key=True, index=True)
    full_name = Column(String(100), nullable=False)
    email = Column(String(100), unique=True, index=True, nullable=False)
    password = Column(String(255), nullable=False)

# Dependency for getting DB session in routes
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# ----------------- Request Body Model -----------------
class UserSignup(BaseModel):
    full_name: str
    email: EmailStr
    password: str

class UserLogin(BaseModel):
    email: EmailStr
    password: str

class ResetPassword(BaseModel):
    email: EmailStr
    new_password: str

class PostOut(PModel):
    id: int
    user_id: int
    content: Optional[str] = None
    image_url: Optional[str] = None
    created_at: datetime
    class Config:
        from_attributes = True  # pydantic v2


class PostDB(Base):
    __tablename__ = "posts"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("user_accounts.id", ondelete="CASCADE"), nullable=False)
    content = Column(Text, nullable=True)                 # text body (optional)
    image_url = Column(String(300), nullable=True)        # store public URL or /uploads/<file>
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    user = relationship("UserDB")  # optional convenience

    

@app.get("/")
def home():
    return {"message": "Hello FastAPI!"}

@app.post("/signup")
def signup(user: UserSignup, db: Session = Depends(get_db)):
    # Check if email exists
    if db.query(UserDB).filter(UserDB.email == user.email).first():
        raise HTTPException(status_code=400, detail="Email already registered")

    # Hash password
    hashed_pw = bcrypt.hashpw(user.password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

    # Create new user
    new_user = UserDB(full_name=user.full_name, email=user.email, password=hashed_pw)
    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    return {"message": "User registered successfully", "user_id": new_user.id}# class Item(BaseModel):

@app.post("/login")
def login(user: UserLogin, db: Session = Depends(get_db)):
    db_user = db.query(UserDB).filter(UserDB.email == user.email).first()
    if not db_user:
        raise HTTPException(status_code=400, detail="Invalid email or password")
    if not bcrypt.checkpw(user.password.encode('utf-8'), db_user.password.encode('utf-8')):
        raise HTTPException(status_code=400, detail="Invalid email or password")
    return {"message": f"Welcome back, {db_user.full_name}!"}

@app.post("/forgot-password")
def forgot_password(reset: ResetPassword, db: Session = Depends(get_db)):
    db_user = db.query(UserDB).filter(UserDB.email == reset.email).first()
    if not db_user:
        raise HTTPException(status_code=404, detail="Email not found")

    hashed_pw = bcrypt.hashpw(reset.new_password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
    db_user.password = hashed_pw
    db.commit()
    return {"message": "Password updated successfully"}

@app.post("/posts", response_model=PostOut)
async def create_post(
    user_id: int = Form(...),
    content: Optional[str] = Form(None),
    image: Optional[UploadFile] = File(None),
    db: Session = Depends(get_db),
):
    # normalize content
    content = (content or "").strip()
    # treat empty file input as no image
    if image is not None and not getattr(image, "filename", ""):
        image = None

    if not content and image is None:
        raise HTTPException(status_code=400, detail="Provide content or an image")

    user = db.get(UserDB, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    image_url = None
    if image is not None:
        allowed = {"image/png", "image/jpeg", "image/jpg", "image/webp"}
        if image.content_type not in allowed:
            raise HTTPException(status_code=415, detail="Unsupported image type")
        ext = { "image/png": ".png", "image/jpeg": ".jpg", "image/jpg": ".jpg", "image/webp": ".webp" }[image.content_type]
        filename = f"{uuid.uuid4().hex}{ext}"
        with open(os.path.join(UPLOAD_DIR, filename), "wb") as f:
            f.write(await image.read())
        image_url = f"/uploads/{filename}"

    post = PostDB(user_id=user_id, content=content or None, image_url=image_url)
    db.add(post); db.commit(); db.refresh(post)
    return post



@app.get("/posts", response_model=List[PostOut])
def list_posts(
    user_id: Optional[int] = None,   # ← pass ?user_id=1
    limit: Optional[int] = None,     # ← optional
    db: Session = Depends(get_db),
):
    q = db.query(PostDB).order_by(PostDB.created_at.desc())
    if user_id is not None:
        q = q.filter(PostDB.user_id == user_id)
    if limit is not None:
        q = q.limit(limit)
    return q.all()