from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.db.database import Base

class Family(Base):
    __tablename__ = "families"

    id = Column(Integer, primary_key=True, index=True)
    family_code = Column(String(10), unique=True, index=True, nullable=False)
    head_id = Column(Integer, ForeignKey("user_accounts.id"), nullable=False)

    total_balance = Column(Float, default=0.0)
    total_income = Column(Float, default=0.0)

    expected_members = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    head = relationship("UserDB", back_populates="family")


class FamilyMember(Base):
    __tablename__ = "family_members"

    id = Column(Integer, primary_key=True, index=True)

    family_code = Column(String(10), index=True, nullable=False)
    name = Column(String(100), nullable=False)

    # 🔗 Link to the actual user account (optional, set when member signs up)
    user_id = Column(Integer, ForeignKey("user_accounts.id"), nullable=True)

    role = Column(String(20), nullable=False, default="member")

    allocated_budget = Column(Float, default=0.0)
    spent_amount = Column(Float, default=0.0)

    created_at = Column(DateTime(timezone=True), server_default=func.now())