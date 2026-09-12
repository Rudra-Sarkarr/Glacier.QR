import os
import json
import secrets
from datetime import datetime

DB_FILE = os.path.join(os.path.dirname(__file__), 'data', 'users_db.json')
PAYMENTS_FILE = os.path.join(os.path.dirname(__file__), 'data', 'payments.json')

def _ensure_dir(filepath):
    os.makedirs(os.path.dirname(filepath), exist_ok=True)

def load_db() -> dict:
    _ensure_dir(DB_FILE)
    if not os.path.exists(DB_FILE):
        return {}
    try:
        with open(DB_FILE, 'r', encoding='utf-8') as f:
            return json.load(f) or {}
    except Exception as e:
        print(f"Error reading DB: {e}")
        return {}

def save_db(db: dict):
    _ensure_dir(DB_FILE)
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


# ==============================================================================
# PAYMENTS & INVOICES STORAGE
# ==============================================================================

def load_payments() -> dict:
    _ensure_dir(PAYMENTS_FILE)
    if not os.path.exists(PAYMENTS_FILE):
        return {}
    try:
        with open(PAYMENTS_FILE, 'r', encoding='utf-8') as f:
            return json.load(f) or {}
    except Exception as e:
        print(f"Error reading Payments DB: {e}")
        return {}

def save_payments(payments: dict):
    _ensure_dir(PAYMENTS_FILE)
    try:
        with open(PAYMENTS_FILE, 'w', encoding='utf-8') as f:
            json.dump(payments, f, indent=2)
    except Exception as e:
        print(f"Error saving Payments DB: {e}")

def create_payment_record(
    user_id: int,
    amount: str,
    slot_id: int,
    upi_id: str,
    payee_name: str,
    customer_name: str,
    customer_email: str,
    utr: str,
    note: str = ""
) -> str:
    """Creates a new payment record with status PENDING and returns the unique tx_id."""
    payments = load_payments()
    date_str = datetime.now().strftime("%Y%m%d")
    rand_suffix = secrets.token_hex(3).upper()
    tx_id = f"TXN-{date_str}-{rand_suffix}"

    record = {
        "tx_id": tx_id,
        "discord_user_id": str(user_id),
        "amount": str(amount),
        "slot_id": int(slot_id),
        "upi_id": str(upi_id),
        "payee_name": str(payee_name),
        "customer_name": str(customer_name),
        "customer_email": str(customer_email).strip().lower(),
        "utr": str(utr).strip(),
        "note": str(note).strip(),
        "status": "PENDING",  # PENDING, APPROVED, REJECTED
        "created_at": datetime.now().strftime("%d %b %Y, %I:%M %p"),
        "reviewed_at": None,
        "reviewed_by": None
    }
    payments[tx_id] = record
    save_payments(payments)
    return tx_id

def get_payment_record(tx_id: str) -> dict:
    payments = load_payments()
    return payments.get(tx_id)

def update_payment_status(tx_id: str, status: str, admin_id: int) -> dict:
    """Updates the status of a payment (APPROVED or REJECTED)."""
    payments = load_payments()
    if tx_id in payments:
        payments[tx_id]["status"] = status
        payments[tx_id]["reviewed_at"] = datetime.now().strftime("%d %b %Y, %I:%M %p")
        payments[tx_id]["reviewed_by"] = str(admin_id)
        save_payments(payments)
        return payments[tx_id]
    return None
