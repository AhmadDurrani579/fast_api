import json
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

router = APIRouter()

@router.websocket("/ws/chat")
async def chat_socket(websocket: WebSocket):
    await websocket.accept()
    print("WebSocket client connected")

    try:
        while True:
            data = await websocket.receive_text()
            payload = json.loads(data)

            if payload.get("type") == "user_message":
                # Temporary echo (no OpenAI yet)
                await websocket.send_text(json.dumps({
                    "type": "token",
                    "content": f"Echo: {payload['content']}"
                }))

                await websocket.send_text(json.dumps({
                    "type": "end"
                }))

    except WebSocketDisconnect:
        print("WebSocket client disconnected")