import os
import io
import re
import json
import secrets
import string
import urllib.request
import urllib.parse
import urllib.error
import asyncio
import discord
from discord import app_commands
from discord.ext import commands, tasks

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

# --- Strict Configuration & Server Lockdown ---
WHITELIST_FILE = os.path.join(os.path.dirname(__file__), "wl.txt")
ADMIN_USER_ID = int(os.getenv("ADMIN_USER_ID", "0"))
ALLOWED_GUILD_ID = int(os.getenv("ALLOWED_GUILD_ID", "0"))

# In-Memory Cache for 5-Second Auto Reloading User Lists & Whitelist
WHITELIST_CACHE = []
FREE_USERS_CACHE = []
PAID_USERS_CACHE = []

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

def is_whitelisted(user_id):
    uid_str = str(user_id)
    if user_id == ADMIN_USER_ID or uid_str == str(ADMIN_USER_ID):
        return True
    wl = WHITELIST_CACHE if WHITELIST_CACHE else get_whitelist()
    return uid_str in wl

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


# --- Random Credentials Generator ---
def generate_random_credentials(prefix="nexa"):
    rand_id = ''.join(secrets.choice(string.ascii_lowercase + string.digits) for _ in range(6))
    username = f"{prefix}_{rand_id}"
    email = f"{username}@nexahostings.in"

    alphabet = string.ascii_letters + string.digits + "!@#$"
    password_chars = [
        secrets.choice(string.ascii_uppercase),
        secrets.choice(string.ascii_lowercase),
        secrets.choice(string.digits),
        secrets.choice("!@#$")
    ] + [secrets.choice(alphabet) for _ in range(8)]
    
    secrets.SystemRandom().shuffle(password_chars)
    password = "".join(password_chars)
    return email, username, password


# --- Multi-Panel API Integration Helper ---
async def fetch_panel_api(endpoint: str, method: str = "GET", payload: dict = None, panel_type: str = "free"):
    if panel_type.lower() == "paid":
        panel_url = os.getenv("PAID_PANEL_URL", "").rstrip("/")
        api_key = os.getenv("PAID_PANEL_API_KEY", "")
    else:
        panel_url = os.getenv("FREE_PANEL_URL", os.getenv("PANEL_URL", "")).rstrip("/")
        api_key = os.getenv("FREE_PANEL_API_KEY", os.getenv("PANEL_API_KEY", ""))

    if not panel_url or not api_key:
        raise ValueError(f"{panel_type.upper()} PANEL_URL or PANEL_API_KEY is not configured in .env file!")

    url = f"{panel_url}{endpoint}"
    data_bytes = json.dumps(payload).encode('utf-8') if payload else None

    req = urllib.request.Request(url, data=data_bytes, method=method)
    req.add_header("Authorization", f"Bearer {api_key}")
    req.add_header("Content-Type", "application/json")
    req.add_header("Accept", "Application/vnd.pterodactyl.v1+json")

    loop = asyncio.get_running_loop()
    def _fetch():
        with urllib.request.urlopen(req, timeout=45) as resp:
            return resp.read().decode('utf-8')
    try:
        response_text = await loop.run_in_executor(None, _fetch)
        return json.loads(response_text)
    except urllib.error.HTTPError as e:
        err_body = e.read().decode('utf-8')
        try:
            err_json = json.loads(err_body)
            errors = err_json.get("errors", [])
            if errors:
                err_detail = errors[0].get("detail", str(e))
                raise ValueError(f"Panel Error: {err_detail}")
        except Exception:
            pass
        raise ValueError(f"Panel HTTP Error {e.code}: {e.reason}")
    except Exception as e:
        raise ValueError(f"Connection Error to {panel_type.capitalize()} Panel: {e}")

# Fetch all users handling pagination (per_page=100)
async def fetch_all_panel_users(panel_type: str = "free"):
    users = []
    page = 1
    while page <= 10:  # Up to 1000 users
        endpoint = f"/api/application/users?per_page=100&page={page}"
        res = await fetch_panel_api(endpoint, panel_type=panel_type)
        data = res.get("data", [])
        if not data:
            break
        users.extend(data)
        meta = res.get("meta", {}).get("pagination", {})
        total_pages = meta.get("total_pages", 1)
        if page >= total_pages:
            break
        page += 1
    return users

async def create_panel_user_api(email: str, username: str, password: str, panel_type: str = "free"):
    payload = {
        "email": email.strip(),
        "username": username.strip(),
        "first_name": username.strip(),
        "last_name": "User",
        "password": password.strip()
    }
    res = await fetch_panel_api("/api/application/users", method="POST", payload=payload, panel_type=panel_type)
    # Trigger instant user list reload after creating a user
    asyncio.create_task(reload_all_user_lists())
    return res

async def create_panel_server_api(user_email: str, name: str, ram: int, cpu: int, disk: int, backups: int = 2, panel_type: str = "free", node_id: str = None):
    clean_email = user_email.strip()
    user_obj = None

    # 1. Query Pterodactyl API filter directly by email for 100% precision
    try:
        encoded_email = urllib.parse.quote(clean_email)
        filter_res = await fetch_panel_api(f"/api/application/users?filter[email]={encoded_email}", panel_type=panel_type)
        filter_data = filter_res.get("data", [])
        if filter_data:
            user_obj = filter_data[0]["attributes"]
    except Exception as e:
        print(f"Filter query note: {e}")

    # 2. If filter query produced no match, search full cached/paginated user list
    if not user_obj:
        users = FREE_USERS_CACHE if panel_type == "free" and FREE_USERS_CACHE else (PAID_USERS_CACHE if panel_type == "paid" and PAID_USERS_CACHE else [])
        if not users:
            users = await fetch_all_panel_users(panel_type=panel_type)
        user_obj = next((u["attributes"] for u in users if u["attributes"]["email"].lower() == clean_email.lower()), None)

    # 3. If still not found, trigger live full fetch as last resort
    if not user_obj:
        all_users = await fetch_all_panel_users(panel_type=panel_type)
        user_obj = next((u["attributes"] for u in all_users if u["attributes"]["email"].lower() == clean_email.lower()), None)

    if not user_obj:
        raise ValueError(f"No existing {panel_type.capitalize()} Panel user found with email `{clean_email}`.")

    user_id = user_obj["id"]

    nodes_res = await fetch_panel_api("/api/application/nodes", panel_type=panel_type)
    nodes = nodes_res.get("data", [])
    if not nodes:
        raise ValueError(f"No nodes found in {panel_type.capitalize()} Panel!")

    target_nodes = nodes
    if node_id:
        target_nodes = [n for n in nodes if str(n["attributes"]["id"]) == str(node_id)]
        if not target_nodes:
            raise ValueError(f"Node ID `{node_id}` not found on {panel_type.capitalize()} Panel!")

    free_alloc_id = None
    free_alloc_ip = None
    free_alloc_port = None
    selected_node_name = None

    for n in target_nodes:
        nid = n["attributes"]["id"]
        nname = n["attributes"]["name"]
        allocs_res = await fetch_panel_api(f"/api/application/nodes/{nid}/allocations", panel_type=panel_type)
        allocs = allocs_res.get("data", [])
        free = [a for a in allocs if not a["attributes"]["assigned"]]
        if free:
            fa = free[0]["attributes"]
            free_alloc_id = fa["id"]
            free_alloc_ip = fa["ip"]
            free_alloc_port = fa["port"]
            selected_node_name = nname
            break

    if not free_alloc_id:
        nodemsg = f"Node `{node_id}`" if node_id else "any panel node"
        raise ValueError(f"No free IP & Port allocation available on {nodemsg}!")

    payload = {
        "name": name or f"Server-{ram}MB",
        "user": user_id,
        "egg": 3,
        "docker_image": "ghcr.io/pterodactyl/yolks:java_25",
        "startup": "java -Xms128M -XX:MaxRAMPercentage=95.0 -Dterminal.jline=false -Dterminal.ansi=true -jar {{SERVER_JARFILE}}",
        "environment": {
            "SERVER_JARFILE": "server.jar",
            "BUILD_NUMBER": "latest"
        },
        "limits": {
            "memory": int(ram),
            "swap": 0,
            "disk": int(disk),
            "io": 500,
            "cpu": int(cpu)
        },
        "feature_limits": {
            "databases": 1,
            "allocations": 1,
            "backups": int(backups)
        },
        "allocation": {
            "default": free_alloc_id
        }
    }

    res = await fetch_panel_api("/api/application/servers", method="POST", payload=payload, panel_type=panel_type)
    return res, free_alloc_ip, free_alloc_port, user_obj["username"], selected_node_name


# --- Mandatory 5-Second User List & Whitelist Auto-Reload Function ---
async def reload_all_user_lists():
    global FREE_USERS_CACHE, PAID_USERS_CACHE
    try:
        # Reload whitelist file
        get_whitelist()

        # Reload Free Panel Users with pagination
        FREE_USERS_CACHE = await fetch_all_panel_users(panel_type="free")

        # Reload Paid Panel Users with pagination
        PAID_USERS_CACHE = await fetch_all_panel_users(panel_type="paid")
            
        print(f"🔄 [5s Auto-Reload] Synced {len(FREE_USERS_CACHE)} Free Panel Users & {len(PAID_USERS_CACHE)} Paid Panel Users!")
    except Exception as e:
        print(f"Note on auto-reload user lists: {e}")


