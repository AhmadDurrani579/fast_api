from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends
from jose import jwt, JWTError
from app.core.config import settings
from app.services.openai_service import OpenAIService
from sqlalchemy.orm import Session
from app.db.database import SessionLocal
from app.db.models_family import Family, FamilyMonthly
from app.db.categories_budget import CategoryBudget
from app.db.models_expenses import ExpenseDB
from app.services.date_extractor import DateExtractor
from datetime import datetime
import calendar
from app.db.models import UserUsage
from app.db.models_chat import ChatMessage
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

def get_category_budgets(db: Session, family_code: str, year: int, month: int) -> list[dict]:
    """
    Returns per-category budget + spent for a given month.
    spent is read directly from category_budgets.spent
    (kept in sync whenever an expense is logged).
    """
    budgets = db.query(CategoryBudget).filter(
        CategoryBudget.family_code == family_code,
        CategoryBudget.month == month,
        CategoryBudget.year == year
    ).all()

    result = []
    for b in budgets:
        budget_amt = float(b.budget or 0.0)
        spent_amt  = float(b.spent  or 0.0)
        remaining  = budget_amt - spent_amt
        pct_used   = round((spent_amt / budget_amt * 100), 1) if budget_amt > 0 else 0.0

        result.append({
            "category":     b.category_name,
            "budget":       budget_amt,
            "spent":        spent_amt,
            "remaining":    remaining,
            "percent_used": pct_used,
            "overspent":    spent_amt > budget_amt,
            "scope":        b.scope,
            "owner_id":     b.owner_id,
        })

    return result


