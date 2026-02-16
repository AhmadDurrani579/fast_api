from sqlalchemy.orm import Session
from datetime import datetime
import calendar

from app.db.models_family import Family, FamilyMonthly
from app.db.models_expenses import ExpenseDB


def build_finance_context(
    db: Session,
    family_code: str,
    year: int = None,
    month: int = None
):
    """
    Fetch financial data for specific month.
    If year/month not provided → use current month.
    """

    family = db.query(Family).filter(
        Family.family_code == family_code
    ).first()

    if not family:
        return None

    # If no month/year passed → use current
    now = datetime.utcnow()
    year = year or now.year
    month = month or now.month

    monthly = db.query(FamilyMonthly).filter(
        FamilyMonthly.family_id == family.id,
        FamilyMonthly.year == year,
        FamilyMonthly.month == month
    ).first()

    if not monthly:
        return None

    last_day = calendar.monthrange(year, month)[1]
    start_date = f"{year}-{month:02d}-01"
    end_date = f"{year}-{month:02d}-{last_day:02d}"

    expenses = db.query(ExpenseDB).filter(
        ExpenseDB.family_code == family_code,
        ExpenseDB.created_at.between(start_date, end_date)
    ).all()

    total_expenses = sum(e.amount for e in expenses)

    category_data = {}
    for e in expenses:
        category_data[e.category] = category_data.get(e.category, 0) + e.amount

    context = {
        "year": year,
        "month": month,
        "starting_balance": monthly.starting_balance,
        "monthly_income": monthly.monthly_income,
        "monthly_budget": monthly.monthly_budget,
        "closing_balance": monthly.closing_balance,
        "total_expenses": total_expenses,
        "categories": category_data
    }

    return context