# --- Autocomplete Handlers (Instant Cached Lookup) ---
async def free_panel_email_autocomplete(interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
    if not is_allowed_server(interaction.guild) or not is_whitelisted(interaction.user.id):
        return []
    try:
        users = FREE_USERS_CACHE if FREE_USERS_CACHE else await fetch_all_panel_users(panel_type="free")
        choices = []
        curr = current.lower().strip()
        for u in users:
            attr = u.get("attributes", {})
            email = attr.get("email", "")
            username = attr.get("username", "")
            label = f"{email} ({username})"
            if not curr or curr in email.lower() or curr in username.lower():
                choices.append(app_commands.Choice(name=label[:100], value=email))
            if len(choices) >= 25:
                break
        return choices
    except Exception:
        return []

async def paid_panel_email_autocomplete(interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
    if not is_allowed_server(interaction.guild) or not is_whitelisted(interaction.user.id):
        return []
    try:
        users = PAID_USERS_CACHE if PAID_USERS_CACHE else await fetch_all_panel_users(panel_type="paid")
        choices = []
        curr = current.lower().strip()
        for u in users:
            attr = u.get("attributes", {})
            email = attr.get("email", "")
            username = attr.get("username", "")
            label = f"{email} ({username})"
            if not curr or curr in email.lower() or curr in username.lower():
                choices.append(app_commands.Choice(name=label[:100], value=email))
            if len(choices) >= 25:
                break
        return choices
    except Exception:
        return []

async def free_panel_node_autocomplete(interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
    if not is_allowed_server(interaction.guild) or not is_whitelisted(interaction.user.id):
        return []
    try:
        res = await fetch_panel_api("/api/application/nodes", panel_type="free")
        nodes = res.get("data", [])
        choices = []
        curr = current.lower().strip()
        for n in nodes:
            attr = n.get("attributes", {})
            nid = str(attr.get("id", ""))
            name = attr.get("name", "")
            label = f"{name} (ID: {nid})"
            if not curr or curr in name.lower() or curr in nid:
                choices.append(app_commands.Choice(name=label[:100], value=nid))
            if len(choices) >= 25:
                break
        return choices
    except Exception:
        return []

async def paid_panel_node_autocomplete(interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
    if not is_allowed_server(interaction.guild) or not is_whitelisted(interaction.user.id):
        return []
    try:
        res = await fetch_panel_api("/api/application/nodes", panel_type="paid")
        nodes = res.get("data", [])
        choices = []
        curr = current.lower().strip()
        for n in nodes:
            attr = n.get("attributes", {})
            nid = str(attr.get("id", ""))
            name = attr.get("name", "")
            label = f"{name} (ID: {nid})"
            if not curr or curr in name.lower() or curr in nid:
                choices.append(app_commands.Choice(name=label[:100], value=nid))
            if len(choices) >= 25:
                break
        return choices
    except Exception:
        return []


# ==============================================================================
# LINK WITH USER INTERACTIVE COMPONENTS & DM DISPATCH
# ==============================================================================

class LinkUserSelect(discord.ui.UserSelect):
    def __init__(self, item_type: str, item_data: dict, original_view=None):
        super().__init__(
            placeholder="Select a Discord member to link and DM details...",
            min_values=1,
            max_values=1
        )
        self.item_type = item_type
        self.item_data = item_data
        self.original_view = original_view

    async def callback(self, interaction: discord.Interaction):
        if not is_allowed_server(interaction.guild):
            await interaction.response.send_message(embed=send_wrong_server_embed(), ephemeral=True)
            return
        if not is_whitelisted(interaction.user.id):
            await interaction.response.send_message(embed=send_unauthorized_embed(), ephemeral=True)
            return

        target_user = self.values[0]
        # Save link to persistent storage
        storage.save_linked_item(target_user.id, self.item_type, self.item_data)

        panel_type_cap = self.item_data.get("panel_type", "Free").capitalize()
        panel_url = self.item_data.get("panel_url", "")

        if self.item_type == "account":
            email = self.item_data.get("email", "N/A")
            username = self.item_data.get("username", "N/A")
            password = self.item_data.get("password", "N/A")
            user_id = self.item_data.get("user_id", "N/A")

            dm_embed = discord.Embed(
                title=f"🎉 Your NexaHostings {panel_type_cap} Panel Account",
                description=f"Hello {target_user.mention}! Your account on the **{panel_type_cap} Panel** has been created and linked to your Discord profile.",
                color=discord.Color.gold() if panel_type_cap.lower() == "paid" else discord.Color.green()
            )
            dm_embed.add_field(name="📧 Email / Login", value=f"`{email}`", inline=True)
            dm_embed.add_field(name="👤 Username", value=f"`{username}`", inline=True)
            dm_embed.add_field(name="🔑 Password", value=f"`{password}`", inline=True)
            if user_id != "N/A":
                dm_embed.add_field(name="🆔 Panel User ID", value=f"`{user_id}`", inline=True)
            if panel_url:
                dm_embed.add_field(name="🌐 Panel Login URL", value=f"[Click to Open {panel_type_cap} Panel]({panel_url})", inline=False)
            dm_embed.add_field(name="🔒 Security Reminder", value="Please change your password after logging in and keep your credentials private.", inline=False)
            dm_embed.set_footer(text=f"Linked by {interaction.user.name}")
        else:  # server
            server_name = self.item_data.get("name", "Nexa Server")
            server_id = self.item_data.get("server_id", "N/A")
            identifier = self.item_data.get("identifier", "N/A")
            alloc_ip = self.item_data.get("alloc_ip", "N/A")
            alloc_port = self.item_data.get("alloc_port", "N/A")
            ram = self.item_data.get("ram", "N/A")
            cpu = self.item_data.get("cpu", "N/A")
            disk = self.item_data.get("disk", "N/A")
            backups = self.item_data.get("backups", "2")
            node_name = self.item_data.get("node_name", "Auto")
            owner_email = self.item_data.get("owner_email", "N/A")

            dm_embed = discord.Embed(
                title=f"🚀 Your NexaHostings Server Has Been Provisioned!",
                description=f"Hello {target_user.mention}! Your server **{server_name}** is now ready on the **{panel_type_cap} Panel**.",
                color=discord.Color.gold() if panel_type_cap.lower() == "paid" else discord.Color.green()
            )
            dm_embed.add_field(name="🖥️ Server Name", value=f"**{server_name}**", inline=True)
            dm_embed.add_field(name="🆔 Server ID", value=f"`{server_id}` ({identifier})", inline=True)
            dm_embed.add_field(name="🌐 Server Address", value=f"`{alloc_ip}:{alloc_port}`", inline=False)
            dm_embed.add_field(name="💾 RAM", value=f"`{ram} MB`", inline=True)
            dm_embed.add_field(name="⚡ CPU", value=f"`{cpu} %`", inline=True)
            dm_embed.add_field(name="💽 Disk Space", value=f"`{disk} MB`", inline=True)
            dm_embed.add_field(name="📦 Backups", value=f"`{backups} Backups`", inline=True)
            dm_embed.add_field(name="🖥️ Node", value=f"`{node_name}`", inline=True)
            if owner_email != "N/A":
                dm_embed.add_field(name="👤 Owner Email", value=f"`{owner_email}`", inline=True)
            if panel_url:
                dm_embed.add_field(name="🌐 Panel Link", value=f"[Open {panel_type_cap} Panel]({panel_url})", inline=False)
            dm_embed.set_footer(text=f"Linked by {interaction.user.name}")

        dm_success = False
        try:
            await target_user.send(embed=dm_embed)
            dm_success = True
        except discord.Forbidden:
            dm_success = False
        except Exception as e:
            print(f"Error sending DM to {target_user.id}: {e}")
            dm_success = False

        if dm_success:
            reply_text = f"✅ **Successfully linked to {target_user.mention}!**\nDirect message containing the login & connection details has been sent to their DM."
        else:
            reply_text = f"⚠️ **Linked to {target_user.mention} in database**, but could not send a DM (they may have direct messages closed/disabled)."

        if self.original_view:
            for child in self.original_view.children:
                if isinstance(child, discord.ui.Button):
                    child.disabled = True
                    child.label = f"Linked with @{target_user.name}"[:80]
                    child.style = discord.ButtonStyle.success
            try:
                if hasattr(self.original_view, 'message') and self.original_view.message:
                    await self.original_view.message.edit(view=self.original_view)
            except Exception as e:
                print(f"Could not update button on original message: {e}")

        await interaction.response.edit_message(content=reply_text, view=None)


class LinkUserSelectView(discord.ui.View):
    def __init__(self, item_type: str, item_data: dict, original_view=None):
        super().__init__(timeout=180)
        self.add_item(LinkUserSelect(item_type, item_data, original_view))


class LinkWithUserButton(discord.ui.Button):
    def __init__(self, item_type: str, item_data: dict):
        super().__init__(
            label="Link with User",
            style=discord.ButtonStyle.primary,
            emoji="🔗"
        )
        self.item_type = item_type
        self.item_data = item_data

    async def callback(self, interaction: discord.Interaction):
        if not is_allowed_server(interaction.guild):
            await interaction.response.send_message(embed=send_wrong_server_embed(), ephemeral=True)
            return
        if not is_whitelisted(interaction.user.id):
            await interaction.response.send_message(embed=send_unauthorized_embed(), ephemeral=True)
            return

        view = LinkUserSelectView(self.item_type, self.item_data, original_view=self.view)
        item_title = "User Account" if self.item_type == "account" else f"Server ({self.item_data.get('name', 'Nexa Server')})"
        await interaction.response.send_message(
            content=f"👤 **Link {item_title} with Discord User**\nSelect a member from the dropdown below to link and dispatch credentials via DM:",
            view=view,
            ephemeral=True
        )


class LinkWithUserView(discord.ui.View):
    def __init__(self, item_type: str, item_data: dict, timeout=None):
        super().__init__(timeout=timeout)
        self.item_type = item_type
        self.item_data = item_data
        self.message = None
        self.add_item(LinkWithUserButton(item_type, item_data))


# --- Modal Form for Custom Panel User Creation ---
class PanelUserCreateModal(discord.ui.Modal):
    def __init__(self, panel_type: str = "free"):
        title_str = f"Create {panel_type.capitalize()} Panel User Account"
        super().__init__(title=title_str[:45])
        self.panel_type = panel_type

        self.email_input = discord.ui.TextInput(
            label="User Email Address:",
            placeholder="e.g. user@example.com",
            required=True,
            max_length=100
        )
        self.add_item(self.email_input)

        self.username_input = discord.ui.TextInput(
            label="Panel Username:",
            placeholder="e.g. john123",
            required=True,
            max_length=50
        )
        self.add_item(self.username_input)

        self.password_input = discord.ui.TextInput(
            label="Account Password:",
            placeholder="Enter secure password",
            required=True,
            max_length=100
        )
        self.add_item(self.password_input)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            if not is_allowed_server(interaction.guild):
                await interaction.response.send_message(embed=send_wrong_server_embed(), ephemeral=True)
                return
            if not is_whitelisted(interaction.user.id):
                await interaction.response.send_message(embed=send_unauthorized_embed(), ephemeral=True)
                return

            await interaction.response.defer(ephemeral=False)

            email = self.email_input.value.strip()
            username = self.username_input.value.strip()
            password = self.password_input.value.strip()

            res = await create_panel_user_api(email, username, password, panel_type=self.panel_type)

            panel_url = os.getenv("PAID_PANEL_URL" if self.panel_type == "paid" else "FREE_PANEL_URL", "https://free.nexahostings.in")
            user_attr = res.get("attributes", {})
            user_id = user_attr.get("id", "N/A")

            embed = discord.Embed(
                title=f"🎉 {self.panel_type.capitalize()} Panel User Account Created!",
                description=f"Successfully created user account on {self.panel_type.capitalize()} Panel (ID: `{user_id}`).",
                color=discord.Color.gold() if self.panel_type == "paid" else discord.Color.green()
            )
            embed.add_field(name="📧 Email", value=f"`{email}`", inline=True)
            embed.add_field(name="👤 Username", value=f"`{username}`", inline=True)
            embed.add_field(name="🔑 Password", value=f"`{password}`", inline=True)
            embed.add_field(name="🌐 Panel URL", value=f"[Open {self.panel_type.capitalize()} Panel]({panel_url})", inline=False)
            embed.set_footer(text=f"Created by {interaction.user.name}")

            account_data = {
                "panel_type": self.panel_type,
                "panel_url": panel_url,
                "email": email,
                "username": username,
                "password": password,
                "user_id": user_id,
                "created_by": interaction.user.name
            }
            link_view = LinkWithUserView("account", account_data)
            msg = await interaction.followup.send(embed=embed, view=link_view, ephemeral=False)
            link_view.message = msg
        except Exception as e:
            print(f"Error in PanelUserCreateModal: {e}")
            if not interaction.response.is_done():
                await interaction.response.send_message(f"❌ Account Creation Failed: {e}", ephemeral=True)
            else:
                await interaction.followup.send(f"❌ Account Creation Failed: {e}", ephemeral=True)



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

# --- Helper function to render & send QR code ---
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

        embed = discord.Embed(
            title="⚡ Custom Value UPI QR Generated",
            color=discord.Color.green()
        )
        embed.add_field(name="💵 Amount", value=f"**₹{amount}**", inline=True)
        embed.add_field(name="💳 UPI ID", value=f"`{upi_id}`", inline=True)
        embed.add_field(name="👤 Payee Name", value=f"`{payee_name}`", inline=True)
        embed.set_image(url=f"attachment://upi_qr_{amount}.png")
        embed.set_footer(text="Scan with GPay, PhonePe, Paytm, BHIM, Cred or any UPI app to pay!")

        await interaction.followup.send(embed=embed, file=file)
    except Exception as e:
        print(f"Error in send_discord_qr: {e}")
        if not interaction.response.is_done():
            await interaction.response.send_message(f"❌ Error generating QR: {e}", ephemeral=True)
        else:
            await interaction.followup.send(f"❌ Error generating QR: {e}", ephemeral=True)


# --- 5-Second Mandatory User List & Presence Auto-Refresh Loop ---
@tasks.loop(seconds=5)
async def auto_refresh_loop():
    try:
        # Mandatory 5-Second Reload of User Lists & Whitelist
        await reload_all_user_lists()

        # Update bot status presence
        latency = round(bot.latency * 1000) if bot.latency else 0
        loop_cnt = auto_refresh_loop.current_loop
        statuses = [
            f"⚡ Latency: {latency}ms | Server Locked",
            f"💳 UPI QR & Panel Manager | /help",
            f"👥 Users: {len(FREE_USERS_CACHE)} Free / {len(PAID_USERS_CACHE)} Paid",
            f"🔒 Authorized Private Mode | Server {ALLOWED_GUILD_ID}"
        ]
        status_name = statuses[loop_cnt % len(statuses)]
        await bot.change_presence(activity=discord.Activity(type=discord.ActivityType.watching, name=status_name))
    except Exception as e:
        print(f"Error in 5s auto refresh loop: {e}")

@auto_refresh_loop.before_loop
async def before_auto_refresh():
    await bot.wait_until_ready()


# --- Discord Bot Client Setup (Prefix: /) ---
intents = discord.Intents.all()
bot = commands.Bot(command_prefix="/", intents=intents)

@bot.event
async def on_ready():
    print("==================================================")
    print(f"🔒 Discord Bot Locked to Server ID: {ALLOWED_GUILD_ID}")
    print(f"🤖 Bot User: {bot.user} (ID: {bot.user.id})")
    print("🔄 Mandatory 5-Second User List & Whitelist Auto-Reload Loop Started!")
    print("📢 Public Channel Announcement Mode Active for User & Server Creation!")
    print("==================================================")
    try:
        guild_obj = discord.Object(id=ALLOWED_GUILD_ID)
        bot.tree.copy_global_to(guild=guild_obj)
        synced = await bot.tree.sync(guild=guild_obj)
        print(f"⚡ Synced {len(synced)} Slash Commands to Server {ALLOWED_GUILD_ID}!")
    except Exception as e:
        print(f"Note on Guild Sync: {e}")
        try:
            synced = await bot.tree.sync()
            print(f"✅ Synced {len(synced)} Slash Commands globally!")
        except Exception as err:
            print(f"Failed to sync slash commands: {err}")

    if not auto_refresh_loop.is_running():
        auto_refresh_loop.start()


# ==============================================================================
# RELOAD USER LIST COMMAND
# ==============================================================================

@bot.tree.command(name="reloaduserlist", description="Force reload the Free and Paid Panel user lists and whitelist immediately")
async def reloaduserlist_slash(interaction: discord.Interaction):
    if not is_allowed_server(interaction.guild):
        await interaction.response.send_message(embed=send_wrong_server_embed(), ephemeral=True)
        return
    if not is_whitelisted(interaction.user.id):
        await interaction.response.send_message(embed=send_unauthorized_embed(), ephemeral=True)
        return

    await interaction.response.defer(ephemeral=False)
    await reload_all_user_lists()

    embed = discord.Embed(
        title="🔄 User List & Whitelist Reloaded!",
        description=(
            f"`✅` **Whitelist**: `{len(WHITELIST_CACHE)}` users\n"
            f"`🖥️` **Free Panel Users**: `{len(FREE_USERS_CACHE)}` users\n"
            f"`💎` **Paid Panel Users**: `{len(PAID_USERS_CACHE)}` users\n\n"
            "*User lists auto-reload every 5 seconds in background!*"
        ),
        color=discord.Color.green()
    )
    await interaction.followup.send(embed=embed, ephemeral=False)


# ==============================================================================
# PAID PANEL SLASH COMMANDS (Public Channel Announcement Mode)
# ==============================================================================

@bot.tree.command(name="paidservercreate", description="Create a new server on Paid NexaHostings Panel with Node Selection, RAM, CPU, Disk & Auto IP")
@app_commands.describe(
    email="Select existing paid user email (autocomplete list available)",
    ram="RAM memory limit in MB (e.g. 4096 or 8192)",
    cpu="CPU limit percentage (e.g. 200 or 400)",
    disk="Disk space limit in MB (e.g. 10240 or 20480)",
    node="Select Paid Panel Node (autocomplete list available)",
    name="Server Name (Optional, default: Paid Nexa Server)"
)
@app_commands.autocomplete(email=paid_panel_email_autocomplete, node=paid_panel_node_autocomplete)
async def paidservercreate_slash(interaction: discord.Interaction, email: str, ram: int, cpu: int, disk: int, node: str = None, name: str = "Paid Nexa Server"):
    if not is_allowed_server(interaction.guild):
        await interaction.response.send_message(embed=send_wrong_server_embed(), ephemeral=True)
        return
    if not is_whitelisted(interaction.user.id):
        await interaction.response.send_message(embed=send_unauthorized_embed(), ephemeral=True)
        return

    await interaction.response.defer(ephemeral=False)

    try:
        res, alloc_ip, alloc_port, username, node_name = await create_panel_server_api(
            user_email=email,
            name=name,
            ram=ram,
            cpu=cpu,
            disk=disk,
            backups=2,
            panel_type="paid",
            node_id=node
        )

        panel_url = os.getenv("PAID_PANEL_URL", "https://paid.nexahostings.in")
        srv_attr = res.get("attributes", {})
        server_id = srv_attr.get("id", "N/A")
        identifier = srv_attr.get("identifier", "N/A")

        embed = discord.Embed(
            title="💎 Paid Panel Server Created Successfully!",
            description=f"Server **{name}** (ID: `{server_id}` / `{identifier}`) has been provisioned on **Paid Panel**.",
            color=discord.Color.gold()
        )
        embed.add_field(name="👤 Owner Email", value=f"`{email}` ({username})", inline=False)
        embed.add_field(name="🖥️ Selected Node", value=f"`{node_name}` (ID: `{node or 'Auto'}`)", inline=True)
        embed.add_field(name="🌐 Auto Allocated IP:Port", value=f"`{alloc_ip}:{alloc_port}`", inline=True)
        embed.add_field(name="💾 RAM", value=f"`{ram} MB`", inline=True)
        embed.add_field(name="⚡ CPU", value=f"`{cpu} %`", inline=True)
        embed.add_field(name="💽 Disk Space", value=f"`{disk} MB`", inline=True)
        embed.add_field(name="📦 Default Backups", value="`2 Backups`", inline=True)
        embed.add_field(name="🌐 Paid Panel Link", value=f"[Open Paid Panel]({panel_url})", inline=False)
        embed.set_footer(text=f"Created by {interaction.user.name}")

        server_data = {
            "panel_type": "paid",
            "panel_url": panel_url,
            "server_id": server_id,
            "identifier": identifier,
            "name": name,
            "node_name": node_name,
            "alloc_ip": alloc_ip,
            "alloc_port": alloc_port,
            "ram": ram,
            "cpu": cpu,
            "disk": disk,
            "backups": 2,
            "owner_email": email,
            "owner_username": username,
            "created_by": interaction.user.name
        }
        link_view = LinkWithUserView("server", server_data)
        msg = await interaction.followup.send(embed=embed, view=link_view, ephemeral=False)
        link_view.message = msg
    except Exception as e:
        await interaction.followup.send(f"❌ Paid Server Creation Failed: {e}", ephemeral=False)

@bot.tree.command(name="paidusercreate-random", description="Generate a random user account on Paid NexaHostings Panel automatically")
async def paidusercreate_random_slash(interaction: discord.Interaction):
    if not is_allowed_server(interaction.guild):
        await interaction.response.send_message(embed=send_wrong_server_embed(), ephemeral=True)
        return
    if not is_whitelisted(interaction.user.id):
        await interaction.response.send_message(embed=send_unauthorized_embed(), ephemeral=True)
        return

    await interaction.response.defer(ephemeral=False)

    try:
        email, username, password = generate_random_credentials(prefix="paid_nexa")
        res = await create_panel_user_api(email, username, password, panel_type="paid")

        panel_url = os.getenv("PAID_PANEL_URL", "https://paid.nexahostings.in")
        user_attr = res.get("attributes", {})
        user_id = user_attr.get("id", "N/A")

        embed = discord.Embed(
            title="🎉 Paid Panel Account Created!",
            description=f"Successfully created a new user account on **Paid Panel** (ID: `{user_id}`).",
            color=discord.Color.gold()
        )
        embed.add_field(name="📧 Email", value=f"`{email}`", inline=True)
        embed.add_field(name="👤 Username", value=f"`{username}`", inline=True)
        embed.add_field(name="🔑 Password", value=f"`{password}`", inline=True)
        embed.add_field(name="🌐 Paid Panel Link", value=f"[Click Here to Open Paid Panel]({panel_url})", inline=False)
        embed.set_footer(text=f"Requested by {interaction.user.name}")

        account_data = {
            "panel_type": "paid",
            "panel_url": panel_url,
            "email": email,
            "username": username,
            "password": password,
            "user_id": user_id,
            "created_by": interaction.user.name
        }
        link_view = LinkWithUserView("account", account_data)
        msg = await interaction.followup.send(embed=embed, view=link_view, ephemeral=False)
        link_view.message = msg
    except Exception as e:
        await interaction.followup.send(f"❌ Paid Panel Random Account Creation Failed: {e}", ephemeral=False)

@bot.tree.command(name="paidusercreate", description="Create a user account on Paid Panel with email, username, and password")
@app_commands.describe(email="Email address for paid panel account", username="Username for paid panel account", password="Password for paid panel account")
async def paidusercreate_slash(interaction: discord.Interaction, email: str = None, username: str = None, password: str = None):
    if not is_allowed_server(interaction.guild):
        await interaction.response.send_message(embed=send_wrong_server_embed(), ephemeral=True)
        return
    if not is_whitelisted(interaction.user.id):
        await interaction.response.send_message(embed=send_unauthorized_embed(), ephemeral=True)
        return

    if not email or not username or not password:
        modal = PanelUserCreateModal(panel_type="paid")
        await interaction.response.send_modal(modal)
        return

    await interaction.response.defer(ephemeral=False)

    try:
        res = await create_panel_user_api(email, username, password, panel_type="paid")
        panel_url = os.getenv("PAID_PANEL_URL", "https://paid.nexahostings.in")
        user_attr = res.get("attributes", {})
        user_id = user_attr.get("id", "N/A")

        embed = discord.Embed(
            title="🎉 Paid Panel User Account Created!",
            description=f"Successfully created user account on **Paid Panel** (ID `{user_id}`).",
            color=discord.Color.gold()
        )
        embed.add_field(name="📧 Email", value=f"`{email}`", inline=True)
        embed.add_field(name="👤 Username", value=f"`{username}`", inline=True)
        embed.add_field(name="🔑 Password", value=f"`{password}`", inline=True)
        embed.add_field(name="🌐 Paid Panel URL", value=f"[Open Paid Panel]({panel_url})", inline=False)
        embed.set_footer(text=f"Created by {interaction.user.name}")

        account_data = {
            "panel_type": "paid",
            "panel_url": panel_url,
            "email": email,
            "username": username,
            "password": password,
            "user_id": user_id,
            "created_by": interaction.user.name
        }
        link_view = LinkWithUserView("account", account_data)
        msg = await interaction.followup.send(embed=embed, view=link_view, ephemeral=False)
        link_view.message = msg
    except Exception as e:
        await interaction.followup.send(f"❌ Paid Panel User Creation Failed: {e}", ephemeral=False)


# ==============================================================================
# FREE PANEL SLASH COMMANDS (Public Channel Announcement Mode)
# ==============================================================================

@bot.tree.command(name="freeservercreate", description="Create a new server on Free NexaHostings Panel with Node Selection, RAM, CPU, Disk & Auto IP")
@app_commands.describe(
    email="Select existing user email (autocomplete list available)",
    ram="RAM memory limit in MB (e.g. 2048 or 4096)",
    cpu="CPU limit percentage (e.g. 100 or 200)",
    disk="Disk space limit in MB (e.g. 5120 or 10240)",
    node="Select Free Panel Node (autocomplete list available)",
    name="Server Name (Optional, default: Nexa Server)"
)
@app_commands.autocomplete(email=free_panel_email_autocomplete, node=free_panel_node_autocomplete)
async def freeservercreate_slash(interaction: discord.Interaction, email: str, ram: int, cpu: int, disk: int, node: str = None, name: str = "Nexa Server"):
    if not is_allowed_server(interaction.guild):
        await interaction.response.send_message(embed=send_wrong_server_embed(), ephemeral=True)
        return
    if not is_whitelisted(interaction.user.id):
        await interaction.response.send_message(embed=send_unauthorized_embed(), ephemeral=True)
        return

    await interaction.response.defer(ephemeral=False)

    try:
        res, alloc_ip, alloc_port, username, node_name = await create_panel_server_api(
            user_email=email,
            name=name,
            ram=ram,
            cpu=cpu,
            disk=disk,
            backups=2,
            panel_type="free",
            node_id=node
        )

        panel_url = os.getenv("FREE_PANEL_URL", "https://free.nexahostings.in")
        srv_attr = res.get("attributes", {})
        server_id = srv_attr.get("id", "N/A")
        identifier = srv_attr.get("identifier", "N/A")

        embed = discord.Embed(
            title="✅ Free Panel Server Created Successfully!",
            description=f"Server **{name}** (ID: `{server_id}` / `{identifier}`) has been created and provisioned on Free Panel.",
            color=discord.Color.green()
        )
        embed.add_field(name="👤 Owner Email", value=f"`{email}` ({username})", inline=False)
        embed.add_field(name="🖥️ Selected Node", value=f"`{node_name}` (ID: `{node or 'Auto'}`)", inline=True)
        embed.add_field(name="🌐 Auto Allocated IP:Port", value=f"`{alloc_ip}:{alloc_port}`", inline=True)
        embed.add_field(name="💾 RAM", value=f"`{ram} MB`", inline=True)
        embed.add_field(name="⚡ CPU", value=f"`{cpu} %`", inline=True)
        embed.add_field(name="💽 Disk Space", value=f"`{disk} MB`", inline=True)
        embed.add_field(name="📦 Default Backups", value="`2 Backups`", inline=True)
        embed.add_field(name="🌐 Free Panel Link", value=f"[Open Free Panel]({panel_url})", inline=False)
        embed.set_footer(text=f"Created by {interaction.user.name}")

        server_data = {
            "panel_type": "free",
            "panel_url": panel_url,
            "server_id": server_id,
            "identifier": identifier,
            "name": name,
            "node_name": node_name,
            "alloc_ip": alloc_ip,
            "alloc_port": alloc_port,
            "ram": ram,
            "cpu": cpu,
            "disk": disk,
            "backups": 2,
            "owner_email": email,
            "owner_username": username,
            "created_by": interaction.user.name
        }
        link_view = LinkWithUserView("server", server_data)
        msg = await interaction.followup.send(embed=embed, view=link_view, ephemeral=False)
        link_view.message = msg
    except Exception as e:
        await interaction.followup.send(f"❌ Free Server Creation Failed: {e}", ephemeral=False)

@bot.tree.command(name="freeusercreate-random", description="Generate a random user account on Free NexaHostings Panel automatically")
async def freeusercreate_random_slash(interaction: discord.Interaction):
    if not is_allowed_server(interaction.guild):
        await interaction.response.send_message(embed=send_wrong_server_embed(), ephemeral=True)
        return
    if not is_whitelisted(interaction.user.id):
        await interaction.response.send_message(embed=send_unauthorized_embed(), ephemeral=True)
        return

    await interaction.response.defer(ephemeral=False)

    try:
        email, username, password = generate_random_credentials(prefix="nexa")
        res = await create_panel_user_api(email, username, password, panel_type="free")

        panel_url = os.getenv("FREE_PANEL_URL", "https://free.nexahostings.in")
        user_attr = res.get("attributes", {})
        user_id = user_attr.get("id", "N/A")

        embed = discord.Embed(
            title="🎉 Free Panel Account Created!",
            description=f"Successfully created a new user account on **Free Panel** (ID: `{user_id}`).",
            color=discord.Color.green()
        )
        embed.add_field(name="📧 Email", value=f"`{email}`", inline=True)
        embed.add_field(name="👤 Username", value=f"`{username}`", inline=True)
        embed.add_field(name="🔑 Password", value=f"`{password}`", inline=True)
        embed.add_field(name="🌐 Free Panel Link", value=f"[Click Here to Open Free Panel]({panel_url})", inline=False)
        embed.set_footer(text=f"Requested by {interaction.user.name}")

        account_data = {
            "panel_type": "free",
            "panel_url": panel_url,
            "email": email,
            "username": username,
            "password": password,
            "user_id": user_id,
            "created_by": interaction.user.name
        }
        link_view = LinkWithUserView("account", account_data)
        msg = await interaction.followup.send(embed=embed, view=link_view, ephemeral=False)
        link_view.message = msg
    except Exception as e:
        await interaction.followup.send(f"❌ Random Panel Account Creation Failed: {e}", ephemeral=False)

@bot.tree.command(name="usercreate", description="Create a user account on Free Panel with email, username, and password")
@app_commands.describe(email="Email address for free panel account", username="Username for free panel account", password="Password for free panel account")
async def usercreate_slash(interaction: discord.Interaction, email: str = None, username: str = None, password: str = None):
    if not is_allowed_server(interaction.guild):
        await interaction.response.send_message(embed=send_wrong_server_embed(), ephemeral=True)
        return
    if not is_whitelisted(interaction.user.id):
        await interaction.response.send_message(embed=send_unauthorized_embed(), ephemeral=True)
        return

    if not email or not username or not password:
        modal = PanelUserCreateModal(panel_type="free")
        await interaction.response.send_modal(modal)
        return

    await interaction.response.defer(ephemeral=False)

    try:
        res = await create_panel_user_api(email, username, password, panel_type="free")
        panel_url = os.getenv("FREE_PANEL_URL", "https://free.nexahostings.in")
        user_attr = res.get("attributes", {})
        user_id = user_attr.get("id", "N/A")

        embed = discord.Embed(
            title="🎉 Free Panel User Account Created!",
            description=f"Successfully created user account on **Free Panel** ID `{user_id}`.",
            color=discord.Color.green()
        )
        embed.add_field(name="📧 Email", value=f"`{email}`", inline=True)
        embed.add_field(name="👤 Username", value=f"`{username}`", inline=True)
        embed.add_field(name="🔑 Password", value=f"`{password}`", inline=True)
        embed.add_field(name="🌐 Free Panel URL", value=f"[Open Free Panel]({panel_url})", inline=False)
        embed.set_footer(text=f"Created by {interaction.user.name}")

        account_data = {
            "panel_type": "free",
            "panel_url": panel_url,
            "email": email,
            "username": username,
            "password": password,
            "user_id": user_id,
            "created_by": interaction.user.name
        }
        link_view = LinkWithUserView("account", account_data)
        msg = await interaction.followup.send(embed=embed, view=link_view, ephemeral=False)
        link_view.message = msg
    except Exception as e:
        await interaction.followup.send(f"❌ Free Panel User Creation Failed: {e}", ephemeral=False)

@bot.tree.command(name="upi-set", description="Configure your 4 UPI ID slots using popup modals")
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

@bot.tree.command(name="qr", description="Generate a custom valued UPI QR Code (e.g. ₹300)")
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

@bot.tree.command(name="myupi", description="View your configured UPI ID slots")
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
            "**🔄 System Commands:**\n"
            "🔹 `/reloaduserlist` - Force reload Free/Paid user lists & whitelist\n\n"
            "**💎 Paid Panel Commands:**\n"
            "🔹 `/paidusercreate-random` - Create random paid panel user\n"
            "🔹 `/paidusercreate` - Create paid panel user\n"
            "🔹 `/paidservercreate` - Create paid panel server (select node, auto IP + 2 backups)\n\n"
            "**🖥️ Free Panel Commands:**\n"
            "🔹 `/freeservercreate` - Create free panel server (select node, auto IP + 2 backups)\n"
            "🔹 `/freeusercreate-random` - Create random free panel user\n"
            "🔹 `/usercreate` - Create free panel user\n\n"
            "**💳 UPI QR Commands:**\n"
            "🔹 `/upi-set` - Configure up to 4 UPI slots\n"
            "🔹 `/qr` - Generate payment QR code\n"
            "🔹 `/myupi` - View saved UPI slots\n"
            "🔹 `300` (chat) - Direct QR generator\n\n"
            "**⚙️ Management & Utility Commands:**\n"
            "🔹 `/cmd` - Display full commands panel\n"
            "🔹 `/linked-info @user` - View linked panel accounts & servers\n"
            "🔹 `/wl @user` / `/unwl @user` - Whitelist manager\n"
            "🔹 `/servers` / `/get` / `/ping` - Bot utils"
        ),
        color=discord.Color.gold()
    )
    await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.tree.command(name="cmd", description="Display full commands panel")
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
            "**🔄 System Commands:**\n"
            "1. `/reloaduserlist` → Force reload Free/Paid user lists & whitelist\n\n"
            "**💎 Paid Panel Commands:**\n"
            "2. `/paidusercreate-random` → Generate random paid panel user\n"
            "3. `/paidusercreate` → Create paid panel user (email, username, pass)\n"
            "4. `/paidservercreate` → Create paid panel server (select node, auto IP + 2 backups)\n\n"
            "**🖥️ Free Panel Commands:**\n"
            "5. `/freeservercreate` → Create free panel server (select node, auto IP + 2 backups)\n"
            "6. `/freeusercreate-random` → Generate random free panel user\n"
            "7. `/usercreate` → Create free panel user\n\n"
            "**💳 UPI QR Commands:**\n"
            "8. `/upi-set` → Configure 4 UPI slots via popup modals\n"
            "9. `/qr` → Generate payment QR code for ₹300, ₹500, etc.\n"
            "10. `/myupi` → View stored UPI slots\n"
            "11. `300` (type number) → Direct custom QR code generation\n\n"
            "**⚙️ Management & Utility Commands:**\n"
            "12. `/ping` → Displays bot latency\n"
            "13. `/linked-info @user` → View linked panel accounts & servers\n"
            "14. `/servers` → Show servers list where bot is present\n"
            "15. `/get <server_id>` → Get server invite link\n"
            "16. `/wl @user` / `/unwl @user` → Whitelist manager"
        ),
        color=discord.Color(0x17004e)
    )
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="ping", description="Displays bot latency")
async def ping_slash(interaction: discord.Interaction):
    if not is_allowed_server(interaction.guild):
        await interaction.response.send_message(embed=send_wrong_server_embed(), ephemeral=True)
        return
    if not is_whitelisted(interaction.user.id):
        await interaction.response.send_message(embed=send_unauthorized_embed(), ephemeral=True)
        return
    latency = round(bot.latency * 1000)
    embed = discord.Embed(title="Bot Latency", description=f"`🤖` The bot's latency is `{latency}ms`.", color=discord.Color(0x17004e))
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="wl", description="Whitelist a user")
@app_commands.describe(user="Select/Mention the Discord User to whitelist")
async def wl_slash(interaction: discord.Interaction, user: discord.User):
    if not is_allowed_server(interaction.guild):
        await interaction.response.send_message(embed=send_wrong_server_embed(), ephemeral=True)
        return
    if interaction.user.id != ADMIN_USER_ID:
        embed = discord.Embed(title="WL Manager", description="`❌` **Only the bot owner can use this command.**", color=discord.Color(0x17004e))
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
    if interaction.user.id != ADMIN_USER_ID:
        embed = discord.Embed(title="WL Manager", description="`❌` **Only the bot owner can use this command.**", color=discord.Color(0x17004e))
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return

    removed = remove_from_whitelist(user.id)
    msg = f"`✅` **User {user.mention} (`{user.id}`) removed from whitelist.**" if removed else f"`❌` **User {user.mention} is not in whitelist.**"
    embed = discord.Embed(title="WL Manager", description=msg, color=discord.Color(0x17004e))
    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="servers", description="Show list of servers where the bot is present")
