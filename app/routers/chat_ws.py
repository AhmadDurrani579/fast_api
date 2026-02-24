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

    # First, check if the client has provided a token in the query params
    token = websocket.query_params.get("token")
    if not token:
        await websocket.close(code=1008)
        return

    token = token.strip()
    user = verify_jwt(token)

    # If token is invalid or expired, close the connection
    if not user:
        await websocket.close(code=1008)
        return

    # Accept the WebSocket connection once authentication succeeds
    await websocket.accept()
    user_id = user.get("id")
    print(f"WebSocket connected | user_id={user_id}")

    # Create a DB session for this WebSocket connection
    db: Session = SessionLocal()

    try:
        while True:

            # Wait for a message from the frontend
            data = await websocket.receive_json()

            # Basic validation to ensure proper message format
            if "content" not in data:
                await websocket.send_json({
                    "type": "error",
                    "message": "Invalid payload"
                })
                continue

            user_message = data["content"].strip()
            lower_message = user_message.lower()

            # Handle simple greetings directly without calling AI or DB
            greetings = ["hi", "hello", "hey"]

            words = lower_message.split()

            if words and words[0] in greetings:
                await websocket.send_json({
                    "type": "assistant_message",
                    "content": "Hello! I'm your finance assistant. How can I help you today?"
                })
                continue
            # Check whether the message is related to finance
            finance_keywords = [
                "budget", "spend", "income",
                "expenses", "saving", "balance"
            ]

            requires_finance_data = any(
                word in lower_message for word in finance_keywords
            )

            # If the message is not finance-related,
            # forward it to the AI without any financial context
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

            # Try to extract month and year from the user's message
            month_data = date_extractor.extract_month_year(user_message)
            year = month_data["year"]
            month = month_data["month"]

            # Retrieve the family record where this user is the head
            family = db.query(Family).filter(
                Family.head_id == user_id
            ).first()

            if not family:
                await websocket.send_json({
                    "type": "assistant_message",
                    "content": "No family data found."
                })
                continue

            # First attempt: get financial data for the requested month
            monthly = db.query(FamilyMonthly).filter(
                FamilyMonthly.family_id == family.id,
                FamilyMonthly.year == year,
                FamilyMonthly.month == month
            ).first()

            # If that month doesn't exist, fallback to the latest available month
            if not monthly:
                monthly = db.query(FamilyMonthly).filter(
                    FamilyMonthly.family_id == family.id
                ).order_by(
                    FamilyMonthly.year.desc(),
                    FamilyMonthly.month.desc()
                ).first()

            # If still nothing found, inform the user
            if not monthly:
                await websocket.send_json({
                    "type": "assistant_message",
                    "content": "No monthly financial data available yet."
                })
                continue

            # Build start and end date range for the selected month
            last_day = calendar.monthrange(monthly.year, monthly.month)[1]

            start_date = datetime(monthly.year, monthly.month, 1)
            end_date = datetime(
                monthly.year,
                monthly.month,
                last_day,
                23, 59, 59
            )

            # Fetch all expenses for that family within the month range
            expenses = db.query(ExpenseDB).filter(
                ExpenseDB.family_code == family.family_code,
                ExpenseDB.created_at >= start_date,
                ExpenseDB.created_at <= end_date
            ).all()

            total_expenses = sum(e.amount for e in expenses)

            # Prepare structured financial data to send into the AI
            finance_context = {
                "year": monthly.year,
                "month": monthly.month,
                "opening_balance": monthly.starting_balance,
                "monthly_income": monthly.monthly_income,
                "monthly_budget": monthly.monthly_budget,
                "closing_balance": monthly.closing_balance,
                "total_expenses": total_expenses
            }

            # Generate AI response using both user message and finance context
            ai_reply = ai.chat_with_context(
                user_message=user_message,
                finance_data=finance_context
            )

            # Send the AI response back to the client
            await websocket.send_json({
                "type": "assistant_message",
                "content": ai_reply
            })

    except WebSocketDisconnect:
        print(f"WebSocket disconnected | user_id={user_id}")
    finally:
        # Make sure DB session is always closed when connection ends
        db.close()