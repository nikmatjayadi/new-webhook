from fastapi import FastAPI, Request
import os
import json
import httpx
from dotenv import load_dotenv
from typing import Optional

load_dotenv()
app = FastAPI()

WRIKE_TOKEN = os.getenv("WRIKE_TOKEN")
WEBEX_TOKEN = os.getenv("BOT_TOKEN")

# Custom field IDs
PRIORITY_FIELD_ID = os.getenv("PRIORITY_FIELD_ID", "")
TECHNOLOGY_FIELD_ID = os.getenv("TECHNOLOGY_FIELD_ID", "")
TYPE_FIELD_ID = os.getenv("TYPE_FIELD_ID", "")
CUSTOMER_FIELD_ID = os.getenv("CUSTOMER_FIELD_ID", "")

# Folder → Webex room mapping with descriptions
ROOM_MAP = json.loads(os.getenv("PROJECT_TO_ROOM_JSON", "{}"))

# Folders that require Customer field
FOLDERS_WITH_CUSTOMER_NAME = set(os.getenv("FOLDERS_WITH_CUSTOMER_NAME", "").split(","))

@app.get("/")
def root():
    return {"status": "Webhook server is running"}

@app.post("/wrike-webhook")
async def wrike_webhook(request: Request):
    # Wrike verification challenge
    if "x-request-token" in request.headers:
        print("✅ Wrike verification token:", request.headers["x-request-token"])
        return request.headers["x-request-token"]

    events = await request.json()
    if not isinstance(events, list) or not events:
        print("❌ Invalid Wrike webhook payload")
        return {"error": "Invalid payload"}

    event = events[0]
    task_id = event.get("taskId")
    event_type = event.get("eventType", "TaskUpdated")

    if not task_id:
        print("❌ Missing taskId in event")
        return {"error": "No taskId"}

    try:
        task = await get_wrike_task(task_id)
        parent_ids = task.get("parentIds", [])

        room_entry = next((ROOM_MAP.get(pid) for pid in parent_ids if pid in ROOM_MAP), None)

        if not room_entry:
            print(f"⚠️ No Webex room mapped for folders: {parent_ids}")
            return {"ignored": True}

        room_id = room_entry.get("roomId")
        room_desc = room_entry.get("roomDescription", "Unknown Room")
        proj_desc = room_entry.get("projectDescription", "Unknown Project")
        show_customer = any(pid in FOLDERS_WITH_CUSTOMER_NAME for pid in parent_ids)

        message = await build_message(task, event_type, proj_desc, room_desc, show_customer)
        await send_to_webex(room_id, message)

        print(f"✅ Sent message for task '{task['title']}' to room {room_id}")
        return {"status": "sent"}

    except Exception as e:
        print(f"❌ Error processing task {task_id}:", str(e))
        return {"error": str(e)}


async def get_wrike_task(task_id: str) -> dict:
    async with httpx.AsyncClient() as client:
        res = await client.get(
            f"https://www.wrike.com/api/v4/tasks/{task_id}",
            headers={"Authorization": f"Bearer {WRIKE_TOKEN}"}
        )
    res.raise_for_status()
    return res.json()["data"][0]


async def get_user_names(user_ids: list[str]) -> list[str]:
    if not user_ids:
        return ["(Unassigned)"]
    async with httpx.AsyncClient() as client:
        res = await client.get(
            f"https://www.wrike.com/api/v4/contacts/{','.join(user_ids)}",
            headers={"Authorization": f"Bearer {WRIKE_TOKEN}"}
        )
    return [f"{u['firstName']} {u['lastName']}" for u in res.json()["data"]]


async def build_message(
    task: dict,
    event_type: str,
    project_desc: str = "",
    room_desc: str = "",
    show_customer: bool = False
) -> str:
    custom_fields = task.get("customFields", [])
    title = task.get("title", "(No title)")
    status = task.get("status", "(No status)")
    task_type = find_field(custom_fields, TYPE_FIELD_ID, fallback="Task")
    priority = map_priority(find_field(custom_fields, PRIORITY_FIELD_ID))
    technology = find_field(custom_fields, TECHNOLOGY_FIELD_ID, fallback="(None)")
    customer = find_field(custom_fields, CUSTOMER_FIELD_ID) if show_customer else None
    assignees = await get_user_names(task.get("responsibleIds", []))
    permalink = task.get("permalink", f"https://www.wrike.com/open.htm?id={task['id']}")

    message = f"""📌 **{task_type}** - {event_type}
• 📝 Name: {title}
• 🔄 Status: {status}
• 🔺 Priority: {priority}
• 👤 Assignees: {', '.join(assignees)}
• 🧪 Technology: {technology}"""

    if customer:
        message += f"\n• 🧑‍💼 Customer: {customer}"

    message += f"\n• 🔗 [Open in Wrike]({permalink})"
    return message


def find_field(fields, target_id, fallback=None):
    for f in fields:
        if f["id"] == target_id:
            return f.get("value", fallback)
    return fallback


def map_priority(value: Optional[str]) -> str:
    if not value:
        return "(None)"
    return {
        "High": "🔴 High",
        "Medium": "🟡 Medium",
        "Low": "🟢 Low"
    }.get(value, value)


async def send_to_webex(room_id: str, message: str):
    async with httpx.AsyncClient() as client:
        res = await client.post(
            "https://webexapis.com/v1/messages",
            headers={
                "Authorization": f"Bearer {WEBEX_TOKEN}",
                "Content-Type": "application/json"
            },
            json={
                "roomId": room_id,
                "markdown": message
            }
        )
    res.raise_for_status()
