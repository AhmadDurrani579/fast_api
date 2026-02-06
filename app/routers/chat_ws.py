import asyncio
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from jose import jwt, JWTError
from app.core.config import settings

router = APIRouter()

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


# ---------------- WEBSOCKET ----------------
@router.websocket("/ws/chat")
async def chat_socket(websocket: WebSocket):
    # 🔐 Get token from query params
    token = websocket.query_params.get("token")

    if not token:
        await websocket.close(code=1008)  # Policy violation
        return

    token = token.strip()
    user = verify_jwt(token)

    if not user:
        await websocket.close(code=1008)
        return

    # ✅ Accept only after auth
    await websocket.accept()
    user_id = user.get("id")
    print(f"✅ WebSocket connected | user_id={user_id}")

    try:
        while True:
            try:
                # ⏳ Wait for message (with timeout)
                data = await asyncio.wait_for(
                    websocket.receive_json(),
                    timeout=60  # seconds
                )

                # 🧹 Validate payload
                if "content" not in data:
                    await websocket.send_json({
                        "type": "error",
                        "message": "Invalid payload"
                    })
                    continue

                # 🤖 Temporary static reply
                await websocket.send_json({
                    "type": "assistant_message",
                    "content": "Hi, how are you Talha?" 
                })

            except asyncio.TimeoutError:
                # ❤️ Heartbeat (keeps socket alive)
                await websocket.send_json({
                    "type": "ping"
                })

    except WebSocketDisconnect:
        print(f"❌ WebSocket disconnected | user_id={user_id}")