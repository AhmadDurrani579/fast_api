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
        finance_keywords = ["budget", "spend", "income", "expenses", "saving", "balance"]

        requires_finance_data = any(word in lower_message for word in finance_keywords)

        # -------------------------
        # 🚫 If NOT finance related
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
        # 📅 EXTRACT MONTH/YEAR
        # -------------------------
        month_data = date_extractor.extract_month_year(user_message)
        year = month_data["year"]
        month = month_data["month"]

        # -------------------------
        # 👨‍👩‍👧 GET FAMILY
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
        # 📊 GET MONTHLY DATA
        # -------------------------
        monthly = db.query(FamilyMonthly).filter(
            FamilyMonthly.family_id == family.id,
            FamilyMonthly.year == year,
            FamilyMonthly.month == month
        ).first()

        if not monthly:
            await websocket.send_json({
                "type": "assistant_message",
                "content": f"I couldn't find financial data for {month}/{year}. Please add your budget for that month."
            })
            continue

        # -------------------------
        # 💸 GET EXPENSES
        # -------------------------
        expenses = db.query(ExpenseDB).filter(
            ExpenseDB.family_code == family.family_code
        ).all()

        total_expenses = sum(e.amount for e in expenses)

        # -------------------------
        # 🧠 BUILD FINANCE CONTEXT
        # -------------------------
        finance_context = {
            "year": year,
            "month": month,
            "opening_balance": monthly.starting_balance,
            "monthly_income": monthly.monthly_income,
            "monthly_budget": monthly.monthly_budget,
            "closing_balance": monthly.closing_balance,
            "total_expenses": total_expenses
        }

        # -------------------------
        # 🤖 CALL OPENAI
        # -------------------------
        ai_reply = ai.chat_with_context(
            user_message=user_message,
            finance_data=finance_context
        )

        # -------------------------
        # 📤 SEND RESPONSE
        # -------------------------
        await websocket.send_json({
            "type": "assistant_message",
            "content": ai_reply
        })
    except WebSocketDisconnect:
        print(f"WebSocket disconnected | user_id={user_id}")

    finally:
        db.close()