async def servers_slash(interaction: discord.Interaction):
    if not is_allowed_server(interaction.guild):
        await interaction.response.send_message(embed=send_wrong_server_embed(), ephemeral=True)
        return
    if not is_whitelisted(interaction.user.id):
        await interaction.response.send_message(embed=send_unauthorized_embed(), ephemeral=True)
        return
    guilds_info = [{'name': g.name, 'id': g.id, 'members_count': len(g.members)} for g in bot.guilds]
    guilds_info.sort(key=lambda x: x['members_count'], reverse=True)
    embed = discord.Embed(title="Servers List", description="Servers where bot is present:", color=discord.Color(0x17004e))
    for info in guilds_info:
        embed.add_field(name=f"- {info['name']} (ID: {info['id']})", value=f" - Members: {info['members_count']}", inline=False)
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="get", description="Get an invite link to a server")
@app_commands.describe(server_id="The Server ID to get invite link for")
async def get_slash(interaction: discord.Interaction, server_id: str):
    if not is_allowed_server(interaction.guild):
        await interaction.response.send_message(embed=send_wrong_server_embed(), ephemeral=True)
        return
    if not is_whitelisted(interaction.user.id):
        await interaction.response.send_message(embed=send_unauthorized_embed(), ephemeral=True)
        return
    try:
        sid = int(server_id)
        server = bot.get_guild(sid)
        if server is None:
            await interaction.response.send_message(f"❌ Server with ID `{sid}` not found.", ephemeral=True)
            return
        text_channel = next((c for c in server.text_channels if c.permissions_for(server.me).create_instant_invite), None) or server.text_channels[0]
        invite = await text_channel.create_invite(max_uses=1, unique=True)
        embed = discord.Embed(title="Server Invite Manager", description=f"`✅` **Invitation for server `{sid}`:**\n{invite.url}", color=discord.Color(0x17004e))
        await interaction.response.send_message(embed=embed)
    except Exception as e:
        await interaction.response.send_message(f"❌ Error: {e}", ephemeral=True)

