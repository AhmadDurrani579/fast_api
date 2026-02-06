from fastapi import FastAPI
from starlette.middleware.cors import CORSMiddleware
from starlette.staticfiles import StaticFiles
import os
from app.db.database import Base, engine
from app.routers import auth
from app.routers import profile
from app.routers import users
from app.routers import family
from app.routers import expense
from app.routers import categorybudget
from app.routers import budget
# from openai import OpenAI
from app.routers import chat_ws
# create missing tables (won't alter existing columns)
Base.metadata.create_all(bind=engine)

app = FastAPI(title="FamFin API")

# static uploads
UPLOAD_DIR = os.path.join(os.getcwd(), "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=UPLOAD_DIR), name="uploads")

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
def root():
    return {"message": "FamFin API is running 🚀"}

# include routers
app.include_router(auth.router)
app.include_router(profile.router)
app.include_router(users.router)
app.include_router(family.router)
app.include_router(expense.router)
app.include_router(categorybudget.router)
app.include_router(budget.router)
app.include_router(chat_ws.router)
# app.include_router(users.router)
# app.include_router(posts.router)
# app.include_router(comments.router)
# app.include_router(likes.router)


