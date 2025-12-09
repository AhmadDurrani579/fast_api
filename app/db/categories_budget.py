from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.db.database import Base


class CategoryBudget(Base):
    __tablename__ = "category_budgets"

    id = Column(Integer, primary_key=True, index=True)
    family_code = Column(String(10), index=True, nullable=False)

    category_name = Column(String(50), nullable=False)
    budget = Column(Float, default=0.0)
    spent = Column(Float, default=0.0)

    created_at = Column(DateTime(timezone=True), server_default=func.now())