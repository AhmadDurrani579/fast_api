from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from jose import jwt, JWTError
from app.core.config import settings
from app.services.openai_service import OpenAIService
from sqlalchemy.orm import Session
from app.db.database import SessionLocal
from app.db.models_family import Family, FamilyMonthly, CategoryBudget
from app.db.models_expenses import ExpenseDB
from app.services.date_extractor import DateExtractor
from datetime import datetime
import calendar
from app.db.models import UserUsage
from collections import defaultdict

router = APIRouter()
ai = OpenAIService()
date_extractor = DateExtractor()

MAX_FREE_REQUESTS = 3


# ─────────────────────────────────────────────
# AUTH
# ─────────────────────────────────────────────

def verify_jwt(token: str):
    try:
        return jwt.decode(
            token,
            settings.JWT_SECRET,
            algorithms=[settings.JWT_ALGORITHM]
        )
    except JWTError:
        return None


# ─────────────────────────────────────────────
# USAGE TRACKING
# ─────────────────────────────────────────────

def get_or_create_usage(db: Session, user_id: int) -> UserUsage:
    now = datetime.utcnow()
    usage = db.query(UserUsage).filter(UserUsage.user_id == user_id).first()

    if not usage:
        usage = UserUsage(
            user_id=user_id,
            request_count=0,
            is_paid=False,
            plan_type="free",
            month=now.month,
            year=now.year
        )
        db.add(usage)
        db.commit()
        db.refresh(usage)

    # Reset monthly counter if new month
    if usage.month != now.month or usage.year != now.year:
        usage.request_count = 0
        usage.is_paid = False
        usage.plan_type = "free"
        usage.month = now.month
        usage.year = now.year
        db.commit()
        db.refresh(usage)

    return usage


def increment_usage(db: Session, usage: UserUsage):
    usage.request_count += 1
    db.commit()
    db.refresh(usage)


# ─────────────────────────────────────────────
# DB HELPERS
# ─────────────────────────────────────────────

def get_month_expenses(db: Session, family_code: str, year: int, month: int) -> float:
    """Total expenses for a family in a given month."""
    last_day = calendar.monthrange(year, month)[1]
    start_date = datetime(year, month, 1)
    end_date = datetime(year, month, last_day, 23, 59, 59)

    expenses = db.query(ExpenseDB).filter(
        ExpenseDB.family_code == family_code,
        ExpenseDB.created_at >= start_date,
        ExpenseDB.created_at <= end_date
    ).all()

    return sum(e.amount for e in expenses)


def get_expenses_by_category(db: Session, family_code: str, year: int, month: int) -> dict:
    """
    Returns per-category total spending for a given month.
    e.g. {"Groceries": 12000, "Transport": 5000, ...}
    Assumes ExpenseDB has a `category` field.
    """
    last_day = calendar.monthrange(year, month)[1]
    start_date = datetime(year, month, 1)
    end_date = datetime(year, month, last_day, 23, 59, 59)

    expenses = db.query(ExpenseDB).filter(
        ExpenseDB.family_code == family_code,
        ExpenseDB.created_at >= start_date,
        ExpenseDB.created_at <= end_date
    ).all()

    category_totals = defaultdict(float)
    for e in expenses:
        cat = getattr(e, "category", "Uncategorised") or "Uncategorised"
        category_totals[cat] += e.amount

    return dict(category_totals)


def get_category_budgets(db: Session, family_code: str, year: int, month: int) -> list[dict]:
    """
    Returns list of category budgets for a given month.
    e.g. [{"category": "Groceries", "budget": 15000, "scope": "family"}, ...]
    """
    budgets = db.query(CategoryBudget).filter(
        CategoryBudget.family_code == family_code,
        CategoryBudget.month == month,
        CategoryBudget.year == year
    ).all()

    return [
        {
            "category": b.category_name,
            "budget": float(b.budget),
            "scope": b.scope,
        }
        for b in budgets
    ]


def get_previous_months_data(db: Session, family_id: int, base_year: int, base_month: int, n: int = 3) -> list[dict]:
    """
    Returns up to `n` previous months of family_monthly data before the given month.
    Used for prediction averaging.
    """
    records = (
        db.query(FamilyMonthly)
        .filter(FamilyMonthly.family_id == family_id)
        .order_by(FamilyMonthly.year.desc(), FamilyMonthly.month.desc())
        .all()
    )

    results = []
    for r in records:
        # Skip current or future months
        if (r.year, r.month) >= (base_year, base_month):
            continue
        results.append({
            "month": r.month,
            "year": r.year,
            "monthly_income": float(r.monthly_income),
            "monthly_budget": float(r.monthly_budget),
            "starting_balance": float(r.starting_balance),
            "closing_balance": float(r.closing_balance),
        })
        if len(results) >= n:
            break

    return results