@bot.tree.command(name="linked-info", description="View Pterodactyl accounts and servers linked to a Discord member")
@app_commands.describe(user="Select/Mention the Discord member to check")
async def linked_info_slash(interaction: discord.Interaction, user: discord.User):
    if not is_allowed_server(interaction.guild):
        await interaction.response.send_message(embed=send_wrong_server_embed(), ephemeral=True)
        return
    if not is_whitelisted(interaction.user.id):
        await interaction.response.send_message(embed=send_unauthorized_embed(), ephemeral=True)
        return

    data = storage.get_user_linked_items(user.id)
    accounts = data.get("accounts", [])
    servers = data.get("servers", [])

    embed = discord.Embed(
        title=f"🔗 Linked Pterodactyl Details for {user.name}",
        description=f"Showing all accounts and servers linked to {user.mention} (`{user.id}`).",
        color=discord.Color(0x17004e)
    )

    if not accounts and not servers:
        embed.add_field(name="ℹ️ Status", value="No accounts or servers are currently linked to this user.", inline=False)
    else:
        if accounts:
            acc_lines = []
            for idx, acc in enumerate(accounts, 1):
                ptype = acc.get("panel_type", "free").capitalize()
                email = acc.get("email", "N/A")
                uname = acc.get("username", "N/A")
                pwd = acc.get("password", "N/A")
                acc_lines.append(f"**{idx}. [{ptype} Panel]** `{email}` (`{uname}`) | Pass: `{pwd}`")
            embed.add_field(name=f"👤 Linked Accounts ({len(accounts)})", value="\n".join(acc_lines)[:1024], inline=False)

        if servers:
            srv_lines = []
            for idx, srv in enumerate(servers, 1):
                ptype = srv.get("panel_type", "free").capitalize()
                sname = srv.get("name", "Nexa Server")
                sid = srv.get("server_id", "N/A")
                ip = srv.get("alloc_ip", "N/A")
                port = srv.get("alloc_port", "N/A")
                srv_lines.append(f"**{idx}. [{ptype} Panel] {sname}** (ID: `{sid}`) → `{ip}:{port}`")
            embed.add_field(name=f"🖥️ Linked Servers ({len(servers)})", value="\n".join(srv_lines)[:1024], inline=False)

    await interaction.response.send_message(embed=embed, ephemeral=True)



