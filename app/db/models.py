from sqlalchemy import Column, Integer, String, Enum, ForeignKey, DateTime, Text, UniqueConstraint
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.db.database import Base
from sqlalchemy import Boolean
import enum


class UserRole(enum.Enum):
    head = "head"
    member = "member"


class UserDB(Base):
    __tablename__ = "user_accounts"

    id = Column(Integer, primary_key=True, index=True)
    full_name = Column(String(100), nullable=False)
    email = Column(String(120), unique=True, index=True, nullable=False)
    password = Column(String(255), nullable=False)

    role = Column(String(20), nullable=False)  # "head" or "member"
    family_code = Column(String(10), nullable=True)

    otp_code = Column(String(6), nullable=True)
    otp_expiry = Column(DateTime, nullable=True)

    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now()
    )

    family = relationship(
        "Family",
        back_populates="head",
        uselist=False
    )

    usage = relationship(
        "UserUsage",
        back_populates="user",
        uselist=False
    )

    chats = relationship(
        "ChatMessage",
        back_populates="user",
        cascade="all, delete-orphan"
    )
class UserUsage(Base):
    __tablename__ = "user_usage"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("user_accounts.id", ondelete="CASCADE"), unique=True, nullable=False)
    request_count = Column(Integer, default=0)
    plan_type = Column(String, default="free")
    is_paid = Column(Boolean, default=False)
    month = Column(Integer)

    year = Column(Integer)
    # 🔗 Relationship back to user
    user = relationship("UserDB", back_populates="usage")


