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

    # Check token from query parameters
    token = websocket.query_params.get("token")
    if not token:
        await websocket.close(code=1008)
        return

    token = token.strip()
    user = verify_jwt(token)

    # If token invalid or expired, close connection
    if not user:
        await websocket.close(code=1008)
        return

    # Accept connection after authentication
    await websocket.accept()
    user_id = user.get("id")
    print(f"WebSocket connected | user_id={user_id}")

    # Open database session for this connection
    db: Session = SessionLocal()

    try:
        while True:

            # Wait for message from frontend
            data = await websocket.receive_json()

            if "content" not in data:
                await websocket.send_json({
                    "type": "error",
                    "message": "Invalid payload"
                })
                continue

            user_message = data["content"].strip()
            lower_message = user_message.lower()

            # -------------------------------------------------
            # Simple greeting handling (no DB or AI needed)
            # -------------------------------------------------
            greetings = ["hi", "hello", "hey"]

            words = lower_message.split()
            if words and words[0] in greetings:
                await websocket.send_json({
                    "type": "assistant_message",
                    "content": "Hello! I'm your finance assistant. How can I help you today?"
                })
                continue

            # -------------------------------------------------
            # Check if message is finance-related
            # -------------------------------------------------
            finance_keywords = [
                "budget", "spend", "income",
                "expenses", "saving", "balance"
            ]

            requires_finance_data = any(
                word in lower_message for word in finance_keywords
            )

            # If not finance-related → just forward to AI normally
            if not requires_finance_data:
                ai_reply = ai.chat_with_context(
                    user_message=user_message,
                    finance_data=None
                )

                await websocket.send_json({
                    "type": "assistant_message",
                    "content": ai_reply
                })
                continue

            # -------------------------------------------------
            # Extract month and year from user message
            # -------------------------------------------------
            month_data = date_extractor.extract_month_year(user_message)
            year = month_data["year"]
            month = month_data["month"]

            # Get family where this user is the head
            family = db.query(Family).filter(
                Family.head_id == user_id
            ).first()

            if not family:
                await websocket.send_json({
                    "type": "assistant_message",
                    "content": "No family data found."
                })
                continue
            # -------------------------------------------------
            # Try to get requested month first
            # -------------------------------------------------
            requested_year = year
            requested_month = month

            monthly = None

            # If user specified a month/year
            if requested_year and requested_month:
                monthly = db.query(FamilyMonthly).filter(
                    FamilyMonthly.family_id == family.id,
                    FamilyMonthly.year == requested_year,
                    FamilyMonthly.month == requested_month
                ).first()

            # Always get latest available month (base reference)
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


            # -------------------------------------------------
            # If exact month exists → use it
            # -------------------------------------------------
            if monthly:

                base_month = monthly

            else:
                # If requested month doesn't exist,
                # we predict forward from latest month

                base_month = latest_month

                # If user didn't specify month, just use latest
                if not requested_year or not requested_month:
                    requested_year = base_month.year
                    requested_month = base_month.month

                # Calculate month difference
                month_diff = (
                    (requested_year - base_month.year) * 12 +
                    (requested_month - base_month.month)
                )

                # If user asks for past month that doesn't exist
                if month_diff < 0:
                    await websocket.send_json({
                        "type": "assistant_message",
                        "content": "I don't have historical data for that month."
                    })
                    continue

                # Predict forward month-by-month
                predicted_budget = base_month.monthly_budget
                predicted_balance = base_month.closing_balance

                # Calculate expenses for base month
                last_day = calendar.monthrange(
                    base_month.year,
                    base_month.month
                )[1]

                start_date = datetime(base_month.year, base_month.month, 1)
                end_date = datetime(base_month.year, base_month.month, last_day, 23, 59, 59)

                expenses = db.query(ExpenseDB).filter(
                    ExpenseDB.family_code == family.family_code,
                    ExpenseDB.created_at >= start_date,
                    ExpenseDB.created_at <= end_date
                ).all()

                total_expenses = sum(e.amount for e in expenses)

                savings = base_month.monthly_income - total_expenses

                for _ in range(month_diff):
                    predicted_budget += (0.05 * savings)
                    predicted_balance += savings

                await websocket.send_json({
                    "type": "assistant_message",
                    "content": f"""
            Your predicted budget for {requested_month}/{requested_year} is PKR {predicted_budget}.
            Your predicted opening balance will be PKR {predicted_balance}.
            """
                })
                continue


            # -------------------------------------------------
            # If exact month exists → normal structured AI flow
            # -------------------------------------------------

            last_day = calendar.monthrange(
                base_month.year,
                base_month.month
            )[1]

            start_date = datetime(base_month.year, base_month.month, 1)
            end_date = datetime(base_month.year, base_month.month, last_day, 23, 59, 59)

            expenses = db.query(ExpenseDB).filter(
                ExpenseDB.family_code == family.family_code,
                ExpenseDB.created_at >= start_date,
                ExpenseDB.created_at <= end_date
            ).all()

            total_expenses = sum(e.amount for e in expenses)

            finance_context = {
                "year": base_month.year,
                "month": base_month.month,
                "opening_balance": base_month.starting_balance,
                "monthly_income": base_month.monthly_income,
                "monthly_budget": base_month.monthly_budget,
                "closing_balance": base_month.closing_balance,
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

    except WebSocketDisconnect:
        print(f"WebSocket disconnected | user_id={user_id}")
    finally:
        db.close()