# ==============================================================================
# PREFIX COMMANDS & CHAT LISTENERS
# ==============================================================================

def format_author_footer(embed, author):
    avatar_url = author.avatar.url if getattr(author, 'avatar', None) else author.default_avatar.url
    embed.set_thumbnail(url=avatar_url)
    embed.set_footer(text=f"Requested by {author.name}", icon_url=avatar_url)
    return embed

@bot.command(name='reloaduserlist')
async def reloaduserlist_cmd(ctx):
    if not is_allowed_server(ctx.guild):
        await ctx.send(embed=send_wrong_server_embed())
        return
    if not is_whitelisted(ctx.author.id):
        await ctx.send(embed=send_unauthorized_embed())
        return
    await reload_all_user_lists()
    embed = discord.Embed(
        title="🔄 User List & Whitelist Reloaded!",
        description=f"`✅` **Whitelist**: `{len(WHITELIST_CACHE)}` users\n`🖥️` **Free Users**: `{len(FREE_USERS_CACHE)}` users\n`💎` **Paid Users**: `{len(PAID_USERS_CACHE)}` users",
        color=discord.Color.green()
    )
    await ctx.send(embed=format_author_footer(embed, ctx.author))

@bot.command(name='paidusercreate')
async def paidusercreate_cmd(ctx, mode_or_email: str = None, username: str = None, password: str = None):
    if not is_allowed_server(ctx.guild):
        await ctx.send(embed=send_wrong_server_embed())
        return
    if not is_whitelisted(ctx.author.id):
        await ctx.send(embed=send_unauthorized_embed())
        return

    if mode_or_email and mode_or_email.lower() == 'random':
        try:
            email, username, password = generate_random_credentials(prefix="paid_nexa")
            res = await create_panel_user_api(email, username, password, panel_type="paid")

            panel_url = os.getenv("PAID_PANEL_URL", "https://paid.nexahostings.in")
            user_attr = res.get("attributes", {})
            user_id = user_attr.get("id", "N/A")

            embed = discord.Embed(
                title="🎉 Paid Panel Account Created!",
                description=f"Successfully created a new user account on **Paid Panel** (ID: `{user_id}`).",
                color=discord.Color.gold()
            )
            embed.add_field(name="📧 Email", value=f"`{email}`", inline=True)
            embed.add_field(name="👤 Username", value=f"`{username}`", inline=True)
            embed.add_field(name="🔑 Password", value=f"`{password}`", inline=True)
            embed.add_field(name="🌐 Paid Panel Link", value=f"[Click Here to Open Paid Panel]({panel_url})", inline=False)

            account_data = {
                "panel_type": "paid",
                "panel_url": panel_url,
                "email": email,
                "username": username,
                "password": password,
                "user_id": user_id,
                "created_by": ctx.author.name
            }
            link_view = LinkWithUserView("account", account_data)
            msg = await ctx.send(embed=format_author_footer(embed, ctx.author), view=link_view)
            link_view.message = msg
        except Exception as e:
            await ctx.send(f"❌ Paid Panel Random Account Creation Failed: {e}")
        return

    email = mode_or_email
    if not email or not username or not password:
        await ctx.send("💡 Usage:\n`/paidusercreate random` - Generate random paid account\n`/paidusercreate <email> <username> <password>` - Create custom paid account")
        return

    try:
        res = await create_panel_user_api(email, username, password, panel_type="paid")
        panel_url = os.getenv("PAID_PANEL_URL", "https://paid.nexahostings.in")
        user_attr = res.get("attributes", {})
        user_id = user_attr.get("id", "N/A")

        embed = discord.Embed(
            title="🎉 Paid Panel User Account Created!",
            description=f"Successfully created user account on Paid Panel (ID: `{user_id}`).",
            color=discord.Color.gold()
        )
        embed.add_field(name="📧 Email", value=f"`{email}`", inline=True)
        embed.add_field(name="👤 Username", value=f"`{username}`", inline=True)
        embed.add_field(name="🔑 Password", value=f"`{password}`", inline=True)
        embed.add_field(name="🌐 Paid Panel URL", value=f"[Open Paid Panel]({panel_url})", inline=False)

        account_data = {
            "panel_type": "paid",
            "panel_url": panel_url,
            "email": email,
            "username": username,
            "password": password,
            "user_id": user_id,
            "created_by": ctx.author.name
        }
        link_view = LinkWithUserView("account", account_data)
        msg = await ctx.send(embed=format_author_footer(embed, ctx.author), view=link_view)
        link_view.message = msg
    except Exception as e:
        await ctx.send(f"❌ Paid Panel User Creation Failed: {e}")

