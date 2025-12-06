from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.db.database import Base

class ExpenseDB(Base):
    __tablename__ = "expenses"

    id = Column(Integer, primary_key=True, index=True)

    family_code = Column(String(10), index=True, nullable=False)
    member_id = Column(Integer, ForeignKey("family_members.id"), nullable=True)

    name = Column(String(100), nullable=False)
    category = Column(String(50), nullable=False)
    amount = Column(Float, nullable=False)

    created_at = Column(DateTime(timezone=True), server_default=func.now())