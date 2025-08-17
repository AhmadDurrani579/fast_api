from fastapi import FastAPI, Depends, HTTPException
from pydantic import BaseModel, EmailStr
from sqlalchemy import create_engine, Column, Integer, String
from sqlalchemy.orm import sessionmaker, declarative_base, Session
import bcrypt

# ----------------- MySQL Connection -----------------
DATABASE_URL = "mysql+pymysql://root:@localhost:3306/city_university"
engine = create_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


# ----------------- ORM Model (matches user_accounts table) -----------------
class UserDB(Base):
    __tablename__ = "user_accounts"
    id = Column(Integer, primary_key=True, index=True)
    full_name = Column(String(100), nullable=False)
    email = Column(String(100), unique=True, index=True, nullable=False)
    password = Column(String(255), nullable=False)


app = FastAPI()

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