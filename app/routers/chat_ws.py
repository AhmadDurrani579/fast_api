from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from jose import jwt, JWTError
from app.core.config import settings

router = APIRouter()

def verify_jwt(token: str):
    try:
        payload = jwt.decode(
            token,
            settings.JWT_SECRET,
            algorithms=[settings.JWT_ALGORITHM]
        )
        return payload  # contains user info
    except JWTError:
        return None


@router.websocket("/ws/chat")
async def chat_socket(websocket: WebSocket):
    # 🔐 Get token from query params
    token = websocket.query_params.get("token")

    if not token:
        await websocket.close(code=1008)  # Policy violation
        return

    user = verify_jwt(token)
    if not user:
        await websocket.close(code=1008)
        return

    await websocket.accept()
    print(f"✅ WebSocket connected | user_id={user.get('id')}")

    try:
        while True:
            data = await websocket.receive_json()

            # Ignore content for now, just reply fixed message
            await websocket.send_json({
                "type": "assistant_message",
                "content": "Hi, how are you?"
            })

    except WebSocketDisconnect:
        print("❌ WebSocket disconnected")