@bot.command(name='paidservercreate')
async def paidservercreate_cmd(ctx, email: str = None, ram: int = None, cpu: int = None, disk: int = None, node: str = None, *, name: str = "Paid Nexa Server"):
    if not is_allowed_server(ctx.guild):
        await ctx.send(embed=send_wrong_server_embed())
        return
    if not is_whitelisted(ctx.author.id):
        await ctx.send(embed=send_unauthorized_embed())
        return

    if not email or not ram or not cpu or not disk:
        await ctx.send("💡 Usage: `/paidservercreate <email> <ram_mb> <cpu_%> <disk_mb> [node_id] [name]`")
        return

    try:
        res, alloc_ip, alloc_port, username, node_name = await create_panel_server_api(
            user_email=email,
            name=name,
            ram=ram,
            cpu=cpu,
            disk=disk,
            backups=2,
            panel_type="paid",
            node_id=node
        )

        panel_url = os.getenv("PAID_PANEL_URL", "https://paid.nexahostings.in")
        srv_attr = res.get("attributes", {})
        server_id = srv_attr.get("id", "N/A")
        identifier = srv_attr.get("identifier", "N/A")

        embed = discord.Embed(
            title="💎 Paid Panel Server Created Successfully!",
            description=f"Server **{name}** (ID: `{server_id}`) has been provisioned on **Paid Panel**.",
            color=discord.Color.gold()
        )
        embed.add_field(name="👤 Owner Email", value=f"`{email}` ({username})", inline=False)
        embed.add_field(name="🖥️ Selected Node", value=f"`{node_name}` (ID: `{node or 'Auto'}`)", inline=True)
        embed.add_field(name="🌐 Auto Allocated IP:Port", value=f"`{alloc_ip}:{alloc_port}`", inline=True)
        embed.add_field(name="💾 RAM", value=f"`{ram} MB`", inline=True)
        embed.add_field(name="⚡ CPU", value=f"`{cpu} %`", inline=True)
        embed.add_field(name="💽 Disk Space", value=f"`{disk} MB`", inline=True)
        embed.add_field(name="📦 Default Backups", value="`2 Backups`", inline=True)
        embed.add_field(name="🌐 Paid Panel Link", value=f"[Open Paid Panel]({panel_url})", inline=False)

        server_data = {
            "panel_type": "paid",
            "panel_url": panel_url,
            "server_id": server_id,
            "identifier": identifier,
            "name": name,
            "node_name": node_name,
            "alloc_ip": alloc_ip,
            "alloc_port": alloc_port,
            "ram": ram,
            "cpu": cpu,
            "disk": disk,
            "backups": 2,
            "owner_email": email,
            "owner_username": username,
            "created_by": ctx.author.name
        }
        link_view = LinkWithUserView("server", server_data)
        msg = await ctx.send(embed=format_author_footer(embed, ctx.author), view=link_view)
        link_view.message = msg
    except Exception as e:
        await ctx.send(f"❌ Paid Server Creation Failed: {e}")

