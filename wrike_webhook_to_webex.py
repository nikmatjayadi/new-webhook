from fastapi import FastAPI, Request
import httpx
import os

app = FastAPI()

WEBEX_ROOM_ID = os.getenv("WEBEX_ROOM_ID")  # Webex Room ID
WEBEX_TOKEN = os.getenv("WEBEX_TOKEN")      # Webex Bot Token

@app.post("/wrike-webhook")
async def wrike_webhook(request: Request):
    data = await request.json()

    # Simple Wrike event parsing
    title = data.get("title", "Wrike Update")
    text = data.get("body", {}).get("text", str(data))

    message = f"📢 **Wrike Update**\n\n📝 {title}\n\n{text}"

    async with httpx.AsyncClient() as client:
        response = await client.post(
            "https://webexapis.com/v1/messages",
            headers={
                "Authorization": f"Bearer {WEBEX_TOKEN}",
                "Content-Type": "application/json"
            },
            json={
                "roomId": WEBEX_ROOM_ID,
                "markdown": message
            }
        )

    return {"status": "sent", "webex_status": response.status_code}

