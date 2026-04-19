from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.db.database import Base

class CategoryBudget(Base):
    __tablename__ = "category_budgets"

    id = Column(Integer, primary_key=True, index=True)

    family_code = Column(String(10), index=True, nullable=False)
    category_name = Column(String(50), nullable=False)

    scope = Column(String(10), nullable=False)   # "family" | "member"
    owner_id = Column(Integer, nullable=True)    # NULL for family, member_id for member

    month = Column(Integer, nullable=False)

    year = Column(Integer, nullable=False)    
    budget = Column(Float, default=0.0)
    spent = Column(Float, default=0.0)

    created_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        UniqueConstraint(
            "family_code", "scope", "owner_id", "category_name", "month", "year",
            name="uq_category_budget_scope"
        ),
    )