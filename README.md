# ⚡ NexaHostings Unified Discord Bot v1

A feature-rich, high-performance **Discord Slash Command Bot** integrating **Pterodactyl Panel API** (Free & Paid Panels), **Dynamic Node Selection**, **Auto IP Allocation**, **Multi-Slot Custom Value UPI QR Payment Generator**, and **Private Whitelist Administration**.

---

## 🔥 Key Features

- **💎 Dual Pterodactyl Panel Integration (Free & Paid)**:
  - Account Creation (`/usercreate`, `/freeusercreate-random`, `/paidusercreate`, `/paidusercreate-random`).
  - Server Provisioning (`/freeservercreate`, `/paidservercreate`) with RAM/CPU/Disk limits, 2 default backups, and automatic unassigned IP/Port allocation.
- **🖥️ Dynamic Node Selection**:
  - Live pop-up autocomplete for selecting specific panel nodes during server creation.
- **💳 Multi-Slot Custom Value UPI QR Generator**:
  - Configure up to 4 UPI ID slots using pop-up modal dialogs (`/upi-set`).
  - Generate instant QR codes for custom amounts (`/qr` or typing `300` directly in chat).
- **🔒 Private Mode & Guild Lockdown**:
  - Restricted to specific Discord Server Guild ID.
  - Whitelist security system (`/wl`, `/unwl`) allowing only authorized members to run commands.
- **📢 Public Channel Announcement Mode**:
  - Server and User creation embeds post directly to the channel for public visibility.
- **🔄 Mandatory 5-Second Auto-Reload Loop**:
  - Automatically syncs Pterodactyl Panel users and local whitelist every 5 seconds in the background.

---

## 🛠️ Prerequisites

- Python 3.9+
- `discord.py` v2.0+
- `qrcode`, `Pillow`, `python-dotenv`

---

## 🚀 Quick Setup Instructions

1. **Clone the repository**:
   ```bash
   git clone https://github.com/your-username/nexahostings-bot.git
   cd nexahostings-bot
   ```

2. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```
   *(or `pip install discord.py qrcode pillow python-dotenv`)*

3. **Configure Environment Variables**:
   Copy `.env.example` to `.env` and fill in your credentials:
   ```bash
   cp .env.example .env
   ```

   Edit `.env`:
   ```env
   # DISCORD BOT CONFIGURATION
   DISCORD_BOT_TOKEN=your_discord_bot_token_here
   ALLOWED_GUILD_ID=your_discord_server_guild_id_here
   ADMIN_USER_ID=your_discord_user_id_here

   # FREE PTERODACTYL PANEL CONFIGURATION
   FREE_PANEL_URL=https://your_panel_url/
   FREE_PANEL_API_KEY=your_free_panel_application_api_key_here

   # PAID PTERODACTYL PANEL CONFIGURATION
   PAID_PANEL_URL=https://your_panel_url/
   PAID_PANEL_API_KEY=your_paid_panel_application_api_key_here
   ```

4. **Run the Bot**:
   ```bash
   python3 bot.py
   ```

---

## 📜 Commands List

| Command | Category | Description |
| :--- | :--- | :--- |
| `/reloaduserlist` | System | Force reload Free/Paid user lists & whitelist |
| `/paidusercreate-random` | Paid Panel | Generate random user account on Paid Panel |
| `/paidusercreate` | Paid Panel | Create custom user account on Paid Panel |
| `/paidservercreate` | Paid Panel | Create server on Paid Panel with node select, auto IP & 2 backups |
| `/freeusercreate-random` | Free Panel | Generate random user account on Free Panel |
| `/usercreate` | Free Panel | Create custom user account on Free Panel |
| `/freeservercreate` | Free Panel | Create server on Free Panel with node select, auto IP & 2 backups |
| `/upi-set` | UPI QR | Configure 4 stored UPI ID slots via pop-up modals |
| `/qr` | UPI QR | Select slot & amount to render payment QR code |
| `/myupi` | UPI QR | View stored UPI ID slots |
| `/dm` | Admin | Direct message a specified server member |
| `/dmall` | Admin | Broadcast direct message to server members |
| `/wl` / `/unwl` | Admin | Add or remove members from whitelist |
| `/cmd` | Utility | Show full interactive commands panel |
| `/ping` | Utility | Display bot latency |

---

## 🔒 Security & Privacy

- All sensitive keys (`DISCORD_BOT_TOKEN`, `PANEL_API_KEY`) are managed securely via environment variables (`.env`).
- Never commit your `.env` or `wl.txt` file to public repositories.

---

## 📄 License
Distributed under the MIT License.
