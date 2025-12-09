from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func, extract
from datetime import datetime

from app.db.database import get_db
from app.db.models import UserDB
from app.db.models_family import Family, FamilyMonthly
from app.db.models_expenses import ExpenseDB
from app.db.categories_budget import CategoryBudget
from app.deps.deps import get_current_user
from app.constants.categories import CATEGORIES   # <-- IMPORTANT

router = APIRouter(prefix="/expense", tags=["expense"])


@router.get("/insights")
def get_budget_insights(
    current_user: UserDB = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    # ---------------- FAMILY CHECK ----------------
    family = db.query(Family).filter(
        Family.family_code == current_user.family_code
    ).first()
    if not family:
        raise HTTPException(404, "Family not found")

    # ---------------- MONTHLY RECORD ----------------
    now = datetime.utcnow()
    monthly = (
        db.query(FamilyMonthly)
        .filter(
            FamilyMonthly.family_id == family.id,
            FamilyMonthly.year == now.year,
            FamilyMonthly.month == now.month
        )
        .first()
    )
    if not monthly:
        raise HTTPException(404, "Monthly record not set")

    # ---------------- CATEGORY USAGE ----------------
    categories = []
    total_spent = 0

    for cat in CATEGORIES:
        name = cat["name"]

        # Load saved budget
        row = db.query(CategoryBudget).filter(
            CategoryBudget.family_code == family.family_code,
            CategoryBudget.category_name == name
        ).first()

        budget = row.budget if row else 0

        # Calculate spending for current month
        spent = (
            db.query(func.sum(ExpenseDB.amount))
            .filter(
                ExpenseDB.family_code == family.family_code,
                ExpenseDB.category == name,
                extract("year", ExpenseDB.created_at) == now.year,
                extract("month", ExpenseDB.created_at) == now.month
            )
            .scalar()
            or 0
        )

        total_spent += spent

        categories.append({
            "name": name,
            "icon": cat["icon"],
            "budget": budget,
            "spent": spent,
            "remaining": max(budget - spent, 0),
            "percentage_used": round((spent / budget) * 100, 2) if budget > 0 else 0
        })

    # ---------------- STATIC PREDICTIONS (PLACEHOLDER) ----------------
    STATIC_PREDICTIONS = {
        "Groceries":     {"predicted": 28500, "change": -5},
        "Food":          {"predicted": 12000, "change": 3},
        "Transport":     {"predicted": 7500,  "change": 4},
        "Health":        {"predicted": 9000,  "change": -2},
        "Gifts":         {"predicted": 6500,  "change": 1},
        "Rent":          {"predicted": 30000, "change": 0},
        "Utilities":     {"predicted": 8000,  "change": 2},
        "Entertainment": {"predicted": 15000, "change": 10},
        "Education":     {"predicted": 20000, "change": 7},
        "Insurance":     {"predicted": 11000, "change": -1},
    }

    category_predictions = []
    for cat in categories:
        pred = STATIC_PREDICTIONS.get(cat["name"], {"predicted": 0, "change": 0})
        category_predictions.append({
            "name": cat["name"],
            "current": cat["budget"],
            "predicted": pred["predicted"],
            "percentage_change": pred["change"],
            "icon": cat["icon"]
        })

    # ---------------- CONSTANT PREDICTED TOTAL ----------------
    predicted_total_budget = 42500

    # ---------------- FINAL RESPONSE ----------------
    return {
        "status": True,
        "message": "Budget insights loaded",

        "predicted_total_budget": predicted_total_budget,
        "category_predictions": category_predictions,

        "monthly_budget": {
            "budget": monthly.monthly_budget,
            "spent": total_spent,
            "remaining": max(monthly.monthly_budget - total_spent, 0)
        },

        "categories": categories
    }