@bot.command(name='freeservercreate')
async def freeservercreate_cmd(ctx, email: str = None, ram: int = None, cpu: int = None, disk: int = None, node: str = None, *, name: str = "Nexa Server"):
    if not is_allowed_server(ctx.guild):
        await ctx.send(embed=send_wrong_server_embed())
        return
    if not is_whitelisted(ctx.author.id):
        await ctx.send(embed=send_unauthorized_embed())
        return

    if not email or not ram or not cpu or not disk:
        await ctx.send("💡 Usage: `/freeservercreate <email> <ram_mb> <cpu_%> <disk_mb> [node_id] [name]`")
        return

    try:
        res, alloc_ip, alloc_port, username, node_name = await create_panel_server_api(
            user_email=email,
            name=name,
            ram=ram,
            cpu=cpu,
            disk=disk,
            backups=2,
            panel_type="free",
            node_id=node
        )

        panel_url = os.getenv("FREE_PANEL_URL", "https://free.nexahostings.in")
        srv_attr = res.get("attributes", {})
        server_id = srv_attr.get("id", "N/A")
        identifier = srv_attr.get("identifier", "N/A")

        embed = discord.Embed(
            title="✅ Free Panel Server Created Successfully!",
            description=f"Server **{name}** (ID: `{server_id}`) has been provisioned on Free Panel.",
            color=discord.Color.green()
        )
        embed.add_field(name="👤 Owner Email", value=f"`{email}` ({username})", inline=False)
        embed.add_field(name="🖥️ Selected Node", value=f"`{node_name}` (ID: `{node or 'Auto'}`)", inline=True)
        embed.add_field(name="🌐 Auto Allocated IP:Port", value=f"`{alloc_ip}:{alloc_port}`", inline=True)
        embed.add_field(name="💾 RAM", value=f"`{ram} MB`", inline=True)
        embed.add_field(name="⚡ CPU", value=f"`{cpu} %`", inline=True)
        embed.add_field(name="💽 Disk Space", value=f"`{disk} MB`", inline=True)
        embed.add_field(name="📦 Default Backups", value="`2 Backups`", inline=True)
        embed.add_field(name="🌐 Free Panel Link", value=f"[Open Free Panel]({panel_url})", inline=False)

        server_data = {
            "panel_type": "free",
            "panel_url": panel_url,
            "server_id": server_id,
            "identifier": identifier,
            "name": name,
            "node_name": node_name,
            "alloc_ip": alloc_ip,
            "alloc_port": alloc_port,
            "ram": ram,
            "cpu": cpu,
            "disk": disk,
            "backups": 2,
            "owner_email": email,
            "owner_username": username,
            "created_by": ctx.author.name
        }
        link_view = LinkWithUserView("server", server_data)
        msg = await ctx.send(embed=format_author_footer(embed, ctx.author), view=link_view)
        link_view.message = msg
    except Exception as e:
        await ctx.send(f"❌ Server Creation Failed: {e}")

@bot.command(name='freeusercreate-random')
async def freeusercreate_random_cmd(ctx):
    if not is_allowed_server(ctx.guild):
        await ctx.send(embed=send_wrong_server_embed())
        return
    if not is_whitelisted(ctx.author.id):
        await ctx.send(embed=send_unauthorized_embed())
        return

    try:
        email, username, password = generate_random_credentials(prefix="nexa")
        res = await create_panel_user_api(email, username, password, panel_type="free")

        panel_url = os.getenv("FREE_PANEL_URL", "https://free.nexahostings.in")
        user_attr = res.get("attributes", {})
        user_id = user_attr.get("id", "N/A")

        embed = discord.Embed(
            title="🎉 Free Panel Account Created!",
            description=f"Successfully created a new user account on **Free Panel** (ID: `{user_id}`).",
            color=discord.Color.green()
        )
        embed.add_field(name="📧 Email", value=f"`{email}`", inline=True)
        embed.add_field(name="👤 Username", value=f"`{username}`", inline=True)
        embed.add_field(name="🔑 Password", value=f"`{password}`", inline=True)
        embed.add_field(name="🌐 Free Panel Link", value=f"[Click Here to Open Free Panel]({panel_url})", inline=False)

        account_data = {
            "panel_type": "free",
            "panel_url": panel_url,
            "email": email,
            "username": username,
            "password": password,
            "user_id": user_id,
            "created_by": ctx.author.name
        }
        link_view = LinkWithUserView("account", account_data)
        msg = await ctx.send(embed=format_author_footer(embed, ctx.author), view=link_view)
        link_view.message = msg
    except Exception as e:
        await ctx.send(f"❌ Random Panel Account Creation Failed: {e}")

@bot.command(name='usercreate')
async def usercreate_cmd(ctx, mode_or_email: str = None, username: str = None, password: str = None):
    if not is_allowed_server(ctx.guild):
        await ctx.send(embed=send_wrong_server_embed())
        return
    if not is_whitelisted(ctx.author.id):
        await ctx.send(embed=send_unauthorized_embed())
        return

    if mode_or_email and mode_or_email.lower() == 'random':
        await freeusercreate_random_cmd(ctx)
        return

    email = mode_or_email
    if not email or not username or not password:
        await ctx.send("💡 Usage:\n`/freeusercreate-random` - Generate random account instantly\n`/usercreate <email> <username> <password>` - Create custom account")
        return

    try:
        res = await create_panel_user_api(email, username, password, panel_type="free")
        panel_url = os.getenv("FREE_PANEL_URL", "https://free.nexahostings.in")
        user_attr = res.get("attributes", {})
        user_id = user_attr.get("id", "N/A")

        embed = discord.Embed(
            title="🎉 Free Panel User Account Created!",
            description=f"Successfully created user account on **Free Panel** ID `{user_id}`.",
            color=discord.Color.green()
        )
        embed.add_field(name="📧 Email", value=f"`{email}`", inline=True)
        embed.add_field(name="👤 Username", value=f"`{username}`", inline=True)
        embed.add_field(name="🔑 Password", value=f"`{password}`", inline=True)
        embed.add_field(name="🌐 Free Panel URL", value=f"[Open Free Panel]({panel_url})", inline=False)

        account_data = {
            "panel_type": "free",
            "panel_url": panel_url,
            "email": email,
            "username": username,
            "password": password,
            "user_id": user_id,
            "created_by": ctx.author.name
        }
        link_view = LinkWithUserView("account", account_data)
        msg = await ctx.send(embed=format_author_footer(embed, ctx.author), view=link_view)
        link_view.message = msg
    except Exception as e:
        await ctx.send(f"❌ Panel User Creation Failed: {e}")

