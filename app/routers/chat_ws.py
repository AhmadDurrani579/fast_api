from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from jose import jwt, JWTError
from app.core.config import settings
from app.services.openai_service import OpenAIService
from sqlalchemy.orm import Session
from app.db.database import SessionLocal
from app.db.models_family import Family, FamilyMonthly
from app.db.models_expenses import ExpenseDB
from app.services.date_extractor import DateExtractor
from datetime import datetime
import calendar
from app.db.models import UserUsage


router = APIRouter()
ai = OpenAIService()
date_extractor = DateExtractor()

MAX_FREE_REQUESTS = 3


def verify_jwt(token: str):
    try:
        return jwt.decode(
            token,
            settings.JWT_SECRET,
            algorithms=[settings.JWT_ALGORITHM]
        )
    except JWTError:
        return None


def get_or_create_usage(db: Session, user_id: int):
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


def get_month_expenses(db: Session, family_code: str, year: int, month: int):
    last_day = calendar.monthrange(year, month)[1]

    start_date = datetime(year, month, 1)
    end_date = datetime(year, month, last_day, 23, 59, 59)

    expenses = db.query(ExpenseDB).filter(
        ExpenseDB.family_code == family_code,
        ExpenseDB.created_at >= start_date,
        ExpenseDB.created_at <= end_date
    ).all()

    return sum(e.amount for e in expenses)


async def send_and_count(websocket: WebSocket, db: Session, usage: UserUsage, content: str):
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


@router.websocket("/ws/chat")
async def chat_socket(websocket: WebSocket):

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

            if "content" not in data or not str(data["content"]).strip():
                await websocket.send_json({
                    "type": "error",
                    "message": "Invalid payload"
                })
                continue

            user_message = str(data["content"]).strip()
            lower_message = user_message.lower()

            usage = get_or_create_usage(db, user_id)

            print("Count:", usage.request_count, "Paid:", usage.is_paid)

            if not usage.is_paid and usage.request_count >= MAX_FREE_REQUESTS:
                await websocket.send_json({
                    "type": "limit_reached",
                    "allowed": False,
                    "message": "Free limit reached. Please upgrade.",
                    "used_requests": usage.request_count,
                    "remaining_requests": 0,
                    "is_paid": usage.is_paid
                })
                continue

            greetings = ["hi", "hello", "hey", "salam", "assalamualaikum"]
            words = lower_message.split()

            if words and words[0] in greetings and len(words) <= 3:
                await websocket.send_json({
                    "type": "assistant_message",
                    "allowed": True,
                    "content": "Hello! I'm your finance assistant. How can I help you today?",
                    "used_requests": usage.request_count,
                    "remaining_requests": max(MAX_FREE_REQUESTS - usage.request_count, 0),
                    "is_paid": usage.is_paid
                })
                continue

            finance_keywords = [
                "budget", "spend", "spent", "income", "expense", "expenses",
                "saving", "savings", "balance", "db", "database",
                "month", "monthly", "march", "april", "february",
                "january", "may", "june", "july", "august",
                "september", "october", "november", "december",
                "previous month", "last month", "this month", "next month"
            ]

            requires_finance = any(word in lower_message for word in finance_keywords)

            if not requires_finance:
                ai_reply = ai.chat_with_context(
                    user_message=user_message,
                    finance_data=None
                )
                await send_and_count(websocket, db, usage, ai_reply)
                continue

            family = db.query(Family).filter(
                Family.head_id == user_id
            ).first()

            if not family:
                await send_and_count(
                    websocket,
                    db,
                    usage,
                    "No family data found for your account."
                )
                continue

            latest_month = db.query(FamilyMonthly).filter(
                FamilyMonthly.family_id == family.id
            ).order_by(
                FamilyMonthly.year.desc(),
                FamilyMonthly.month.desc()
            ).first()

            if not latest_month:
                await send_and_count(
                    websocket,
                    db,
                    usage,
                    "No monthly financial data available yet."
                )
                continue

            if "next month" in lower_message:
                target_year = latest_month.year
                target_month = latest_month.month + 1

                if target_month == 13:
                    target_month = 1
                    target_year += 1

                month_diff = 1

            elif "last month" in lower_message or "previous month" in lower_message:
                target_year = latest_month.year
                target_month = latest_month.month - 1

                if target_month == 0:
                    target_month = 12
                    target_year -= 1

                month_diff = -1

            elif "this month" in lower_message or "current month" in lower_message:
                target_year = latest_month.year
                target_month = latest_month.month
                month_diff = 0

            else:
                month_data = date_extractor.extract_month_year(user_message)
                target_month = month_data.get("month")
                target_year = month_data.get("year")
                if not target_month:
                    target_month = latest_month.month
                if not target_year or target_year < latest_month.year:
                    target_year = latest_month.year
                month_diff = (
                    (target_year - latest_month.year) * 12 +
                    (target_month - latest_month.month)
                )
            # Future prediction
            if month_diff > 0:
                latest_total_expenses = get_month_expenses(
                    db,
                    family.family_code,
                    latest_month.year,
                    latest_month.month
                )

                savings = latest_month.monthly_income - latest_total_expenses

                predicted_budget = latest_month.monthly_budget
                predicted_balance = latest_month.closing_balance

                for _ in range(month_diff):
                    predicted_budget += (0.05 * savings)
                    predicted_balance += savings

                await send_and_count(
                    websocket,
                    db,
                    usage,
                    f"Your predicted budget for {target_month}/{target_year} is PKR {predicted_budget:,.0f}. "
                    f"Your predicted opening balance will be PKR {predicted_balance:,.0f}."
                )
                continue

            # Past/current month lookup from DB
            target_data = db.query(FamilyMonthly).filter(
                FamilyMonthly.family_id == family.id,
                FamilyMonthly.year == target_year,
                FamilyMonthly.month == target_month
            ).first()

            if not target_data:
                await send_and_count(
                    websocket,
                    db,
                    usage,
                    f"No financial data is available for {target_month}/{target_year}."
                )
                continue

            total_expenses = get_month_expenses(
                db,
                family.family_code,
                target_data.year,
                target_data.month
            )

            remaining_budget = target_data.monthly_budget - total_expenses
            savings = target_data.monthly_income - total_expenses

            finance_context = {
                "year": target_data.year,
                "month": target_data.month,
                "opening_balance": target_data.starting_balance,
                "monthly_income": target_data.monthly_income,
                "monthly_budget": target_data.monthly_budget,
                "closing_balance": target_data.closing_balance,
                "total_expenses": total_expenses,
                "remaining_budget": remaining_budget,
                "savings": savings
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