# ─────────────────────────────────────────────
# INTENT DETECTION
# ─────────────────────────────────────────────

GREETING_WORDS = {"hi", "hello", "hey", "salam", "assalamualaikum"}

FINANCE_KEYWORDS = [
    "budget", "spend", "spent", "income", "expense", "expenses",
    "saving", "savings", "balance", "month", "monthly",
    "march", "april", "february", "january", "may", "june",
    "july", "august", "september", "october", "november", "december",
    "previous month", "last month", "this month", "next month",
    "predict", "predicted", "forecast", "control", "reduce", "cut",
    "overspend", "overspending", "category", "categories", "groceries",
    "transport", "utilities", "food", "bills", "how to save"
]

SPENDING_CONTROL_KEYWORDS = [
    "control", "reduce", "cut", "overspend", "overspending",
    "how to save", "spending habits", "where am i spending",
    "too much", "control my spending", "manage", "improve",
    "suggestion", "advice", "tip", "tips", "help me save"
]

PREDICTION_KEYWORDS = [
    "predict", "predicted", "forecast", "next month",
    "will my budget", "what will", "estimate", "projection"
]


def detect_intent(message: str) -> str:
    """
    Returns: 'greeting' | 'spending_control' | 'prediction' | 'budget_lookup' | 'general'
    """
    lower = message.lower()
    words = lower.split()

    if words and words[0] in GREETING_WORDS and len(words) <= 3:
        return "greeting"

    if any(kw in lower for kw in SPENDING_CONTROL_KEYWORDS):
        return "spending_control"

    if any(kw in lower for kw in PREDICTION_KEYWORDS):
        return "prediction"

    if any(kw in lower for kw in FINANCE_KEYWORDS):
        return "budget_lookup"

    return "general"


# ─────────────────────────────────────────────
# TARGET MONTH RESOLVER
# ─────────────────────────────────────────────

def resolve_target_month(message: str, latest_month: FamilyMonthly, date_extractor) -> tuple[int, int, int]:
    """
    Returns (target_month, target_year, month_diff_from_latest).
    month_diff > 0 → future, 0 → current, < 0 → past
    """
    lower = message.lower()

    if "next month" in lower:
        m = latest_month.month + 1
        y = latest_month.year
        if m == 13:
            m = 1
            y += 1
        return m, y, 1

    if "last month" in lower or "previous month" in lower:
        m = latest_month.month - 1
        y = latest_month.year
        if m == 0:
            m = 12
            y -= 1
        return m, y, -1

    if "this month" in lower or "current month" in lower:
        return latest_month.month, latest_month.year, 0

    extracted = date_extractor.extract_month_year(message)
    t_month = extracted.get("month") or latest_month.month
    t_year = extracted.get("year") or latest_month.year
    if t_year < latest_month.year:
        t_year = latest_month.year

    diff = (t_year - latest_month.year) * 12 + (t_month - latest_month.month)
    return t_month, t_year, diff


# ─────────────────────────────────────────────
# WEBSOCKET SENDER (with usage tracking)
# ─────────────────────────────────────────────

async def send_and_count(
    websocket: WebSocket,
    db: Session,
    usage: UserUsage,
    content: str
):
    await websocket.send_json({
        "type": "assistant_message",
        "allowed": True,
        "content": content,
        "used_requests": usage.request_count + 1,
        "remaining_requests": max(MAX_FREE_REQUESTS - (usage.request_count + 1), 0),
        "is_paid": usage.is_paid
    })

    if not usage.is_paid:
        increment_usage(db, usage)


# ─────────────────────────────────────────────
# WEBSOCKET ENDPOINT
# ─────────────────────────────────────────────

