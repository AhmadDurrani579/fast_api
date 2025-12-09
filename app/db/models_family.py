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

    # Permanent values (NOT monthly)
    total_balance = Column(Float, default=0.0)
    total_income = Column(Float, default=0.0)   # lifetime or initial income

    expected_members = Column(String, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())

    head = relationship("UserDB", back_populates="family")


# -------------------------------------------------
# 🟩 FAMILY MEMBER TABLE
# -------------------------------------------------
class FamilyMember(Base):
    __tablename__ = "family_members"

    id = Column(Integer, primary_key=True, index=True)

    # Null until signup → then we attach real user_id
    user_id = Column(Integer, ForeignKey("user_accounts.id"), nullable=True)

    family_code = Column(String(10), index=True, nullable=False)
    name = Column(String(100), nullable=False)

    # Head sets role later (wife, son, etc.)
    role = Column(String(20), nullable=True)

    allocated_budget = Column(Float, default=0.0)
    spent_amount = Column(Float, default=0.0)

    created_at = Column(DateTime(timezone=True), server_default=func.now())

    user = relationship("UserDB", backref="family_member")



# -------------------------------------------------
# 🟧 MONTHLY FAMILY DATA (Per Month)
# -------------------------------------------------
class FamilyMonthly(Base):
    __tablename__ = "family_monthly"

    id = Column(Integer, primary_key=True, index=True)
    family_id = Column(Integer, ForeignKey("families.id"), nullable=False)

    # Month identifiers
    year = Column(Integer, nullable=False)
    month = Column(Integer, nullable=False)  # 1–12

    # User-set monthly data
    monthly_income = Column(Float, default=0.0)
    monthly_budget = Column(Float, default=0.0)

    # 🔮 Future AI prediction fields (will use later)
    predicted_income = Column(Float, nullable=True)
    predicted_budget = Column(Float, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())

    family = relationship("Family", backref="monthly_records")