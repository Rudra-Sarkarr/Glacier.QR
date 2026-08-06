import os
import threading
import asyncio
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS

import storage
import upi_utils
from discord_bot import create_bot_client

app = Flask(__name__, static_folder='public')
CORS(app)

bot_thread = None
bot_loop = None
bot_client_instance = None

@app.route('/')
def serve_index():
    return send_from_directory('public', 'index.html')

@app.route('/<path:path>')
def serve_static(path):
    return send_from_directory('public', path)

@app.route('/api/user/<user_id>', methods=['GET'])
def get_user_profile(user_id):
    try:
        profile = storage.get_user_profile(user_id)
        return jsonify({"success": True, "profile": profile})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/api/user/slot', methods=['POST'])
def update_slot():
    try:
        data = request.json or {}
        user_id = data.get('userId')
        slot_id = data.get('slotId')
        upi_id = data.get('upiId')
        name = data.get('name', '')

        if not user_id or not slot_id or not upi_id:
            return jsonify({"success": False, "error": "Missing required fields"}), 400

        if not upi_utils.is_valid_upi(upi_id):
            return jsonify({"success": False, "error": "Invalid UPI ID format"}), 400

        updated = storage.update_slot(user_id, slot_id, upi_id, name)
        return jsonify({"success": True, "profile": updated})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/api/user/slot', methods=['DELETE'])
def delete_slot():
    try:
        data = request.json or {}
        user_id = data.get('userId')
        slot_id = data.get('slotId')

        if not user_id or not slot_id:
            return jsonify({"success": False, "error": "Missing userId or slotId"}), 400

        updated = storage.delete_slot(user_id, slot_id)
        return jsonify({"success": True, "profile": updated})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/api/qr/generate', methods=['POST'])
def generate_qr():
    try:
        data = request.json or {}
        upi_id = data.get('upiId')
        amount = data.get('amount')
        name = data.get('name', '')
        note = data.get('note', '')

        if not upi_id or not upi_utils.is_valid_upi(upi_id):
            return jsonify({"success": False, "error": "Valid upiId is required"}), 400

        formatted_amt = upi_utils.format_amount(amount)
        if not formatted_amt:
            return jsonify({"success": False, "error": "Valid positive amount is required"}), 400

        upi_url = upi_utils.build_upi_url(upi_id, formatted_amt, name, note)
        data_url = upi_utils.generate_qr_data_url(upi_url)
        app_links = upi_utils.get_app_links(upi_url)

        return jsonify({
            "success": True,
            "upiUrl": upi_url,
            "qrDataUrl": data_url,
            "amount": formatted_amt,
            "upiId": upi_id,
            "payeeName": name or 'Payee',
            "appLinks": app_links
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

def _run_bot(token):
    global bot_loop, bot_client_instance
    bot_loop = asyncio.new_event_loop()
    asyncio.set_event_loop(bot_loop)
    bot_client_instance = create_bot_client()
    try:
        bot_loop.run_until_complete(bot_client_instance.start(token))
    except Exception as e:
        print(f"Discord Bot stopped/errored: {e}")

@app.route('/api/bot/start', methods=['POST'])
def start_bot():
    global bot_thread, bot_client_instance
    data = request.json or {}
    token = data.get('token', '').strip()

    if not token or len(token) < 20:
        return jsonify({"success": False, "error": "Invalid Discord Bot Token format"}), 400

    if bot_client_instance and bot_client_instance.is_ready():
        return jsonify({"success": True, "message": "Bot is already running."})

    bot_thread = threading.Thread(target=_run_bot, args=(token,), daemon=True)
    bot_thread.start()

    return jsonify({"success": True, "message": "Discord Bot launch initiated!"})

@app.route('/api/bot/stop', methods=['POST'])
def stop_bot():
    global bot_client_instance, bot_loop
    if bot_client_instance and bot_loop:
        asyncio.run_coroutine_threadsafe(bot_client_instance.close(), bot_loop)
        bot_client_instance = None
        return jsonify({"success": True, "message": "Discord Bot shutdown requested."})
    return jsonify({"success": True, "message": "No active bot instance running."})

@app.route('/api/bot/status', methods=['GET'])
def bot_status():
    is_active = bool(bot_client_instance and bot_client_instance.is_ready())
    bot_user = str(bot_client_instance.user) if is_active and bot_client_instance.user else None
    return jsonify({
        "success": True,
        "active": is_active,
        "botUser": bot_user
    })

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 3000))
    print("==================================================")
    print(f"🚀 Custom UPI QR Discord Bot Server running on port {port}")
    print(f"🌐 Open http://localhost:{port} in your browser")
    print("==================================================")
    app.run(host='0.0.0.0', port=port, debug=False)
