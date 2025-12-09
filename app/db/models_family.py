from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.db.database import Base


# -------------------------------------------------
# 🟦 FAMILY TABLE (stable info)
# -------------------------------------------------
class Family(Base):
    __tablename__ = "families"

    id = Column(Integer, primary_key=True, index=True)
    family_code = Column(String(10), unique=True, index=True, nullable=False)
    head_id = Column(Integer, ForeignKey("user_accounts.id"), nullable=False)

    total_balance = Column(Float, default=0.0)
    monthly_budget = Column(Float, default=0.0)
    expected_members = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    head = relationship("UserDB", back_populates="family")

# -------------------------------------------------
# 🟩 FAMILY MEMBER TABLE
# -------------------------------------------------
class FamilyMember(Base):
    __tablename__ = "family_members"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("user_accounts.id"), nullable=True)

    family_code = Column(String(10), nullable=False)
    name = Column(String(100), nullable=False)
    role = Column(String(20), nullable=True)

    allocated_budget = Column(Float, default=0.0)
    spent_amount = Column(Float, default=0.0)


# -------------------------------------------------
# 🟧 MONTHLY FAMILY DATA (Per Month)
# -------------------------------------------------
class FamilyMonthly(Base):
    __tablename__ = "family_monthly"

    id = Column(Integer, primary_key=True, index=True)
    family_id = Column(Integer, ForeignKey("families.id"), nullable=False)

    year = Column(Integer, nullable=False)
    month = Column(Integer, nullable=False)

    monthly_income = Column(Float, default=0.0)
    monthly_budget = Column(Float, default=0.0)

    predicted_income = Column(Float, nullable=True)
    predicted_budget = Column(Float, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())