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
# ---------------- JWT VERIFY ----------------
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

    # -------------------------
    # 🔐 AUTH
    # -------------------------
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
    print(f"WebSocket connected | user_id={user_id}")

    db: Session = SessionLocal()

    try:
        while True:

            # -------------------------
            # 📩 RECEIVE MESSAGE
            # -------------------------
            data = await websocket.receive_json()

            if "content" not in data:
                await websocket.send_json({
                    "type": "error",
                    "message": "Invalid payload"
                })
                continue

            user_message = data["content"].strip()
            lower_message = user_message.lower()

            # -------------------------
            # 🟢 GREETING DETECTION
            # -------------------------
            if any(greet in lower_message for greet in ["hi", "hello", "hey"]):
                await websocket.send_json({
                    "type": "assistant_message",
                    "content": "Hello! I'm your finance assistant. How can I help you today?"
                })
                continue

            # -------------------------
            # 🧠 INTENT DETECTION
            # -------------------------
            finance_keywords = [
                "budget", "spend", "income",
                "expenses", "saving", "balance"
            ]

            requires_finance_data = any(
                word in lower_message for word in finance_keywords
            )

            # -------------------------
            # 🚫 Not finance related
            # -------------------------
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

            # -------------------------
            # 📅 Extract month/year
            # -------------------------
            month_data = date_extractor.extract_month_year(user_message)
            year = month_data["year"]
            month = month_data["month"]

            # -------------------------
            # 👨‍👩‍👧 Get family
            # -------------------------
            family = db.query(Family).filter(
                Family.head_id == user_id
            ).first()

            if not family:
                await websocket.send_json({
                    "type": "assistant_message",
                    "content": "No family data found."
                })
                continue

            # -------------------------
            # 📊 Try specific month first
            # -------------------------
            monthly = db.query(FamilyMonthly).filter(
                FamilyMonthly.family_id == family.id,
                FamilyMonthly.year == year,
                FamilyMonthly.month == month
            ).first()

            # If not found → fallback to latest month
            if not monthly:
                monthly = db.query(FamilyMonthly).filter(
                    FamilyMonthly.family_id == family.id
                ).order_by(
                    FamilyMonthly.year.desc(),
                    FamilyMonthly.month.desc()
                ).first()

            if not monthly:
                await websocket.send_json({
                    "type": "assistant_message",
                    "content": "No monthly financial data available yet."
                })
                continue

            # -------------------------
            # 💸 Filter expenses by month
            # -------------------------
            last_day = calendar.monthrange(monthly.year, monthly.month)[1]

            start_date = datetime(monthly.year, monthly.month, 1)
            end_date = datetime(
                monthly.year,
                monthly.month,
                last_day,
                23, 59, 59
            )

            expenses = db.query(ExpenseDB).filter(
                ExpenseDB.family_code == family.family_code,
                ExpenseDB.created_at >= start_date,
                ExpenseDB.created_at <= end_date
            ).all()

            total_expenses = sum(e.amount for e in expenses)

            # -------------------------
            # 🧠 Build Finance Context
            # -------------------------
            finance_context = {
                "year": monthly.year,
                "month": monthly.month,
                "opening_balance": monthly.starting_balance,
                "monthly_income": monthly.monthly_income,
                "monthly_budget": monthly.monthly_budget,
                "closing_balance": monthly.closing_balance,
                "total_expenses": total_expenses
            }

            # -------------------------
            # 🤖 Call OpenAI
            # -------------------------
            ai_reply = ai.chat_with_context(
                user_message=user_message,
                finance_data=finance_context
            )

            # -------------------------
            # 📤 Send Response
            # -------------------------
            await websocket.send_json({
                "type": "assistant_message",
                "content": ai_reply
            })

    except WebSocketDisconnect:
        print(f"WebSocket disconnected | user_id={user_id}")

    finally:
        db.close()