@bot.command(name='wl')
async def whitelist_cmd(ctx, user: discord.User):
    if not is_allowed_server(ctx.guild):
        await ctx.send(embed=send_wrong_server_embed())
        return
    if ctx.author.id != ADMIN_USER_ID:
        embed = discord.Embed(title="WL Manager", description="`❌` **Only the bot owner can use this command.**", color=discord.Color(0x17004e))
        await ctx.send(embed=format_author_footer(embed, ctx.author))
        return
    added = add_to_whitelist(user.id)
    msg = f"`✅` **User {user.mention} (`{user.id}`) added to whitelist.**" if added else f"`✅` **User {user.mention} is already whitelisted.**"
    embed = discord.Embed(title="WL Manager", description=msg, color=discord.Color(0x17004e))
    await ctx.send(embed=format_author_footer(embed, ctx.author))

@bot.command(name='unwl')
async def unwhitelist_cmd(ctx, user: discord.User):
    if not is_allowed_server(ctx.guild):
        await ctx.send(embed=send_wrong_server_embed())
        return
    if ctx.author.id != ADMIN_USER_ID:
        embed = discord.Embed(title="WL Manager", description="`❌` **Only the bot owner can use this command.**", color=discord.Color(0x17004e))
        await ctx.send(embed=format_author_footer(embed, ctx.author))
        return
    removed = remove_from_whitelist(user.id)
    msg = f"`✅` **User {user.mention} (`{user.id}`) removed from whitelist.**" if removed else f"`❌` **User {user.mention} is not in whitelist.**"
    embed = discord.Embed(title="WL Manager", description=msg, color=discord.Color(0x17004e))
    await ctx.send(embed=format_author_footer(embed, ctx.author))

@bot.command(name='cmd')
async def command_panel(ctx):
    if not is_allowed_server(ctx.guild):
        await ctx.send(embed=send_wrong_server_embed())
        return
    if not is_whitelisted(ctx.author.id):
        await ctx.send(embed=send_unauthorized_embed())
        return
    embed = discord.Embed(
        title="Unified Commands Panel (Server Locked)",
        description=(
            "**🔄 System Commands:**\n"
            "1. `/reloaduserlist` → Force reload Free/Paid user lists & whitelist\n\n"
            "**💎 Paid Panel Commands:**\n"
            "2. `/paidusercreate-random` → Generate random paid panel user\n"
            "3. `/paidusercreate` → Create paid panel user (email, username, pass)\n"
            "4. `/paidservercreate` → Create paid panel server (select node, auto IP + 2 backups)\n\n"
            "**🖥️ Free Panel Commands:**\n"
            "5. `/freeservercreate <email> <ram> <cpu> <disk>` → Create free panel server (select node)\n"
            "6. `/freeusercreate-random` → Generate random free panel user\n"
            "7. `/usercreate` → Create free panel user\n\n"
            "**💳 UPI QR Commands:**\n"
            "8. `/upi-set` → Configure 4 UPI slots via popup modals\n"
            "9. `/qr` → Generate payment QR code for ₹300, ₹500, etc.\n"
            "10. `/myupi` → View stored UPI slots\n"
            "11. `300` (type number) → Direct custom QR code generation\n\n"
            "**⚙️ Management & Utility Commands:**\n"
            "12. `/ping` → Displays bot latency\n"
            "13. `/linked-info @user` → View linked panel accounts & servers\n"
            "14. `/servers` → Show servers list where bot is present\n"
            "15. `/get <server_id>` → Get server invite link\n"
            "16. `/wl @user` / `/unwl @user` → Whitelist manager"
        ),
        color=discord.Color(0x17004e)
    )
    await ctx.send(embed=format_author_footer(embed, ctx.author))

@bot.command(name='ping')
async def ping_cmd(ctx):
    if not is_allowed_server(ctx.guild):
        await ctx.send(embed=send_wrong_server_embed())
        return
    if not is_whitelisted(ctx.author.id):
        await ctx.send(embed=send_unauthorized_embed())
        return
    latency = round(bot.latency * 1000)
    embed = discord.Embed(title="Bot Latency", description=f"`🤖` Latency is `{latency}ms`.", color=discord.Color(0x17004e))
    await ctx.send(embed=format_author_footer(embed, ctx.author))

@bot.command(name='servers')
async def show_servers_cmd(ctx):
    if not is_allowed_server(ctx.guild):
        await ctx.send(embed=send_wrong_server_embed())
        return
    if not is_whitelisted(ctx.author.id):
        await ctx.send(embed=send_unauthorized_embed())
        return

    guilds_info = [{'name': g.name, 'id': g.id, 'members_count': len(g.members)} for g in bot.guilds]
    guilds_info.sort(key=lambda x: x['members_count'], reverse=True)
    embed = discord.Embed(title="Servers List", description="Servers where bot is present:", color=discord.Color(0x17004e))
    for info in guilds_info:
        embed.add_field(name=f"- {info['name']} (ID: {info['id']})", value=f" - Members: {info['members_count']}", inline=False)
    await ctx.send(embed=format_author_footer(embed, ctx.author))

@bot.command(name='get')
async def get_server_invite_cmd(ctx, server_id: int):
    if not is_allowed_server(ctx.guild):
        await ctx.send(embed=send_wrong_server_embed())
        return
    if not is_whitelisted(ctx.author.id):
        await ctx.send(embed=send_unauthorized_embed())
        return

    server = bot.get_guild(server_id)
    if server is None:
        embed = discord.Embed(title="Server Invite Manager", description=f"`❌` Server `{server_id}` not found.", color=discord.Color(0x17004e))
        await ctx.send(embed=format_author_footer(embed, ctx.author))
        return

    try:
        text_channel = next((c for c in server.text_channels if c.permissions_for(server.me).create_instant_invite), None) or server.text_channels[0]
        invite = await text_channel.create_invite(max_uses=1, unique=True)
        embed = discord.Embed(title="Server Invite Manager", description=f"`✅` **Invitation for server `{server_id}`:**\n{invite.url}", color=discord.Color(0x17004e))
    except Exception as e:
        embed = discord.Embed(title="Server Invite Manager", description=f"`❌` Unable to create invite: {e}", color=discord.Color(0x17004e))

    await ctx.send(embed=format_author_footer(embed, ctx.author))

@bot.command(name='linkedinfo', aliases=['links', 'userlinks'])
async def linkedinfo_cmd(ctx, user: discord.User = None):
    if not is_allowed_server(ctx.guild):
        await ctx.send(embed=send_wrong_server_embed())
        return
    if not is_whitelisted(ctx.author.id):
        await ctx.send(embed=send_unauthorized_embed())
        return

    target = user or ctx.author
    data = storage.get_user_linked_items(target.id)
    accounts = data.get("accounts", [])
    servers = data.get("servers", [])

    embed = discord.Embed(
        title=f"🔗 Linked Pterodactyl Details for {target.name}",
        description=f"Showing all accounts and servers linked to {target.mention} (`{target.id}`).",
        color=discord.Color(0x17004e)
    )

    if not accounts and not servers:
        embed.add_field(name="ℹ️ Status", value="No accounts or servers are currently linked to this user.", inline=False)
    else:
        if accounts:
            acc_lines = []
            for idx, acc in enumerate(accounts, 1):
                ptype = acc.get("panel_type", "free").capitalize()
                email = acc.get("email", "N/A")
                uname = acc.get("username", "N/A")
                pwd = acc.get("password", "N/A")
                acc_lines.append(f"**{idx}. [{ptype} Panel]** `{email}` (`{uname}`) | Pass: `{pwd}`")
            embed.add_field(name=f"👤 Linked Accounts ({len(accounts)})", value="\n".join(acc_lines)[:1024], inline=False)

        if servers:
            srv_lines = []
            for idx, srv in enumerate(servers, 1):
                ptype = srv.get("panel_type", "free").capitalize()
                sname = srv.get("name", "Nexa Server")
                sid = srv.get("server_id", "N/A")
                ip = srv.get("alloc_ip", "N/A")
                port = srv.get("alloc_port", "N/A")
                srv_lines.append(f"**{idx}. [{ptype} Panel] {sname}** (ID: `{sid}`) → `{ip}:{port}`")
            embed.add_field(name=f"🖥️ Linked Servers ({len(servers)})", value="\n".join(srv_lines)[:1024], inline=False)

    await ctx.send(embed=format_author_footer(embed, ctx.author))



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

        if not is_whitelisted(message.author.id):
            await message.reply(embed=send_unauthorized_embed())
            return

        configured = storage.get_configured_slots(message.author.id)
        if not configured:
            await message.reply("💡 You entered an amount, but no UPI ID is saved yet! Use `/upi-set` to save your UPI ID first.")
        elif len(configured) == 1:
            upi_url = upi_utils.build_upi_url(configured[0]["upiId"], extracted_amt, configured[0]["name"])
            qr_bytes = upi_utils.generate_qr_bytes(upi_url)
            file = discord.File(io.BytesIO(qr_bytes), filename=f"upi_qr_{extracted_amt}.png")

            embed = discord.Embed(title="⚡ Custom Value UPI QR Generated", color=discord.Color.green())
            embed.add_field(name="💵 Amount", value=f"**₹{extracted_amt}**", inline=True)
            embed.add_field(name="💳 UPI ID", value=f"`{configured[0]['upiId']}`", inline=True)
            embed.set_image(url=f"attachment://upi_qr_{extracted_amt}.png")

            await message.reply(embed=embed, file=file)
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
