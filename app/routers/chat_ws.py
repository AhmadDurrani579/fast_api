import asyncio
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

def get_or_create_usage(db: Session, user_id: int):
    usage = db.query(UserUsage).filter(UserUsage.user_id == user_id).first()
    if not usage:
        usage = UserUsage(user_id=user_id)
        db.add(usage)
        db.commit()
        db.refresh(usage)
    return usage


router = APIRouter()
ai = OpenAIService()
date_extractor = DateExtractor()


# Simple helper to decode and verify JWT token.
# Returns the payload if valid, otherwise None.
def verify_jwt(token: str):
    try:
        payload = jwt.decode(
            token,
            settings.JWT_SECRET,
            algorithms=[settings.JWT_ALGORITHM]
        )
        return payload
    except JWTError:
        return None


@router.websocket("/ws/chat")
async def chat_socket(websocket: WebSocket):

    token = websocket.query_params.get("token")
    if not token:
        await websocket.close(code=1008)
        return

    token = token.strip()
    user = verify_jwt(token)

    if not user:
        await websocket.close(code=1008)
        return

    await websocket.accept()
    user_id = user.get("id")

    db: Session = SessionLocal()

    MAX_FREE_REQUESTS = 3

    try:
        while True:

            data = await websocket.receive_json()

            if "content" not in data:
                await websocket.send_json({
                    "type": "error",
                    "message": "Invalid payload"
                })
                continue

            user_message = data["content"].strip()

            # 🔹 Get usage
            usage = get_or_create_usage(db, user_id)

            # 🔹 Monthly reset (VERY IMPORTANT)
            now = datetime.utcnow()

            if usage.month != now.month or usage.year != now.year:
                usage.request_count = 0
                usage.is_paid = False
                usage.month = now.month
                usage.year = now.year
                db.commit()

            lower_message = user_message.lower()

            # 🔹 Limit check
            if not usage.is_paid and usage.request_count >= MAX_FREE_REQUESTS:
                await websocket.send_json({
                    "type": "limit_reached",
                    "allowed": False
                })
                continue           
            
            # -------------------------------
            # Greeting handling
            # -------------------------------
            greetings = ["hi", "hello", "hey"]

            words = lower_message.split()
            if words and words[0] in greetings:
                await websocket.send_json({
                    "type": "assistant_message",
                    "content": "Hello! I'm your finance assistant. How can I help you today?"
                })
                continue
                
            # -------------------------------
            # Check finance intent
            # -------------------------------
            finance_keywords = [
                "budget", "spend", "income",
                "expenses", "saving", "balance"
            ]

            requires_finance = any(
                word in lower_message for word in finance_keywords
            )

            if not requires_finance:
                ai_reply = ai.chat_with_context(
                    user_message=user_message,
                    finance_data=None
                )

                await websocket.send_json({
                    "type": "assistant_message",
                    "content": ai_reply
                })
                usage.request_count += 1
                db.commit()
                continue

            # -------------------------------
            # Get family
            # -------------------------------
            family = db.query(Family).filter(
                Family.head_id == user_id
            ).first()

            if not family:
                await websocket.send_json({
                    "type": "assistant_message",
                    "content": "No family data found."
                })
                continue

            # -------------------------------
            # Get latest month
            # -------------------------------
            latest_month = db.query(FamilyMonthly).filter(
                FamilyMonthly.family_id == family.id
            ).order_by(
                FamilyMonthly.year.desc(),
                FamilyMonthly.month.desc()
            ).first()

            if not latest_month:
                await websocket.send_json({
                    "type": "assistant_message",
                    "content": "No monthly financial data available yet."
                })
                continue

            # -------------------------------
            # Handle relative month queries
            # -------------------------------
            if "next month" in lower_message:

                target_year = latest_month.year
                target_month = latest_month.month + 1

                if target_month == 13:
                    target_month = 1
                    target_year += 1

                month_diff = 1

            elif "last month" in lower_message:

                target_year = latest_month.year
                target_month = latest_month.month - 1

                if target_month == 0:
                    target_month = 12
                    target_year -= 1

                month_diff = -1

            elif "this month" in lower_message:

                target_year = latest_month.year
                target_month = latest_month.month
                month_diff = 0

            else:
                # Absolute month request (April 2026)
                month_data = date_extractor.extract_month_year(user_message)
                target_year = month_data["year"]
                target_month = month_data["month"]

                if not target_year or not target_month:
                    target_year = latest_month.year
                    target_month = latest_month.month

                month_diff = (
                    (target_year - latest_month.year) * 12 +
                    (target_month - latest_month.month)
                )

            # -------------------------------
            # If past data not available
            # -------------------------------
            if month_diff < 0:
                await websocket.send_json({
                    "type": "assistant_message",
                    "content": "I don't have historical data for that month."
                })
                continue

            # -------------------------------
            # Calculate savings from latest month
            # -------------------------------
            last_day = calendar.monthrange(
                latest_month.year,
                latest_month.month
            )[1]

            start_date = datetime(latest_month.year, latest_month.month, 1)
            end_date = datetime(
                latest_month.year,
                latest_month.month,
                last_day,
                23, 59, 59
            )

            expenses = db.query(ExpenseDB).filter(
                ExpenseDB.family_code == family.family_code,
                ExpenseDB.created_at >= start_date,
                ExpenseDB.created_at <= end_date
            ).all()

            total_expenses = sum(e.amount for e in expenses)

            savings = latest_month.monthly_income - total_expenses

            # -------------------------------
            # If future month prediction
            # -------------------------------
            if month_diff > 0:

                predicted_budget = latest_month.monthly_budget
                predicted_balance = latest_month.closing_balance

                for _ in range(month_diff):
                    predicted_budget += (0.05 * savings)
                    predicted_balance += savings

                await websocket.send_json({
                    "type": "assistant_message",
                    "content": f"""
Your predicted budget for {target_month}/{target_year} is PKR {predicted_budget}.
Your predicted opening balance will be PKR {predicted_balance}.
"""
                })
                continue

            # -------------------------------
            # Exact month exists → use AI
            # -------------------------------
            finance_context = {
                "year": latest_month.year,
                "month": latest_month.month,
                "opening_balance": latest_month.starting_balance,
                "monthly_income": latest_month.monthly_income,
                "monthly_budget": latest_month.monthly_budget,
                "closing_balance": latest_month.closing_balance,
                "total_expenses": total_expenses
            }

            ai_reply = ai.chat_with_context(
                user_message=user_message,
                finance_data=finance_context
            )

            await websocket.send_json({
                "type": "assistant_message",
                "content": ai_reply
            })
            usage.request_count += 1
            db.commit()
    except WebSocketDisconnect:
        pass

    finally:
        db.close()