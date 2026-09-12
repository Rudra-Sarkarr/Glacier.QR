import os
import sys
import io
import re
import asyncio
from datetime import datetime

# Configure Windows UTF-8 stdout/stderr with line buffering
if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace', line_buffering=True)
        sys.stderr.reconfigure(encoding='utf-8', errors='replace', line_buffering=True)
    except Exception:
        pass

import discord
from discord import app_commands
from discord.ext import commands, tasks
from aiohttp import web
import socket
import urllib.request
import urllib.parse

# Try loading python-dotenv, or fall back gracefully
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    env_path = os.path.join(os.path.dirname(__file__), '.env')
    if os.path.exists(env_path):
        with open(env_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    k, v = line.split('=', 1)
                    os.environ.setdefault(k.strip(), v.strip())

import storage
import upi_utils
import mailer

# --- Strict Configuration & Server Lockdown ---
WHITELIST_FILE = os.path.join(os.path.dirname(__file__), "wl.txt")
ADMIN_USER_ID = int(os.getenv("ADMIN_USER_ID", "0"))
ALLOWED_GUILD_ID = int(os.getenv("ALLOWED_GUILD_ID", "0"))

# In-Memory Cache for Whitelist
WHITELIST_CACHE = []

def ensure_whitelist_file():
    if not os.path.exists(WHITELIST_FILE):
        with open(WHITELIST_FILE, "w", encoding="utf-8") as f:
            f.write(str(ADMIN_USER_ID) + "\n")

def get_whitelist():
    global WHITELIST_CACHE
    ensure_whitelist_file()
    try:
        with open(WHITELIST_FILE, "r", encoding="utf-8") as f:
            wl = [line.strip() for line in f if line.strip()]
            WHITELIST_CACHE = wl
            return wl
    except Exception:
        return [str(ADMIN_USER_ID)]

def is_admin(user, guild=None):
    uid = getattr(user, 'id', user)
    try:
        uid = int(uid)
    except Exception:
        pass

    # 1. Direct ID match with ADMIN_USER_ID
    if uid == ADMIN_USER_ID or str(uid) == str(ADMIN_USER_ID):
        return True

    g = guild or getattr(user, 'guild', None)
    if not g:
        g = bot.get_guild(ALLOWED_GUILD_ID)

    # 2. Server Owner check
    if g and getattr(g, 'owner_id', None) == uid:
        return True

    member = None
    if isinstance(user, discord.Member):
        member = user
    elif g:
        member = g.get_member(uid)

    if member:
        # 3. Server Administrator permission check
        if getattr(member, 'guild_permissions', None) and member.guild_permissions.administrator:
            return True

        # 4. Check if member has role matching ADMIN_USER_ID
        if hasattr(member, 'roles'):
            for r in member.roles:
                if r.id == ADMIN_USER_ID or str(r.id) == str(ADMIN_USER_ID):
                    return True

    return False

def is_whitelisted(user, guild=None):
    uid = getattr(user, 'id', user)
    try:
        uid = int(uid)
    except Exception:
        pass

    g = guild or getattr(user, 'guild', None)
    if not g:
        g = bot.get_guild(ALLOWED_GUILD_ID)

    member = None
    if isinstance(user, discord.Member):
        member = user
    elif g:
        member = g.get_member(uid)

    target_user = member or user

    if is_admin(target_user, g):
        print(f"[AUTH OK - ADMIN] User: {target_user} (ID: {uid})", flush=True)
        return True

    uid_str = str(uid)
    wl = WHITELIST_CACHE if WHITELIST_CACHE else get_whitelist()
    if uid_str in wl:
        print(f"[AUTH OK - WHITELIST] User: {target_user} (ID: {uid})", flush=True)
        return True

    if hasattr(target_user, 'roles'):
        for r in target_user.roles:
            if str(r.id) in wl:
                print(f"[AUTH OK - ROLE WL] User: {target_user} (Role: {r.id})", flush=True)
                return True

    print(f"[AUTH DENIED] User: {target_user} (ID: {uid}) | Guild: {getattr(g, 'id', 'None')}", flush=True)
    return False

def add_to_whitelist(user_id):
    wl = get_whitelist()
    uid_str = str(user_id)
    if uid_str not in wl:
        wl.append(uid_str)
        with open(WHITELIST_FILE, "w", encoding="utf-8") as f:
            f.write("\n".join(wl) + "\n")
        get_whitelist()
        return True
    return False

def remove_from_whitelist(user_id):
    wl = get_whitelist()
    uid_str = str(user_id)
    if uid_str in wl:
        wl.remove(uid_str)
        with open(WHITELIST_FILE, "w", encoding="utf-8") as f:
            f.write("\n".join(wl) + "\n")
        get_whitelist()
        return True
    return False

def is_allowed_server(guild):
    if not guild:
        return False
    return guild.id == ALLOWED_GUILD_ID

def send_unauthorized_embed():
    return discord.Embed(
        title="🔒 Private Bot Access Restricted",
        description=(
            "`❌` **You are not authorized to use this bot.**\n\n"
            "This bot is in **Private Mode**. Contact the bot owner to get whitelisted."
        ),
        color=discord.Color.red()
    )

def send_wrong_server_embed():
    return discord.Embed(
        title="⛔ Server Locked",
        description=f"`❌` **This bot only operates inside Server ID `{ALLOWED_GUILD_ID}`.**",
        color=discord.Color.red()
    )


# ==============================================================================
# MODALS & VIEWS FOR UPI SETUP & AMOUNT SELECTION
# ==============================================================================

# --- Modal Form for UPI Slot Configuration ---
class SlotConfigModal(discord.ui.Modal):
    def __init__(self, slot_id: int, current_upi: str = "", current_name: str = ""):
        super().__init__(title=f"Configure UPI Slot {slot_id}")
        self.slot_id = slot_id

        self.upi_input = discord.ui.TextInput(
            label=f"UPI ID / VPA for Slot {slot_id}:",
            placeholder="e.g. merchant@okicici or 9876543210@paytm",
            default=current_upi,
            required=True,
            max_length=100
        )
        self.add_item(self.upi_input)

        self.name_input = discord.ui.TextInput(
            label="Payee / Shop Name (Optional):",
            placeholder="e.g. John Store or Personal UPI",
            default=current_name if current_name and not current_name.startswith("Slot") else "",
            required=False,
            max_length=100
        )
        self.add_item(self.name_input)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            if not is_allowed_server(interaction.guild):
                await interaction.response.send_message(embed=send_wrong_server_embed(), ephemeral=True)
                return

            if not is_whitelisted(interaction.user.id):
                await interaction.response.send_message(embed=send_unauthorized_embed(), ephemeral=True)
                return

            upi_id = self.upi_input.value.strip()
            name = self.name_input.value.strip()

            if not upi_utils.is_valid_upi(upi_id):
                await interaction.response.send_message(
                    "⚠️ **Invalid UPI ID format!** Please enter a valid UPI ID (e.g. `user@bank` or `9876543210@paytm`).",
                    ephemeral=True
                )
                return

            storage.update_slot(interaction.user.id, self.slot_id, upi_id, name or f"UPI Slot {self.slot_id}")

            embed = discord.Embed(
                title=f"✅ Slot {self.slot_id} Saved Successfully!",
                color=discord.Color.green()
            )
            embed.add_field(name="💳 UPI ID", value=f"`{upi_id}`", inline=True)
            embed.add_field(name="👤 Payee Name", value=f"`{name or f'UPI Slot {self.slot_id}'}`", inline=True)
            embed.set_footer(text="Now use /qr to generate custom payment QR codes!")

            await interaction.response.send_message(embed=embed, ephemeral=True)
        except Exception as e:
            print(f"Error in SlotConfigModal: {e}")
            if not interaction.response.is_done():
                await interaction.response.send_message(f"❌ Error: {e}", ephemeral=True)


# --- Modal Form for Custom Amount ---
class CustomAmountModal(discord.ui.Modal):
    def __init__(self, slot_id: int):
        super().__init__(title="Enter Custom Payment Amount")
        self.slot_id = slot_id

        self.amount_input = discord.ui.TextInput(
            label="Amount in ₹ (e.g. 300 or 500.50):",
            placeholder="300",
            required=True,
            max_length=15
        )
        self.add_item(self.amount_input)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            if not is_allowed_server(interaction.guild):
                await interaction.response.send_message(embed=send_wrong_server_embed(), ephemeral=True)
                return

            if not is_whitelisted(interaction.user.id):
                await interaction.response.send_message(embed=send_unauthorized_embed(), ephemeral=True)
                return

            amt_str = self.amount_input.value.strip()
            formatted_amt = upi_utils.format_amount(amt_str)

            if not formatted_amt:
                await interaction.response.send_message("⚠️ Invalid amount. Please enter a valid positive number like 300.", ephemeral=True)
                return

            await send_discord_qr(interaction, self.slot_id, formatted_amt)
        except Exception as e:
            print(f"Error in CustomAmountModal: {e}")
            if not interaction.response.is_done():
                await interaction.response.send_message(f"❌ Error: {e}", ephemeral=True)


# --- Interactive Buttons View for /upi-set (4 Slots) ---
class UpiSetView(discord.ui.View):
    def __init__(self, user_id):
        super().__init__(timeout=180)
        profile = storage.get_user_profile(user_id)

        for slot in profile.get("slots", []):
            slot_id = slot["id"]
            upi_id = slot.get("upiId", "")
            name = slot.get("name", f"Slot {slot_id}")

            is_set = bool(upi_id)
            label = f"Slot {slot_id}: {name}" if is_set else f"Set Slot {slot_id}"
            style = discord.ButtonStyle.success if is_set else discord.ButtonStyle.primary

            button = discord.ui.Button(
                label=label[:80],
                style=style,
                custom_id=f"btn_slot_{slot_id}"
            )
            button.callback = self.make_slot_callback(slot_id, upi_id, name)
            self.add_item(button)

    def make_slot_callback(self, slot_id, upi_id, name):
        async def callback(interaction: discord.Interaction):
            try:
                if not is_allowed_server(interaction.guild):
                    await interaction.response.send_message(embed=send_wrong_server_embed(), ephemeral=True)
                    return
                if not is_whitelisted(interaction.user.id):
                    await interaction.response.send_message(embed=send_unauthorized_embed(), ephemeral=True)
                    return
                modal = SlotConfigModal(slot_id, current_upi=upi_id, current_name=name)
                await interaction.response.send_modal(modal)
            except Exception as e:
                print(f"Error launching slot modal: {e}")
        return callback


# --- Interactive Select Menu View for /qr (Select Slot) ---
class QrSlotSelectView(discord.ui.View):
    def __init__(self, user_id):
        super().__init__(timeout=180)
        configured = storage.get_configured_slots(user_id)

        options = [
            discord.SelectOption(
                label=f"Slot {s['id']}: {s['name']}",
                description=s['upiId'][:50],
                value=str(s['id']),
                emoji="💳"
            )
            for s in configured
        ]

        select = discord.ui.Select(
            placeholder="Select a UPI ID slot...",
            options=options
        )
        select.callback = self.select_callback
        self.add_item(select)

    async def select_callback(self, interaction: discord.Interaction):
        try:
            if not is_allowed_server(interaction.guild):
                await interaction.response.send_message(embed=send_wrong_server_embed(), ephemeral=True)
                return
            if not is_whitelisted(interaction.user.id):
                await interaction.response.send_message(embed=send_unauthorized_embed(), ephemeral=True)
                return

            slot_id = int(interaction.data["values"][0])
            view = AmountSelectView(interaction.user.id, slot_id)

            profile = storage.get_user_profile(interaction.user.id)
            slot = next((s for s in profile["slots"] if s["id"] == slot_id), None)

            embed = discord.Embed(
                title="💰 Select Amount for QR Code",
                description=f"💳 **Selected Payee:** `{slot['name']}` (`{slot['upiId']}`)\n\nClick a quick amount button below or enter a custom amount:",
                color=discord.Color.blue()
            )
            await interaction.response.edit_message(embed=embed, view=view)
        except Exception as e:
            print(f"Error in select_callback: {e}")


# --- Interactive Buttons View for Amount Selection ---
class AmountSelectView(discord.ui.View):
    def __init__(self, user_id, slot_id: int):
        super().__init__(timeout=180)
        self.user_id = user_id
        self.slot_id = slot_id

        amounts = [50, 100, 200, 300, 500, 1000, 2000]

        for amt in amounts:
            btn = discord.ui.Button(
                label=f"₹{amt}",
                style=discord.ButtonStyle.green if amt == 300 else discord.ButtonStyle.secondary,
                custom_id=f"amt_{amt}"
            )
            btn.callback = self.make_amount_callback(amt)
            self.add_item(btn)

        custom_btn = discord.ui.Button(
            label="✏️ Custom Amount",
            style=discord.ButtonStyle.danger,
            custom_id="amt_custom"
        )
        custom_btn.callback = self.custom_amount_callback
        self.add_item(custom_btn)

    def make_amount_callback(self, amount):
        async def callback(interaction: discord.Interaction):
            if not is_allowed_server(interaction.guild):
                await interaction.response.send_message(embed=send_wrong_server_embed(), ephemeral=True)
                return
            if not is_whitelisted(interaction.user.id):
                await interaction.response.send_message(embed=send_unauthorized_embed(), ephemeral=True)
                return
            await send_discord_qr(interaction, self.slot_id, str(amount))
        return callback

    async def custom_amount_callback(self, interaction: discord.Interaction):
        try:
            if not is_allowed_server(interaction.guild):
                await interaction.response.send_message(embed=send_wrong_server_embed(), ephemeral=True)
                return
            if not is_whitelisted(interaction.user.id):
                await interaction.response.send_message(embed=send_unauthorized_embed(), ephemeral=True)
                return
            modal = CustomAmountModal(self.slot_id)
            await interaction.response.send_modal(modal)
        except Exception as e:
            print(f"Error launching custom amount modal: {e}")


# ==============================================================================
# BUILT-IN UPI REDIRECT WEB SERVER & QR ACTION WORKFLOW
# ==============================================================================

def get_redirect_base_url():
    configured = os.getenv("REDIRECT_BASE_URL", "").strip().rstrip("/")
    if configured:
        return configured
    port = int(os.getenv("PORT") or os.getenv("SERVER_PORT") or "5050")

    # On Pterodactyl or VPS, use public node IP
    if os.getenv("P_SERVER_UUID") or os.getenv("SERVER_PORT"):
        try:
            req = urllib.request.Request("https://api.ipify.org", headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=3) as resp:
                pub_ip = resp.read().decode().strip()
                if pub_ip:
                    return f"http://{pub_ip}:{port}"
        except Exception:
            pass

    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        local_ip = s.getsockname()[0]
        s.close()
        return f"http://{local_ip}:{port}"
    except Exception:
        return f"http://localhost:{port}"

async def handle_pay_redirect(request):
    params = request.query
    pa = params.get('pa', '')
    am = params.get('am', '')
    pn = params.get('pn', 'Payee')
    tn = params.get('tn', f'Payment of Rs {am}')
    cu = params.get('cu', 'INR')

    if not pa or not am:
        return web.Response(text="Invalid payment parameters. pa and am are required.", status=400)

    qs = urllib.parse.urlencode({'pa': pa, 'am': am, 'pn': pn, 'tn': tn, 'cu': cu}, safe='@')
    upi_url = f"upi://pay?{qs}"
    gpay_url = f"gpay://upi/pay?{qs}"
    phonepe_url = f"phonepe://pay?{qs}"
    paytm_url = f"paytmmp://pay?{qs}"

    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Pay ₹{am} to {pn}</title>
  <style>
    body {{
      margin: 0;
      padding: 24px 16px;
      background: #0b0f19;
      color: #f8fafc;
      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
      display: flex;
      flex-direction: column;
      align-items: center;
      justify-content: center;
      min-height: 90vh;
      box-sizing: border-box;
    }}
    .card {{
      background: #1e293b;
      border: 1px solid #334155;
      border-radius: 24px;
      padding: 32px 24px;
      max-width: 400px;
      width: 100%;
      box-shadow: 0 16px 36px rgba(0,0,0,0.6);
      text-align: center;
      box-sizing: border-box;
    }}
    .icon {{ font-size: 44px; margin-bottom: 8px; }}
    h1 {{ font-size: 20px; margin: 0 0 6px; color: #ffffff; font-weight: 700; }}
    .amount {{ font-size: 42px; font-weight: 800; color: #38bdf8; margin: 8px 0; }}
    .payee {{ color: #94a3b8; font-size: 14px; margin-bottom: 24px; }}
    .btn {{
      display: flex;
      align-items: center;
      justify-content: center;
      gap: 10px;
      width: 100%;
      padding: 15px 0;
      margin: 10px 0;
      border-radius: 14px;
      font-size: 16px;
      font-weight: 700;
      text-decoration: none;
      color: #ffffff;
      box-sizing: border-box;
      box-shadow: 0 4px 12px rgba(0,0,0,0.2);
      transition: transform 0.1s ease;
    }}
    .btn:active {{ transform: scale(0.98); }}
    .btn-upi {{ background: linear-gradient(135deg, #10b981 0%, #059669 100%); }}
    .btn-phonepe {{ background: #5f259f; }}
    .btn-gpay {{ background: #1a73e8; }}
    .btn-paytm {{ background: #00b9f5; }}
    .copy-box {{
      margin-top: 24px;
      padding: 14px;
      background: #0f172a;
      border-radius: 12px;
      font-size: 13px;
      color: #cbd5e1;
      cursor: pointer;
      border: 1px dashed #475569;
    }}
    .footer {{ margin-top: 20px; font-size: 12px; color: #64748b; }}
  </style>
</head>
<body>
  <div class="card">
    <div class="icon">⚡</div>
    <h1>Complete UPI Payment</h1>
    <div class="amount">₹{am}</div>
    <div class="payee">Payee: <strong>{pn}</strong> (<code style="color:#cbd5e1">{pa}</code>)</div>
    
    <a href="{upi_url}" class="btn btn-upi" id="btnUpi">📱 Open Any UPI App</a>
    <a href="{phonepe_url}" class="btn btn-phonepe">🟣 Open in PhonePe</a>
    <a href="{gpay_url}" class="btn btn-gpay">🔵 Open in Google Pay</a>
    <a href="{paytm_url}" class="btn btn-paytm">🔷 Open in Paytm</a>

    <div class="copy-box" onclick="navigator.clipboard.writeText('{pa}'); alert('UPI ID copied to clipboard: {pa}');">
      📋 Tap to copy UPI ID: <strong>{pa}</strong>
    </div>
    <div class="footer">If your app does not open automatically, tap your preferred app button above.</div>
  </div>

  <script>
    window.addEventListener('load', function() {{
      setTimeout(function() {{
        window.location.href = "{upi_url}";
      }}, 300);
    }});
  </script>
</body>
</html>
"""
    return web.Response(text=html_content, content_type='text/html')

web_app_runner = None

async def start_web_server():
    global web_app_runner
    if web_app_runner is not None:
        return
    try:
        app = web.Application()
        app.router.add_get('/pay', handle_pay_redirect)
        web_app_runner = web.AppRunner(app)
        await web_app_runner.setup()
        port = int(os.getenv("PORT") or os.getenv("SERVER_PORT") or "5050")
        site = web.TCPSite(web_app_runner, '0.0.0.0', port)
        await site.start()
        print(f"🌐 UPI Redirect Web Server running on port {port} (URL: {get_redirect_base_url()}/pay)!", flush=True)
    except Exception as e:
        print(f"Error starting redirect web server: {e}", flush=True)


# --- QR Actions View attached to generated QR ---
class QrActionView(discord.ui.View):
    def __init__(self, slot_id: int, amount: str, upi_id: str, payee_name: str, upi_url: str):
        super().__init__(timeout=3600)
        self.slot_id = slot_id
        self.amount = amount
        self.upi_id = upi_id
        self.payee_name = payee_name
        self.upi_url = upi_url

        base_url = get_redirect_base_url()
        query_str = urllib.parse.urlencode({
            "pa": upi_id,
            "am": amount,
            "pn": payee_name,
            "tn": f"Payment of Rs {amount}"
        }, safe='@')
        pay_url = f"{base_url}/pay?{query_str}"

        # Native Discord Link Button (Direct 1-click on mobile!)
        self.add_item(discord.ui.Button(
            label="📱 Pay via UPI App",
            url=pay_url,
            style=discord.ButtonStyle.link,
            emoji="📲"
        ))

        # Button 2: Payment Done
        paid_btn = discord.ui.Button(
            label="✅ Payment Done",
            style=discord.ButtonStyle.success,
            custom_id=f"btn_paid_{slot_id}_{amount}"
        )
        paid_btn.callback = self.payment_done_callback
        self.add_item(paid_btn)

    async def payment_done_callback(self, interaction: discord.Interaction):
        try:
            view = PaymentConfirmView(self.slot_id, self.amount, self.upi_id, self.payee_name)
            embed = discord.Embed(
                title="⚠️ Confirm Payment Completion",
                description=(
                    f"Did you complete the payment of **₹{self.amount}** to **{self.payee_name}** (`{self.upi_id}`)?\n\n"
                    "If you select **Yes**, you will be prompted to enter your name and email to receive your invoice."
                ),
                color=discord.Color.gold()
            )
            await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
        except Exception as e:
            print(f"Error in payment_done_callback: {e}")


# --- Confirmation View: Did you complete the payment? ---
class PaymentConfirmView(discord.ui.View):
    def __init__(self, slot_id: int, amount: str, upi_id: str, payee_name: str):
        super().__init__(timeout=180)
        self.slot_id = slot_id
        self.amount = amount
        self.upi_id = upi_id
        self.payee_name = payee_name

    @discord.ui.button(label="✅ Yes, I have paid", style=discord.ButtonStyle.success)
    async def confirm_paid(self, interaction: discord.Interaction, button: discord.ui.Button):
        modal = PaymentDetailsModal(self.slot_id, self.amount, self.upi_id, self.payee_name)
        await interaction.response.send_modal(modal)

    @discord.ui.button(label="❌ Cancel", style=discord.ButtonStyle.secondary)
    async def cancel_paid(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(content="❌ Payment confirmation cancelled.", embed=None, view=None)


# --- Modal Form for Customer Name, Email, and UTR Number ---
class PaymentDetailsModal(discord.ui.Modal):
    def __init__(self, slot_id: int, amount: str, upi_id: str, payee_name: str):
        super().__init__(title="Submit Payment Details for Invoice")
        self.slot_id = slot_id
        self.amount = amount
        self.upi_id = upi_id
        self.payee_name = payee_name

        self.name_input = discord.ui.TextInput(
            label="Your Full Name:",
            placeholder="e.g. Rudra Sarkar",
            required=True,
            max_length=80
        )
        self.add_item(self.name_input)

        self.email_input = discord.ui.TextInput(
            label="Email Address (for Invoice Delivery):",
            placeholder="e.g. yourname@gmail.com",
            required=True,
            max_length=100
        )
        self.add_item(self.email_input)

        self.utr_input = discord.ui.TextInput(
            label="UPI Ref / UTR Number (12 digits):",
            placeholder="e.g. 425183920192 or transaction ref",
            required=True,
            max_length=50
        )
        self.add_item(self.utr_input)

        self.note_input = discord.ui.TextInput(
            label="Optional Note / Purpose:",
            placeholder="e.g. Server hosting, subscription renewal",
            required=False,
            max_length=100
        )
        self.add_item(self.note_input)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            name = self.name_input.value.strip()
            email = self.email_input.value.strip()
            utr = self.utr_input.value.strip()
            note = self.note_input.value.strip()

            # Email validation
            if not re.match(r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$", email):
                await interaction.response.send_message(
                    "⚠️ **Invalid email address!** Please enter a valid email to receive your invoice.",
                    ephemeral=True
                )
                return

            # Record in storage
            tx_id = storage.create_payment_record(
                user_id=interaction.user.id,
                amount=self.amount,
                slot_id=self.slot_id,
                upi_id=self.upi_id,
                payee_name=self.payee_name,
                customer_name=name,
                customer_email=email,
                utr=utr,
                note=note
            )

            # Confirm to user
            embed = discord.Embed(
                title="✅ Payment Details Submitted!",
                description=(
                    f"Thank you, **{name}**!\n"
                    f"Your payment details for **₹{self.amount}** have been registered.\n\n"
                    f"📧 An **Invoice** has been dispatched to `{email}`.\n"
                    f"⏳ **Status:** `PENDING ADMIN VERIFICATION`\n\n"
                    f"🔖 **TXN ID:** `{tx_id}`\n"
                    f"🔢 **UTR:** `{utr}`\n\n"
                    f"Staff has been notified to verify your payment. Once confirmed, you will receive a payment receipt email."
                ),
                color=discord.Color.green()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)

            # Send Invoice email asynchronously in background
            asyncio.create_task(mailer.send_invoice_email(
                to_email=email,
                customer_name=name,
                tx_id=tx_id,
                amount=self.amount,
                payee_name=self.payee_name,
                upi_id=self.upi_id,
                utr=utr
            ))

            # Notify Admin for verification
            await notify_admin_new_payment(
                tx_id=tx_id,
                discord_user_id=interaction.user.id,
                customer_name=name,
                customer_email=email,
                amount=self.amount,
                payee_name=self.payee_name,
                upi_id=self.upi_id,
                utr=utr,
                note=note,
                fallback_channel=interaction.channel
            )
        except Exception as e:
            print(f"Error in PaymentDetailsModal on_submit: {e}")
            if not interaction.response.is_done():
                await interaction.response.send_message(f"❌ Error submitting payment: {e}", ephemeral=True)


# --- Notify Admin with Interactive Verification View ---
async def notify_admin_new_payment(
    tx_id: str,
    discord_user_id: int,
    customer_name: str,
    customer_email: str,
    amount: str,
    payee_name: str,
    upi_id: str,
    utr: str,
    note: str = "",
    fallback_channel = None
):
    embed_admin = discord.Embed(
        title="🔔 New Payment Verification Request",
        description=(
            f"Did you receive the payment of **₹{amount}** from this user?\n\n"
            f"👤 **Discord User:** <@{discord_user_id}> (`{discord_user_id}`)\n"
            f"🏷️ **Customer Name:** `{customer_name}`\n"
            f"📧 **Email:** `{customer_email}`\n"
            f"💵 **Amount:** `₹{amount}`\n"
            f"💳 **Payee UPI:** `{payee_name}` (`{upi_id}`)\n"
            f"🔢 **UTR / Transaction ID:** `{utr}`\n"
            f"📝 **Note:** `{note or 'None'}`\n"
            f"🔖 **TXN ID:** `{tx_id}`"
        ),
        color=discord.Color.gold()
    )
    embed_admin.set_footer(text="Click a button below to approve or reject this transaction.")

    admin_view = AdminVerificationView(
        tx_id=tx_id,
        discord_user_id=discord_user_id,
        customer_name=customer_name,
        customer_email=customer_email,
        amount=amount,
        payee_name=payee_name,
        upi_id=upi_id,
        utr=utr
    )

    channel_id = int(os.getenv("PAYMENT_LOG_CHANNEL_ID", "0"))
    channel = bot.get_channel(channel_id) if channel_id else None

    if channel:
        try:
            await channel.send(content=f"<@{ADMIN_USER_ID}>", embed=embed_admin, view=admin_view)
            return
        except Exception as e:
            print(f"[Admin Alert] Failed sending to channel {channel_id}: {e}")

    # Fallback 1: Send directly to Admin DM
    sent = False
    try:
        admin_user = bot.get_user(ADMIN_USER_ID) or await bot.fetch_user(ADMIN_USER_ID)
        if admin_user:
            await admin_user.send(embed=embed_admin, view=admin_view)
            sent = True
    except Exception as e:
        print(f"[Admin Alert] Could not send DM to admin {ADMIN_USER_ID}: {e}")

    # Fallback 2: If DM failed and fallback channel is provided, post to channel
    if not sent and fallback_channel:
        try:
            await fallback_channel.send(content=f"<@{ADMIN_USER_ID}>", embed=embed_admin, view=admin_view)
        except Exception as e:
            print(f"[Admin Alert] Failed fallback channel send: {e}")


# --- Admin Verification View (Approve / Reject Buttons) ---
class AdminVerificationView(discord.ui.View):
    def __init__(
        self,
        tx_id: str,
        discord_user_id: int,
        customer_name: str,
        customer_email: str,
        amount: str,
        payee_name: str,
        upi_id: str,
        utr: str
    ):
        super().__init__(timeout=None)
        self.tx_id = tx_id
        self.discord_user_id = discord_user_id
        self.customer_name = customer_name
        self.customer_email = customer_email
        self.amount = amount
        self.payee_name = payee_name
        self.upi_id = upi_id
        self.utr = utr

    @discord.ui.button(label="✅ Payment Received", style=discord.ButtonStyle.success, custom_id="btn_admin_approve")
    async def approve_payment(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not is_admin(interaction.user, interaction.guild) and not is_whitelisted(interaction.user, interaction.guild):
            await interaction.response.send_message("❌ Only authorized administrators can verify payments.", ephemeral=True)
            return

        record = storage.get_payment_record(self.tx_id)
        if not record:
            await interaction.response.send_message("❌ Transaction record not found.", ephemeral=True)
            return

        if record.get("status") != "PENDING":
            await interaction.response.send_message(f"⚠️ This transaction has already been {record.get('status')}.", ephemeral=True)
            return

        # Update status in storage
        storage.update_payment_status(self.tx_id, "APPROVED", interaction.user.id)

        # Send Payment Received Email
        asyncio.create_task(mailer.send_payment_received_email(
            to_email=self.customer_email,
            customer_name=self.customer_name,
            tx_id=self.tx_id,
            amount=self.amount,
            payee_name=self.payee_name,
            upi_id=self.upi_id,
            utr=self.utr
        ))

        # Notify user on Discord
        try:
            user = bot.get_user(self.discord_user_id) or await bot.fetch_user(self.discord_user_id)
            if user:
                user_embed = discord.Embed(
                    title="🎉 Payment Confirmed & Received!",
                    description=(
                        f"Hello **{self.customer_name}**,\n"
                        f"Your payment of **₹{self.amount}** has been verified and confirmed by the administrator!\n\n"
                        f"📧 A payment receipt has been sent to `{self.customer_email}`.\n"
                        f"🔖 **TXN ID:** `{self.tx_id}`\n"
                        f"🔢 **UTR:** `{self.utr}`\n\n"
                        f"Thank you for your payment!"
                    ),
                    color=discord.Color.green()
                )
                await user.send(embed=user_embed)
        except Exception as e:
            print(f"[User Alert] Could not DM user {self.discord_user_id}: {e}")

        # Disable buttons and update admin message
        for item in self.children:
            item.disabled = True

        embed = interaction.message.embeds[0]
        embed.title = "✅ Payment Verified & Received"
        embed.color = discord.Color.green()
        embed.add_field(
            name="Status Update",
            value=f"✅ **APPROVED** by <@{interaction.user.id}> on {datetime.now().strftime('%d %b %Y, %I:%M %p')}",
            inline=False
        )
        await interaction.response.edit_message(embed=embed, view=self)
        await interaction.followup.send(f"✅ Payment for `{self.tx_id}` marked as RECEIVED. Receipt dispatched to `{self.customer_email}`.", ephemeral=True)

    @discord.ui.button(label="❌ Reject / Not Received", style=discord.ButtonStyle.danger, custom_id="btn_admin_reject")
    async def reject_payment(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not is_admin(interaction.user, interaction.guild) and not is_whitelisted(interaction.user, interaction.guild):
            await interaction.response.send_message("❌ Only authorized administrators can verify payments.", ephemeral=True)
            return

        record = storage.get_payment_record(self.tx_id)
        if not record:
            await interaction.response.send_message("❌ Transaction record not found.", ephemeral=True)
            return

        if record.get("status") != "PENDING":
            await interaction.response.send_message(f"⚠️ This transaction has already been {record.get('status')}.", ephemeral=True)
            return

        # Update status in storage
        storage.update_payment_status(self.tx_id, "REJECTED", interaction.user.id)

        # Send Rejection Email
        asyncio.create_task(mailer.send_payment_rejected_email(
            to_email=self.customer_email,
            customer_name=self.customer_name,
            tx_id=self.tx_id,
            amount=self.amount,
            payee_name=self.payee_name,
            upi_id=self.upi_id,
            utr=self.utr
        ))

        # Notify user on Discord
        try:
            user = bot.get_user(self.discord_user_id) or await bot.fetch_user(self.discord_user_id)
            if user:
                user_embed = discord.Embed(
                    title="❌ Payment Not Received / Rejected",
                    description=(
                        f"Hello **{self.customer_name}**,\n"
                        f"Your payment submission of **₹{self.amount}** (UTR: `{self.utr}`) was marked as **Not Received** by the administrator.\n\n"
                        f"📧 An update notice has been sent to `{self.customer_email}`.\n"
                        f"🔖 **TXN ID:** `{self.tx_id}`\n\n"
                        f"If this is in error, please check your bank transaction or contact server staff."
                    ),
                    color=discord.Color.red()
                )
                await user.send(embed=user_embed)
        except Exception as e:
            print(f"[User Alert] Could not DM user {self.discord_user_id}: {e}")

        # Disable buttons and update admin message
        for item in self.children:
            item.disabled = True

        embed = interaction.message.embeds[0]
        embed.title = "❌ Payment Not Received / Rejected"
        embed.color = discord.Color.red()
        embed.add_field(
            name="Status Update",
            value=f"❌ **REJECTED** by <@{interaction.user.id}> on {datetime.now().strftime('%d %b %Y, %I:%M %p')}",
            inline=False
        )
        await interaction.response.edit_message(embed=embed, view=self)
        await interaction.followup.send(f"❌ Payment for `{self.tx_id}` marked as REJECTED. User notified via email.", ephemeral=True)


# --- Helper function to render & send QR code with action buttons ---
async def send_discord_qr(interaction: discord.Interaction, slot_id: int, amount: str):
    try:
        if not is_allowed_server(interaction.guild):
            if not interaction.response.is_done():
                await interaction.response.send_message(embed=send_wrong_server_embed(), ephemeral=True)
            else:
                await interaction.followup.send(embed=send_wrong_server_embed(), ephemeral=True)
            return

        if not is_whitelisted(interaction.user.id):
            if not interaction.response.is_done():
                await interaction.response.send_message(embed=send_unauthorized_embed(), ephemeral=True)
            else:
                await interaction.followup.send(embed=send_unauthorized_embed(), ephemeral=True)
            return

        profile = storage.get_user_profile(interaction.user.id)
        slot = next((s for s in profile["slots"] if s["id"] == slot_id), None)

        if not slot or not slot.get("upiId"):
            if not interaction.response.is_done():
                await interaction.response.send_message("❌ Selected slot is missing a UPI ID.", ephemeral=True)
            else:
                await interaction.followup.send("❌ Selected slot is missing a UPI ID.", ephemeral=True)
            return

        if not interaction.response.is_done():
            await interaction.response.defer()

        upi_id = slot["upiId"]
        payee_name = slot.get("name", "Payee")

        upi_url = upi_utils.build_upi_url(upi_id, amount, payee_name, f"Payment of Rs {amount}")
        qr_bytes = upi_utils.generate_qr_bytes(upi_url)

        file = discord.File(io.BytesIO(qr_bytes), filename=f"upi_qr_{amount}.png")

        base_url = get_redirect_base_url()
        query_str = urllib.parse.urlencode({
            "pa": upi_id,
            "am": amount,
            "pn": payee_name,
            "tn": f"Payment of Rs {amount}"
        }, safe='@')
        pay_url = f"{base_url}/pay?{query_str}"

        action_view = QrActionView(slot_id, amount, upi_id, payee_name, upi_url)

        embed = discord.Embed(
            title="⚡ Custom Value UPI QR Generated",
            color=discord.Color.green()
        )
        embed.add_field(name="💵 Amount", value=f"**₹{amount}**", inline=True)
        embed.add_field(name="💳 UPI ID", value=f"`{upi_id}`", inline=True)
        embed.add_field(name="👤 Payee Name", value=f"`{payee_name}`", inline=True)
        embed.add_field(name="📲 Direct Mobile App Link", value=f"[👉 Tap to Pay via PhonePe / GPay / Paytm]({pay_url})", inline=False)
        embed.set_image(url=f"attachment://upi_qr_{amount}.png")
        embed.set_footer(text="Scan with any UPI app, or tap 'Pay via UPI App' / 'Payment Done' below!")

        await interaction.followup.send(embed=embed, file=file, view=action_view)
    except Exception as e:
        print(f"Error in send_discord_qr: {e}")
        if not interaction.response.is_done():
            await interaction.response.send_message(f"❌ Error generating QR: {e}", ephemeral=True)
        else:
            await interaction.followup.send(f"❌ Error generating QR: {e}", ephemeral=True)


# --- 5-Second Presence & Whitelist Auto-Refresh Loop ---
@tasks.loop(seconds=5)
async def auto_refresh_loop():
    try:
        # Reload whitelist from file
        get_whitelist()

        # Update bot status presence
        latency = round(bot.latency * 1000) if bot.latency else 0
        loop_cnt = auto_refresh_loop.current_loop
        statuses = [
            f"⚡ Latency: {latency}ms | Server Locked",
            f"💳 UPI QR Payments | /cmd",
            f"🔒 Whitelist Mode | Server {ALLOWED_GUILD_ID}"
        ]
        status_name = statuses[loop_cnt % len(statuses)]
        await bot.change_presence(activity=discord.Activity(type=discord.ActivityType.watching, name=status_name))
    except Exception as e:
        print(f"Error in 5s auto refresh loop: {e}")

@auto_refresh_loop.before_loop
async def before_auto_refresh():
    await bot.wait_until_ready()


# --- Discord Bot Client Setup ---
intents = discord.Intents.all()
bot = commands.Bot(command_prefix="/", intents=intents)

@bot.event
async def on_ready():
    print("==================================================", flush=True)
    print(f"🔒 Discord Bot Locked to Server ID: {ALLOWED_GUILD_ID}", flush=True)
    print(f"🤖 Bot User: {bot.user} (ID: {bot.user.id})", flush=True)
    print(f"🌐 Connected Guilds: {[f'{g.name} ({g.id})' for g in bot.guilds]}", flush=True)
    print("🔄 5-Second Whitelist Auto-Reload Loop Started!", flush=True)
    print("📧 SMTP Invoicing & Verification System Active!", flush=True)
    print("==================================================", flush=True)
    await start_web_server()
    try:
        guild_obj = discord.Object(id=ALLOWED_GUILD_ID)
        bot.tree.copy_global_to(guild=guild_obj)
        synced = await bot.tree.sync(guild=guild_obj)
        print(f"⚡ Synced {len(synced)} Slash Commands to Server {ALLOWED_GUILD_ID}!", flush=True)
    except Exception as e:
        print(f"Note on Guild Sync: {e}", flush=True)
        try:
            synced = await bot.tree.sync()
            print(f"✅ Synced {len(synced)} Slash Commands globally!", flush=True)
        except Exception as err:
            print(f"Failed to sync slash commands: {err}", flush=True)

    if not auto_refresh_loop.is_running():
        auto_refresh_loop.start()


# ==============================================================================
# SLASH COMMANDS
# ==============================================================================

@bot.tree.command(name="ping", description="Display current bot latency in milliseconds")
async def ping_slash(interaction: discord.Interaction):
    if not is_allowed_server(interaction.guild):
        await interaction.response.send_message(embed=send_wrong_server_embed(), ephemeral=True)
        return
    if not is_whitelisted(interaction.user.id):
        await interaction.response.send_message(embed=send_unauthorized_embed(), ephemeral=True)
        return
    latency = round(bot.latency * 1000)
    embed = discord.Embed(
        title="Bot Latency",
        description=f"`🤖` The bot's latency is `{latency}ms`.",
        color=discord.Color(0x17004e)
    )
    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="wl", description="Add or remove server members from the staff whitelist")
@app_commands.describe(user="Select/Mention the Discord User to whitelist")
async def wl_slash(interaction: discord.Interaction, user: discord.User):
    if not is_allowed_server(interaction.guild):
        await interaction.response.send_message(embed=send_wrong_server_embed(), ephemeral=True)
        return
    if not is_admin(interaction.user, interaction.guild):
        embed = discord.Embed(
            title="WL Manager",
            description="`❌` **Only the bot owner or server administrators can use this command.**",
            color=discord.Color(0x17004e)
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return

    added = add_to_whitelist(user.id)
    msg = f"`✅` **User {user.mention} (`{user.id}`) has been added to the whitelist.**" if added else f"`✅` **User {user.mention} (`{user.id}`) is already whitelisted.**"
    embed = discord.Embed(title="WL Manager", description=msg, color=discord.Color(0x17004e))
    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="unwl", description="Remove a user from whitelist")
@app_commands.describe(user="Select/Mention the Discord User to remove from whitelist")
async def unwl_slash(interaction: discord.Interaction, user: discord.User):
    if not is_allowed_server(interaction.guild):
        await interaction.response.send_message(embed=send_wrong_server_embed(), ephemeral=True)
        return
    if not is_admin(interaction.user, interaction.guild):
        embed = discord.Embed(
            title="WL Manager",
            description="`❌` **Only the bot owner or server administrators can use this command.**",
            color=discord.Color(0x17004e)
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return

    removed = remove_from_whitelist(user.id)
    msg = f"`✅` **User {user.mention} (`{user.id}`) removed from whitelist.**" if removed else f"`❌` **User {user.mention} is not in whitelist.**"
    embed = discord.Embed(title="WL Manager", description=msg, color=discord.Color(0x17004e))
    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="cmd", description="Display full interactive commands control panel")
async def cmd_slash(interaction: discord.Interaction):
    if not is_allowed_server(interaction.guild):
        await interaction.response.send_message(embed=send_wrong_server_embed(), ephemeral=True)
        return
    if not is_whitelisted(interaction.user.id):
        await interaction.response.send_message(embed=send_unauthorized_embed(), ephemeral=True)
        return

    embed = discord.Embed(
        title="Commands Panel",
        description=(
            "**⚙️ Utility & Whitelist Commands:**\n"
            "🔹 `/ping` → Display current bot latency in milliseconds\n"
            "🔹 `/wl @user` → Add a server member to the staff whitelist\n"
            "🔹 `/unwl @user` → Remove a user from the staff whitelist\n"
            "🔹 `/cmd` → Display full interactive commands control panel\n\n"
            "**💳 UPI QR & Payment Commands:**\n"
            "🔹 `/upi-set` → Configure up to 4 stored UPI ID slots via modal popup dialogs\n"
            "🔹 `/qr` → Select slot & amount to render payment QR code\n"
            "🔹 `/myupi` → View all currently configured UPI ID slots\n"
            "🔹 `300` (chat) → Type any amount in chat for instant payment QR code\n"
            "🔹 `📱 Open UPI App` → One-click deep link to launch installed UPI app\n"
            "🔹 `✅ Payment Done` → Confirm payment, enter email & receive invoice"
        ),
        color=discord.Color(0x17004e)
    )
    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="upi-set", description="Configure up to 4 stored UPI ID slots via modal popup dialogs")
async def upi_set_slash(interaction: discord.Interaction):
    if not is_allowed_server(interaction.guild):
        await interaction.response.send_message(embed=send_wrong_server_embed(), ephemeral=True)
        return
    if not is_whitelisted(interaction.user.id):
        await interaction.response.send_message(embed=send_unauthorized_embed(), ephemeral=True)
        return

    embed = discord.Embed(
        title="⚙️ Multi-Slot UPI ID Manager",
        description="Store up to **4 UPI IDs**. Click any button below to configure or edit that slot using a pop-up modal menu:",
        color=discord.Color.blurple()
    )
    profile = storage.get_user_profile(interaction.user.id)
    for s in profile.get("slots", []):
        status = "✅" if s.get("upiId") else "❌"
        val = f"💳 `{s['upiId']}`\n👤 *{s['name']}*" if s.get("upiId") else "*Not Configured*"
        embed.add_field(name=f"Slot {s['id']} {status}", value=val, inline=True)

    view = UpiSetView(interaction.user.id)
    await interaction.response.send_message(embed=embed, view=view)


@bot.tree.command(name="qr", description="Select slot & amount to render payment QR code")
async def qr_slash(interaction: discord.Interaction):
    if not is_allowed_server(interaction.guild):
        await interaction.response.send_message(embed=send_wrong_server_embed(), ephemeral=True)
        return
    if not is_whitelisted(interaction.user.id):
        await interaction.response.send_message(embed=send_unauthorized_embed(), ephemeral=True)
        return

    configured = storage.get_configured_slots(interaction.user.id)
    if not configured:
        embed = discord.Embed(
            title="⚠️ No UPI IDs Configured Yet!",
            description="Please configure at least 1 UPI ID slot before generating QR codes.\nUse `/upi-set` to get started!",
            color=discord.Color.red()
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return

    embed = discord.Embed(
        title="📱 Select UPI Slot for Custom QR",
        description="Choose which saved UPI ID you want to receive payment into:",
        color=discord.Color.blurple()
    )
    view = QrSlotSelectView(interaction.user.id)
    await interaction.response.send_message(embed=embed, view=view)


@bot.tree.command(name="myupi", description="View all currently configured UPI ID slots")
async def myupi_slash(interaction: discord.Interaction):
    if not is_allowed_server(interaction.guild):
        await interaction.response.send_message(embed=send_wrong_server_embed(), ephemeral=True)
        return
    if not is_whitelisted(interaction.user.id):
        await interaction.response.send_message(embed=send_unauthorized_embed(), ephemeral=True)
        return

    profile = storage.get_user_profile(interaction.user.id)
    embed = discord.Embed(title="💳 Your Stored UPI ID Slots", color=discord.Color.blue())
    for s in profile.get("slots", []):
        val = f"`{s['upiId']}` ({s['name']})" if s.get("upiId") else "*Not Configured*"
        embed.add_field(name=f"Slot {s['id']}", value=val, inline=True)
    await interaction.response.send_message(embed=embed, ephemeral=True)


@bot.tree.command(name="help", description="Learn how to use the Bot")
async def help_slash(interaction: discord.Interaction):
    if not is_allowed_server(interaction.guild):
        await interaction.response.send_message(embed=send_wrong_server_embed(), ephemeral=True)
        return
    if not is_whitelisted(interaction.user.id):
        await interaction.response.send_message(embed=send_unauthorized_embed(), ephemeral=True)
        return

    embed = discord.Embed(
        title="ℹ️ Discord Bot Help & Commands",
        description=(
            "**💳 UPI QR Commands:**\n"
            "🔹 `/upi-set` - Configure up to 4 UPI ID slots via modal popup dialogs\n"
            "🔹 `/qr` - Select slot & amount to render payment QR code\n"
            "🔹 `/myupi` - View all currently configured UPI ID slots\n"
            "🔹 `300` (chat) - Type any number in chat for an instant payment QR code\n\n"
            "**📧 Payment & Invoicing Flow:**\n"
            "1️⃣ Scan the QR code or click **📱 Open UPI App** to pay\n"
            "2️⃣ Click **✅ Payment Done** on the QR message\n"
            "3️⃣ Confirm and submit your name, email, and UTR number\n"
            "4️⃣ An automated invoice will be sent to your email\n"
            "5️⃣ Admin verifies the payment: you get a receipt email when approved\n\n"
            "**⚙️ Utility & Whitelist Commands:**\n"
            "🔹 `/ping` - Display current bot latency in milliseconds\n"
            "🔹 `/cmd` - Display full interactive commands control panel\n"
            "🔹 `/wl @user` / `/unwl @user` - Manage authorized staff whitelist"
        ),
        color=discord.Color.gold()
    )
    await interaction.response.send_message(embed=embed, ephemeral=True)


# --- On Message Listener for Server Check & Direct Amounts ---

@bot.event
async def on_message(message: discord.Message):
    if message.author.bot:
        return

    content = message.content.strip()

    # Process commands starting with '/'
    if content.startswith('/'):
        if not is_allowed_server(message.guild):
            await message.channel.send(embed=send_wrong_server_embed())
            return
        await bot.process_commands(message)
        return

    # Direct number entry in chat (e.g. typing "300" or "₹300")
    extracted_amt = upi_utils.format_amount(content)
    if extracted_amt and not " " in content:
        if not is_allowed_server(message.guild):
            await message.reply(embed=send_wrong_server_embed())
            return

        if not is_whitelisted(message.author, message.guild):
            await message.reply(embed=send_unauthorized_embed())
            return

        configured = storage.get_configured_slots(message.author.id)
        if not configured:
            await message.reply("💡 You entered an amount, but no UPI ID is saved yet! Use `/upi-set` to save your UPI ID first.")
        elif len(configured) == 1:
            slot_id = configured[0]["id"]
            upi_id = configured[0]["upiId"]
            payee_name = configured[0]["name"]

            upi_url = upi_utils.build_upi_url(upi_id, extracted_amt, payee_name, f"Payment of Rs {extracted_amt}")
            qr_bytes = upi_utils.generate_qr_bytes(upi_url)
            file = discord.File(io.BytesIO(qr_bytes), filename=f"upi_qr_{extracted_amt}.png")

            base_url = get_redirect_base_url()
            query_str = urllib.parse.urlencode({
                "pa": upi_id,
                "am": extracted_amt,
                "pn": payee_name,
                "tn": f"Payment of Rs {extracted_amt}"
            }, safe='@')
            pay_url = f"{base_url}/pay?{query_str}"

            action_view = QrActionView(slot_id, extracted_amt, upi_id, payee_name, upi_url)

            embed = discord.Embed(title="⚡ Custom Value UPI QR Generated", color=discord.Color.green())
            embed.add_field(name="💵 Amount", value=f"**₹{extracted_amt}**", inline=True)
            embed.add_field(name="💳 UPI ID", value=f"`{upi_id}`", inline=True)
            embed.add_field(name="👤 Payee Name", value=f"`{payee_name}`", inline=True)
            embed.add_field(name="📲 Direct Mobile App Link", value=f"[👉 Tap to Pay via PhonePe / GPay / Paytm]({pay_url})", inline=False)
            embed.set_image(url=f"attachment://upi_qr_{extracted_amt}.png")
            embed.set_footer(text="Scan with any UPI app, or tap 'Pay via UPI App' / 'Payment Done' below!")

            await message.reply(embed=embed, file=file, view=action_view)
        else:
            embed = discord.Embed(
                title=f"💸 Select UPI Slot for ₹{extracted_amt}",
                description="Which UPI ID slot should receive this payment?",
                color=discord.Color.blue()
            )
            view = QrSlotSelectView(message.author.id)
            await message.reply(embed=embed, view=view)


if __name__ == "__main__":
    TOKEN = os.getenv("DISCORD_BOT_TOKEN")
    if not TOKEN:
        print("--------------------------------------------------")
        print("⚠️ DISCORD_BOT_TOKEN is not set in environment or .env file!")
        TOKEN = input("👉 Please enter your Discord Bot Token: ").strip()

    if TOKEN:
        bot.run(TOKEN)
    else:
        print("❌ No token provided. Exiting.")
