import os
import json

DB_FILE = os.path.join(os.path.dirname(__file__), 'data', 'users_db.json')

def _ensure_dir():
    os.makedirs(os.path.dirname(DB_FILE), exist_ok=True)

def load_db() -> dict:
    _ensure_dir()
    if not os.path.exists(DB_FILE):
        return {}
    try:
        with open(DB_FILE, 'r', encoding='utf-8') as f:
            return json.load(f) or {}
    except Exception as e:
        print(f"Error reading DB: {e}")
        return {}

def save_db(db: dict):
    _ensure_dir()
    try:
        with open(DB_FILE, 'w', encoding='utf-8') as f:
            json.dump(db, f, indent=2)
    except Exception as e:
        print(f"Error saving DB: {e}")

def default_profile(user_id: str) -> dict:
    return {
        "userId": str(user_id),
        "slots": [
            {"id": 1, "upiId": "", "name": "Slot 1"},
            {"id": 2, "upiId": "", "name": "Slot 2"},
            {"id": 3, "upiId": "", "name": "Slot 3"},
            {"id": 4, "upiId": "", "name": "Slot 4"}
        ]
    }

def get_user_profile(user_id) -> dict:
    db = load_db()
    uid = str(user_id)
    if uid not in db:
        db[uid] = default_profile(uid)
        save_db(db)
    
    # Ensure 4 slots exist
    if "slots" not in db[uid] or len(db[uid]["slots"]) < 4:
        db[uid]["slots"] = default_profile(uid)["slots"]
        save_db(db)
        
    return db[uid]

def update_slot(user_id, slot_id: int, upi_id: str, name: str = "") -> dict:
    db = load_db()
    uid = str(user_id)
    if uid not in db:
        db[uid] = default_profile(uid)
        
    slot_id = int(slot_id)
    for slot in db[uid]["slots"]:
        if slot["id"] == slot_id:
            slot["upiId"] = upi_id.strip()
            if name and name.strip():
                slot["name"] = name.strip()
            elif not slot.get("name") or slot["name"].startswith("Slot"):
                slot["name"] = f"UPI Slot {slot_id}"
            break
            
    save_db(db)
    return db[uid]

def delete_slot(user_id, slot_id: int) -> dict:
    db = load_db()
    uid = str(user_id)
    if uid in db:
        slot_id = int(slot_id)
        for slot in db[uid]["slots"]:
            if slot["id"] == slot_id:
                slot["upiId"] = ""
                slot["name"] = f"Slot {slot_id}"
                break
        save_db(db)
    return db.get(uid, default_profile(uid))

def get_configured_slots(user_id) -> list:
    profile = get_user_profile(user_id)
    return [s for s in profile.get("slots", []) if s.get("upiId") and s.get("upiId").strip()]
