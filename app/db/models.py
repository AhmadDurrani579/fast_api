from sqlalchemy import Column, Integer, String, Enum, ForeignKey, DateTime, Text, UniqueConstraint
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.db.database import Base
import enum


class UserRole(enum.Enum):
    head = "head"
    member = "member"


class UserAccount(Base):
    __tablename__ = "user_accounts"
    id = Column(Integer, primary_key=True, index=True)
    full_name = Column(String(100), nullable=False)
    email = Column(String(120), unique=True, index=True, nullable=False)
    password = Column(String(255), nullable=False)
    role = Column(Enum(UserRole), nullable=False)   # "head" or "member"
    family_code = Column(String(10), index=True)    # Head gets code, members use it
    family_id = Column(Integer, index=True)         # Same family group ID
    created_at = Column(String, server_default=func.now())



class UserDB(Base):
    __tablename__ = "user_accounts"

    id = Column(Integer, primary_key=True, index=True)
    full_name = Column(String(100), nullable=False)
    email = Column(String(120), unique=True, index=True, nullable=False)
    password = Column(String(255), nullable=False)

    role = Column(String(20), nullable=False)  # "head" or "member"
    family_code = Column(String(10), nullable=True)  # Only for members

    created_at = Column(DateTime(timezone=True), server_default=func.now())


# class PostDB(Base):
#     __tablename__ = "posts"
#     id = Column(Integer, primary_key=True, index=True)
#     user_id = Column(Integer, ForeignKey("user_accounts.id", ondelete="CASCADE"), nullable=False)
#     content = Column(Text, nullable=True)
#     image_url = Column(String(300), nullable=True)
#     created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

#     user = relationship("UserDB")
#     comments = relationship("CommentDB", backref="post", cascade="all, delete-orphan")
#     likes = relationship("LikeDB", back_populates="post", cascade="all, delete-orphan")

# class CommentDB(Base):
#     __tablename__ = "comments"
#     id = Column(Integer, primary_key=True, index=True)
#     content = Column(Text, nullable=False)
#     created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
#     post_id = Column(Integer, ForeignKey("posts.id", ondelete="CASCADE"), nullable=False)
#     user_id = Column(Integer, ForeignKey("user_accounts.id", ondelete="CASCADE"), nullable=False)
#     user = relationship("UserDB")

# class LikeDB(Base):
#     __tablename__ = "likes"
#     id = Column(Integer, primary_key=True, index=True)
#     user_id = Column(Integer, ForeignKey("user_accounts.id", ondelete="CASCADE"), nullable=False)
#     post_id = Column(Integer, ForeignKey("posts.id", ondelete="CASCADE"), nullable=False)
#     created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

#     __table_args__ = (UniqueConstraint("user_id", "post_id", name="unique_like"),)

#     user = relationship("UserDB")
#     post = relationship("PostDB", back_populates="likes")