import asyncio
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from jose import jwt, JWTError
from app.core.config import settings
from app.services.openai_service import OpenAIService
from sqlalchemy.orm import Session
from app.db.database import SessionLocal
from app.db.models_family import Family, FamilyMonthly
from app.db.models_expenses import ExpenseDB
from app.services.date_extractor import extract_month_year
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
            data = await websocket.receive_json()
            user_message = data.get("content")

            date_info = date_extractor.extract_month_year(user_message)
            print("Extracted:", date_info)
            
            if "content" not in data:
                await websocket.send_json({
                    "type": "error",
                    "message": "Invalid payload"
                })
                continue

            user_message = data["content"]

            # -------------------------
            # 1️⃣ Extract month/year
            # -------------------------
            month_data = extract_month_year(user_message)
            year = month_data["year"]
            month = month_data["month"]

            # -------------------------
            # 2️⃣ Get family
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
            # 3️⃣ Get monthly record
            # -------------------------
            monthly = db.query(FamilyMonthly).filter(
                FamilyMonthly.family_id == family.id,
                FamilyMonthly.year == year,
                FamilyMonthly.month == month
            ).first()

            if not monthly:
                await websocket.send_json({
                    "type": "assistant_message",
                    "content": f"No data found for {month}/{year}"
                })
                continue

            # -------------------------
            # 4️⃣ Get expenses
            # -------------------------
            expenses = db.query(ExpenseDB).filter(
                ExpenseDB.family_code == family.family_code
            ).all()

            total_expenses = sum(e.amount for e in expenses)

            # -------------------------
            # 5️⃣ Build structured finance context
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
            # 6️⃣ Call OpenAI
            # -------------------------
            ai_reply = ai.chat_with_context(
                user_message=user_message,
                finance_data=finance_context
            )

            # -------------------------
            # 7️⃣ Send response
            # -------------------------
            await websocket.send_json({
                "type": "assistant_message",
                "content": ai_reply
            })

    except WebSocketDisconnect:
        print(f"WebSocket disconnected | user_id={user_id}")
    finally:
        db.close()