def get_previous_months_data(
    db: Session,
    family_id: int,
    base_year: int,
    base_month: int,
    n: int = 3
) -> list[dict]:
    """
    Returns up to n previous months of family_monthly records
    before base_month, ordered most recent first.
    """
    records = (
        db.query(FamilyMonthly)
        .filter(FamilyMonthly.family_id == family_id)
        .order_by(FamilyMonthly.year.desc(), FamilyMonthly.month.desc())
        .all()
    )

    results = []
    for r in records:
        if (r.year, r.month) >= (base_year, base_month):
            continue
        results.append({
            "month":            r.month,
            "year":             r.year,
            "monthly_income":   float(r.monthly_income),
            "monthly_budget":   float(r.monthly_budget),
            "starting_balance": float(r.starting_balance),
            "closing_balance":  float(r.closing_balance),
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

def resolve_target_month(
    message: str,
    latest_month: FamilyMonthly,
    date_extractor
) -> tuple[int, int, int]:
    """
    Returns (target_month, target_year, month_diff).
    month_diff > 0 → future | 0 → current | < 0 → past
    """
    lower = message.lower()

    if "next month" in lower:
        m, y = latest_month.month + 1, latest_month.year
        if m == 13:
            m, y = 1, y + 1
        return m, y, 1

    if "last month" in lower or "previous month" in lower:
        m, y = latest_month.month - 1, latest_month.year
        if m == 0:
            m, y = 12, y - 1
        return m, y, -1

    if "this month" in lower or "current month" in lower:
        return latest_month.month, latest_month.year, 0

    extracted = date_extractor.extract_month_year(message)
    t_month = extracted.get("month") or latest_month.month
    t_year  = extracted.get("year")  or latest_month.year
    if t_year < latest_month.year:
        t_year = latest_month.year

    diff = (t_year - latest_month.year) * 12 + (t_month - latest_month.month)
    return t_month, t_year, diff


# ─────────────────────────────────────────────
# WEBSOCKET SENDER
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
            #  Save user message

            save_chat(db, user_id, "user", user_message)
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

            # ── Greeting — no usage count ──
            if intent == "greeting":

                greeting_message = (
                    "Hello! I'm FinanceAI, your personal finance assistant 💰\n\n"
                    "I can help you with:\n"
                    "• Your monthly budget breakdown\n"
                    "• Spending predictions for next month\n"
                    "• Tips to control and reduce your expenses\n\n"
                    "What would you like to know?"
                )
                save_chat(db, user_id, "assistant", greeting_message)
                await websocket.send_json({
                    "type": "assistant_message",
                    "allowed": True,
                    "content": greeting_message,
                    "used_requests": usage.request_count,
                    "remaining_requests": max(MAX_FREE_REQUESTS - usage.request_count, 0),
                    "is_paid": usage.is_paid
                })

                continue
            # ── General non-finance chat ──
            if intent == "general":
                ai_reply = ai.chat_with_context(user_message=user_message, finance_data=None)
                save_chat(db, user_id, "assistant", ai_reply)
                
                await send_and_count(websocket, db, usage, ai_reply)
                continue

            # ── Load family ──
            family = db.query(Family).filter(Family.head_id == user_id).first()
            if not family:
                await send_and_count(
                    websocket, db, usage,
                    "No family account found. Please set up your family profile first."
                )
                continue

            # ── Load latest monthly record ──
            latest_month = (
                db.query(FamilyMonthly)
                .filter(FamilyMonthly.family_id == family.id)
                .order_by(FamilyMonthly.year.desc(), FamilyMonthly.month.desc())
                .first()
            )

            if not latest_month:
                await send_and_count(
                    websocket, db, usage,
                    "No monthly financial data found. Please add your income and budget for this month first."
                )
                continue

            # ── Resolve target month ──
            target_month, target_year, month_diff = resolve_target_month(
                user_message, latest_month, date_extractor
            )

            # ═══════════════════════════════════════════════
            # INTENT: SPENDING CONTROL & ADVICE
            # ═══════════════════════════════════════════════
            if intent == "spending_control":
                cat_budgets    = get_category_budgets(db, family.family_code, latest_month.year, latest_month.month)
                total_expenses = sum(c["spent"] for c in cat_budgets)
                total_budget   = float(latest_month.monthly_budget)
                savings        = float(latest_month.monthly_income) - total_expenses

                finance_context = {
                    "intent":             "spending_control",
                    "month":              latest_month.month,
                    "year":               latest_month.year,
                    "monthly_income":     float(latest_month.monthly_income),
                    "monthly_budget":     total_budget,
                    "total_expenses":     total_expenses,
                    "remaining_budget":   total_budget - total_expenses,
                    "savings":            savings,
                    "opening_balance":    float(latest_month.starting_balance),
                    "closing_balance":    float(latest_month.closing_balance),
                    "category_breakdown": cat_budgets,
                }

                ai_reply = ai.chat_with_context(user_message=user_message, finance_data=finance_context)
                save_chat(db, user_id, "assistant", ai_reply)

                await send_and_count(websocket, db, usage, ai_reply)
                continue

            # ═══════════════════════════════════════════════
            # INTENT: PREDICTION (future month)
            # ═══════════════════════════════════════════════
            if intent == "prediction" or month_diff > 0:
                current_cat_budgets    = get_category_budgets(db, family.family_code, latest_month.year, latest_month.month)
                current_total_expenses = sum(c["spent"] for c in current_cat_budgets)
                current_savings        = float(latest_month.monthly_income) - current_total_expenses

                prev_months = get_previous_months_data(
                    db, family.id,
                    latest_month.year, latest_month.month,
                    n=3
                )

                finance_context = {
                    "intent":             "prediction",
                    "target_month":       target_month,
                    "target_year":        target_year,
                    "months_ahead":       max(month_diff, 1),
                    "current_month":      latest_month.month,
                    "current_year":       latest_month.year,
                    "monthly_income":     float(latest_month.monthly_income),
                    "monthly_budget":     float(latest_month.monthly_budget),
                    "total_expenses":     current_total_expenses,
                    "current_savings":    current_savings,
                    "closing_balance":    float(latest_month.closing_balance),
                    "previous_months":    prev_months,
                    "category_breakdown": current_cat_budgets,
                }

                ai_reply = ai.chat_with_context(user_message=user_message, finance_data=finance_context)
                save_chat(db, user_id, "assistant", ai_reply)

                await send_and_count(websocket, db, usage, ai_reply)
                continue

            # ═══════════════════════════════════════════════
            # INTENT: BUDGET LOOKUP (past / current month)
            # ═══════════════════════════════════════════════
            target_data = (
                db.query(FamilyMonthly)
                .filter(
                    FamilyMonthly.family_id == family.id,
                    FamilyMonthly.year  == target_year,
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

            cat_budgets    = get_category_budgets(db, family.family_code, target_year, target_month)
            total_expenses = sum(c["spent"] for c in cat_budgets)

            finance_context = {
                "intent":             "budget_lookup",
                "month":              target_data.month,
                "year":               target_data.year,
                "opening_balance":    float(target_data.starting_balance),
                "monthly_income":     float(target_data.monthly_income),
                "monthly_budget":     float(target_data.monthly_budget),
                "closing_balance":    float(target_data.closing_balance),
                "total_expenses":     total_expenses,
                "remaining_budget":   float(target_data.monthly_budget) - total_expenses,
                "savings":            float(target_data.monthly_income) - total_expenses,
                "category_breakdown": cat_budgets,
            }

            ai_reply = ai.chat_with_context(user_message=user_message, finance_data=finance_context)
            save_chat(db, user_id, "assistant", ai_reply)

            await send_and_count(websocket, db, usage, ai_reply)

    except WebSocketDisconnect:
        pass

    finally:
        db.close()
    

def save_chat(db: Session, user_id: int, role: str, message: str):
        chat = ChatMessage(
            user_id=user_id,
            role=role,
            message=message
        )

        db.add(chat)
        db.commit()

@router.get("/history")
def get_chat_history(
    current_user: UserDB = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    chats = (
        db.query(ChatMessage)
        .filter(ChatMessage.user_id == current_user.id)
        .order_by(ChatMessage.created_at.asc())
        .all()
    )

    response = []

    for chat in chats:
        response.append({
            "id": chat.id,
            "role": chat.role,
            "message": chat.message,
            "created_at": chat.created_at
        })

    return {
        "status": True,
        "messages": response
    }