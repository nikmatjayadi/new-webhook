# wrike_webhook_to_webex.py

from fastapi import FastAPI, Request
import httpx
import json
import os
from dotenv import load_dotenv

load_dotenv()

app = FastAPI()

# Load mapping from JSON
with open("project_to_webex_room.json") as f:
    ROOM_MAP = json.load(f)

WEBEX_TOKEN = os.getenv("WEBEX_TOKEN")

@app.post("/wrike-webhook")
async def wrike_webhook(request: Request):
    data = await request.json()
    print("📩 Wrike Webhook Received:", data)

    folder_id = data.get("folderId") or data.get("projectId")
    if not folder_id:
        return {"status": "ignored", "reason": "No folder/project ID"}

    room_entry = ROOM_MAP.get(folder_id)
    if not room_entry:
        return {"status": "ignored", "reason": f"No mapping for {folder_id}"}

    room_id = room_entry.get("roomId")
    room_desc = room_entry.get("roomDescription", "Unnamed Room")
    proj_desc = room_entry.get("projectDescription", "Unnamed Project")

    title = data.get("title", "Wrike Event")
    body_text = data.get("body", {}).get("text", str(data))

    message = (
        f"📢 **Update for {proj_desc}**\n"
        f"💬 Room: {room_desc}\n\n"
        f"📝 {title}\n\n{body_text}"
    )

    async with httpx.AsyncClient() as client:
        res = await client.post(
            "https://webexapis.com/v1/messages",
            headers={
                "Authorization": f"Bearer {WEBEX_TOKEN}",
                "Content-Type": "application/json"
            },
            json={"roomId": room_id, "markdown": message}
        )

    return {"status": "sent", "webex_response": res.status_code}

@app.get("/")
def root():
    return {"status": "Webhook server is live!"}