@router.websocket("/ws/chat")
async def chat_socket(websocket: WebSocket):

    # ── Auth ──
    token = websocket.query_params.get("token")
    if not token:
        await websocket.close(code=1008)
        return

    user = verify_jwt(token.strip())
    if not user:
        await websocket.close(code=1008)
        return

    user_id = user.get("id")
    if not user_id:
        await websocket.close(code=1008)
        return

    await websocket.accept()
    db: Session = SessionLocal()

    try:
        while True:
            data = await websocket.receive_json()

            # ── Validate payload ──
            if "content" not in data or not str(data["content"]).strip():
                await websocket.send_json({"type": "error", "message": "Invalid payload"})
                continue

            user_message = str(data["content"]).strip()
            usage = get_or_create_usage(db, user_id)

            print(f"[Chat] user_id={user_id} | count={usage.request_count} | paid={usage.is_paid}")

            # ── Usage gate ──
            if not usage.is_paid and usage.request_count >= MAX_FREE_REQUESTS:
                await websocket.send_json({
                    "type": "limit_reached",
                    "allowed": False,
                    "message": "You've used your 3 free messages this month. Upgrade to Pro for unlimited access.",
                    "used_requests": usage.request_count,
                    "remaining_requests": 0,
                    "is_paid": usage.is_paid
                })
                continue

            # ── Intent detection ──
            intent = detect_intent(user_message)

            # ── Greeting (no usage count) ──
            if intent == "greeting":
                await websocket.send_json({
                    "type": "assistant_message",
                    "allowed": True,
                    "content": "Hello! I'm FinanceAI, your personal finance assistant 💰\n\nI can help you with:\n• Your monthly budget breakdown\n• Spending predictions\n• Tips to control your expenses\n\nWhat would you like to know?",
                    "used_requests": usage.request_count,
                    "remaining_requests": max(MAX_FREE_REQUESTS - usage.request_count, 0),
                    "is_paid": usage.is_paid
                })
                continue

            # ── Non-finance general chat ──
            if intent == "general":
                ai_reply = ai.chat_with_context(user_message=user_message, finance_data=None)
                await send_and_count(websocket, db, usage, ai_reply)
                continue

            # ── Load family ──
            family = db.query(Family).filter(Family.head_id == user_id).first()
            if not family:
                await send_and_count(websocket, db, usage, "No family account found. Please set up your family profile first.")
                continue

            # ── Load latest monthly record ──
            latest_month = (
                db.query(FamilyMonthly)
                .filter(FamilyMonthly.family_id == family.id)
                .order_by(FamilyMonthly.year.desc(), FamilyMonthly.month.desc())
                .first()
            )

            if not latest_month:
                await send_and_count(websocket, db, usage, "No monthly financial data found. Please add your income and budget for this month first.")
                continue

            # ── Resolve target month ──
            target_month, target_year, month_diff = resolve_target_month(
                user_message, latest_month, date_extractor
            )

            # ═══════════════════════════════════════
            # INTENT: SPENDING CONTROL & ADVICE
            # ═══════════════════════════════════════
            if intent == "spending_control":
                # Use current/latest month for analysis
                analysis_month = latest_month.month
                analysis_year = latest_month.year

                cat_budgets = get_category_budgets(db, family.family_code, analysis_year, analysis_month)
                cat_expenses = get_expenses_by_category(db, family.family_code, analysis_year, analysis_month)
                total_expenses = sum(cat_expenses.values())
                total_budget = float(latest_month.monthly_budget)

                # Build per-category comparison
                category_breakdown = []
                for cb in cat_budgets:
                    spent = cat_expenses.get(cb["category"], 0.0)
                    remaining = cb["budget"] - spent
                    pct_used = (spent / cb["budget"] * 100) if cb["budget"] > 0 else 0
                    category_breakdown.append({
                        "category": cb["category"],
                        "budget": cb["budget"],
                        "spent": spent,
                        "remaining": remaining,
                        "percent_used": round(pct_used, 1),
                        "overspent": spent > cb["budget"],
                        "scope": cb["scope"]
                    })

                # Also include categories with expenses but no budget set
                budgeted_cats = {cb["category"] for cb in cat_budgets}
                for cat, spent in cat_expenses.items():
                    if cat not in budgeted_cats:
                        category_breakdown.append({
                            "category": cat,
                            "budget": 0,
                            "spent": spent,
                            "remaining": -spent,
                            "percent_used": 100,
                            "overspent": True,
                            "scope": "unbudgeted"
                        })

                finance_context = {
                    "intent": "spending_control",
                    "year": analysis_year,
                    "month": analysis_month,
                    "monthly_income": float(latest_month.monthly_income),
                    "monthly_budget": total_budget,
                    "total_expenses": total_expenses,
                    "remaining_budget": total_budget - total_expenses,
                    "savings": float(latest_month.monthly_income) - total_expenses,
                    "category_breakdown": category_breakdown,
                    "opening_balance": float(latest_month.starting_balance),
                    "closing_balance": float(latest_month.closing_balance),
                }

                ai_reply = ai.chat_with_context(
                    user_message=user_message,
                    finance_data=finance_context
                )
                await send_and_count(websocket, db, usage, ai_reply)
                continue

            # ═══════════════════════════════════════
            # INTENT: PREDICTION (future month)
            # ═══════════════════════════════════════
            if intent == "prediction" or month_diff > 0:
                # Gather last 3 months for averaging
                prev_months = get_previous_months_data(
                    db, family.id,
                    latest_month.year, latest_month.month,
                    n=3
                )

                current_total_expenses = get_month_expenses(
                    db, family.family_code,
                    latest_month.year, latest_month.month
                )
                current_savings = float(latest_month.monthly_income) - current_total_expenses
                current_cat_budgets = get_category_budgets(
                    db, family.family_code,
                    latest_month.year, latest_month.month
                )
                current_cat_expenses = get_expenses_by_category(
                    db, family.family_code,
                    latest_month.year, latest_month.month
                )

                finance_context = {
                    "intent": "prediction",
                    "target_month": target_month,
                    "target_year": target_year,
                    "months_ahead": max(month_diff, 1),
                    "current_month": latest_month.month,
                    "current_year": latest_month.year,
                    "monthly_income": float(latest_month.monthly_income),
                    "monthly_budget": float(latest_month.monthly_budget),
                    "total_expenses": current_total_expenses,
                    "current_savings": current_savings,
                    "closing_balance": float(latest_month.closing_balance),
                    "previous_months": prev_months,
                    "category_budgets": current_cat_budgets,
                    "category_expenses": current_cat_expenses,
                }

                ai_reply = ai.chat_with_context(
                    user_message=user_message,
                    finance_data=finance_context
                )
                await send_and_count(websocket, db, usage, ai_reply)
                continue

            # ═══════════════════════════════════════
            # INTENT: BUDGET LOOKUP (past/current month)
            # ═══════════════════════════════════════
            target_data = (
                db.query(FamilyMonthly)
                .filter(
                    FamilyMonthly.family_id == family.id,
                    FamilyMonthly.year == target_year,
                    FamilyMonthly.month == target_month
                )
                .first()
            )

            if not target_data:
                await send_and_count(
                    websocket, db, usage,
                    f"No financial data found for {calendar.month_name[target_month]} {target_year}. "
                    f"Please make sure the family head has set the budget for that month."
                )
                continue

            total_expenses = get_month_expenses(db, family.family_code, target_year, target_month)
            cat_budgets = get_category_budgets(db, family.family_code, target_year, target_month)
            cat_expenses = get_expenses_by_category(db, family.family_code, target_year, target_month)

            # Build per-category breakdown
            category_breakdown = []
            for cb in cat_budgets:
                spent = cat_expenses.get(cb["category"], 0.0)
                remaining = cb["budget"] - spent
                pct_used = (spent / cb["budget"] * 100) if cb["budget"] > 0 else 0
                category_breakdown.append({
                    "category": cb["category"],
                    "budget": cb["budget"],
                    "spent": spent,
                    "remaining": remaining,
                    "percent_used": round(pct_used, 1),
                    "overspent": spent > cb["budget"],
                    "scope": cb["scope"]
                })

            finance_context = {
                "intent": "budget_lookup",
                "year": target_data.year,
                "month": target_data.month,
                "opening_balance": float(target_data.starting_balance),
                "monthly_income": float(target_data.monthly_income),
                "monthly_budget": float(target_data.monthly_budget),
                "closing_balance": float(target_data.closing_balance),
                "total_expenses": total_expenses,
                "remaining_budget": float(target_data.monthly_budget) - total_expenses,
                "savings": float(target_data.monthly_income) - total_expenses,
                "category_breakdown": category_breakdown,
            }

            ai_reply = ai.chat_with_context(
                user_message=user_message,
                finance_data=finance_context
            )
            await send_and_count(websocket, db, usage, ai_reply)

    except WebSocketDisconnect:
        pass

    finally:
        db.close()