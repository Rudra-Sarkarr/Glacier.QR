# ⚡ PteroLink

[![Discord.js](https://img.shields.io/badge/Discord.js-v14-blue.svg)](https://discord.js.org/)
[![Node.js](https://img.shields.io/badge/Node.js-%3E%3D%2018.0.0-green.svg)](https://nodejs.org/)
[![Database](https://img.shields.io/badge/Database-SQLite3-lightblue.svg)](https://www.sqlite.org/)
[![Wiki Documentation](https://img.shields.io/badge/Documentation-Official%20Wiki-007ACC?style=flat-square&logo=github)](https://github.com/Rudra-Sarkarr/Tickxa-Ticket-Manager/wiki)
[![Powered By NexaHostings](https://img.shields.io/badge/Powered%20By-NexaHostings-FF6B6B?style=flat-square&logo=rocket)](https://www.nexahostings.in)
[![Join Discord](https://img.shields.io/badge/Discord-Join%20NexaHostings-5865F2?style=flat-square&logo=discord&logoColor=white)](https://discord.gg/tjwNTGwm8k)
[![License](https://img.shields.io/badge/License-MIT-purple.svg)](LICENSE)

> High-performance Discord bot bridging Dual Pterodactyl Panel provisioning, interactive Discord member linking with automated DM delivery, multi-slot custom UPI QR payments, and staff whitelist security.

---

## Description

**PteroLink** is an enterprise-grade Discord Slash Command Bot designed for game server hosts, community managers, and Pterodactyl panel administrators. It streamlines server provisioning, user onboarding, and payment collections directly inside your Discord server.

With **PteroLink**, administrators can provision game servers on both **Free and Paid Pterodactyl Panels** with customizable resource limits (RAM, CPU, Disk, Backups), dynamic live node selection, and automatic IP/port allocation. Whenever an account or server is provisioned, the bot offers an interactive **"Link with User"** option that connects the Pterodactyl entity to a Discord member and automatically delivers login credentials or server connection information directly to their DMs. Additionally, PteroLink includes a multi-slot **UPI QR Code Payment Generator** supporting custom amounts (e.g. typing `300` in chat or running `/qr`), strict server lockdown, and live 5-second background synchronization loops.

---

## Key Features

- **💎 Dual Pterodactyl Panel Integration (Free & Paid)**: Seamlessly create user accounts and provision servers with auto IP/Port allocation and 2 default backups.
- **🔗 One-Click "Link with User" & Auto-DM**: Interactive UI dropdown to link provisioned accounts/servers to Discord users with instant DM delivery of credentials.
- **🖥️ Dynamic Node Autocomplete**: Real-time interactive node selection during server creation.
- **💳 Multi-Slot Custom Value UPI QR Generator**: Store up to 4 UPI IDs via popup modals and generate instant QR codes for custom amounts.
- **🔒 Guild Lockdown & Whitelist Security**: Restricts bot execution to a designated Server ID with an authorized staff whitelist (`/wl`, `/unwl`).
- **🔄 Live Auto-Reload Background Sync**: 5-second asynchronous sync loop keeping panel users and staff whitelists up to date.

---

## Getting Started

### Dependencies

* **Operating System**: Windows 10/11, Linux (Ubuntu, Debian, CentOS), or macOS
* **Python**: Version `3.9` or higher
* **Python Libraries**:
  * `discord.py` (v2.0+)
  * `qrcode` & `Pillow` (for dynamic QR image rendering)
  * `python-dotenv` (for secure environment variable handling)
* **Pterodactyl Panel**: Version `1.x` with Application API keys enabled

### Installing

1. **Clone the repository**:
   ```bash
   git clone https://github.com/Rudra-Sarkarr/PteroLink.git
   cd PteroLink
   ```

2. **Install required Python dependencies**:
   ```bash
   pip install -r requirements.txt
   ```
   *(or manually: `pip install discord.py qrcode pillow python-dotenv`)*

3. **Configure Environment Variables**:
   Copy the `.env.example` file to `.env`:
   ```bash
   cp .env.example .env
   ```

4. **Edit `.env` with your configuration**:
   ```env
   # DISCORD BOT CONFIGURATION
   DISCORD_BOT_TOKEN=your_discord_bot_token_here
   ALLOWED_GUILD_ID=your_discord_server_guild_id_here
   ADMIN_USER_ID=your_discord_user_id_here

   # FREE PTERODACTYL PANEL CONFIGURATION
   FREE_PANEL_URL=https://free.yourpanel.com/
   FREE_PANEL_API_KEY=ptla_your_free_panel_application_api_key

   # PAID PTERODACTYL PANEL CONFIGURATION
   PAID_PANEL_URL=https://paid.yourpanel.com/
   PAID_PANEL_API_KEY=ptla_your_paid_panel_application_api_key
   ```

### Executing program

* **Start the Discord bot**:
  ```bash
  python bot.py
  ```
  *(on Windows: `py bot.py`)*

* **Step-by-step verification**:
  1. Ensure the bot console displays successful connection to the Discord Gateway.
  2. Verify slash command synchronization in your authorized Discord guild.
  3. Type `/ping` to confirm bot responsiveness and latency.
  4. Run `/upi-set` to configure your payment slots or `/help` to see all available commands.

---

## 📜 Commands Reference

| Command | Category | Description |
| :--- | :--- | :--- |
| `/reloaduserlist` | System | Force reload Free/Paid user lists & whitelist cache |
| `/paidusercreate-random` | Paid Panel | Automatically generate a random user account on Paid Panel |
| `/paidusercreate` | Paid Panel | Create a custom user account on Paid Panel |
| `/paidservercreate` | Paid Panel | Provision a server on Paid Panel with node select, auto IP & 2 backups |
| `/freeusercreate-random` | Free Panel | Automatically generate a random user account on Free Panel |
| `/usercreate` | Free Panel | Create a custom user account on Free Panel |
| `/freeservercreate` | Free Panel | Provision a server on Free Panel with node select, auto IP & 2 backups |
| `/upi-set` | UPI QR | Configure up to 4 stored UPI ID slots via modal popup dialogs |
| `/qr` | UPI QR | Select slot & amount to render payment QR code |
| `/myupi` | UPI QR | View all currently configured UPI ID slots |
| `/linked-info` | Admin | View all Pterodactyl accounts and servers linked to a Discord user |
| `/wl` / `/unwl` | Admin | Add or remove server members from the staff whitelist |
| `/cmd` | Utility | Display full interactive commands control panel |
| `/ping` | Utility | Display current bot latency in milliseconds |

---

## Help

### Common Issues & Solutions

* **Bot not responding to Slash Commands**:
  * Ensure the Discord Bot has been invited with `applications.commands` and `bot` scopes.
  * Verify that the bot is running inside the server specified by `ALLOWED_GUILD_ID`.
  * Ensure your Discord user ID is added to `ADMIN_USER_ID` or whitelisted via `/wl`.

* **Pterodactyl API Connection Errors (401 / 403 / 404 / 500)**:
  * Check that `FREE_PANEL_URL` and `PAID_PANEL_URL` include `https://` with no trailing spaces.
  * Confirm that your API key is an **Application API Key** (starts with `ptla_`), NOT an Account API Key (`ptlc_`).
  * Ensure the API key has full read/write permissions for Users, Servers, Nodes, and Allocations.

* **User did not receive credentials in Direct Message (DM)**:
  * Discord users must allow direct messages from server members (Privacy Settings > Direct Messages).
  * If DMs are disabled for the member, the admin receives a warning embed and the link remains recorded in the database.

### Helper Commands
To view the live command list and interactive help panel inside Discord, run:
```text
/help
```
or
```text
/cmd
```

---

## Authors

* **Rudra Sarkar** — Project Creator & Lead Developer
  * GitHub: [@Rudra-Sarkarr](https://github.com/Rudra-Sarkarr)
  * Email: [rudrasarkar7869@gmail.com](mailto:rudrasarkar7869@gmail.com)

---

## Version History

* **v1.1** *(Current)*
  * Added interactive **"Link with User"** UI component with auto DM credential & connection delivery.
  * Added `/linked-info` admin command for inspecting linked accounts & servers.
  * Enhanced multi-panel server provisioning and allocation handlers.
  * Rebranded project to **PteroLink**.
  * Removed legacy mass/direct DM commands in favor of targeted user linking.
* **v1.0**
  * Initial Release: Dual Pterodactyl panel integration, dynamic node autocomplete, multi-slot UPI QR generator, and whitelist lockdown.

---

## License

This project is licensed under the **MIT License** — see the [LICENSE](LICENSE) file for details.

---

## Acknowledgments

* [discord.py](https://github.com/Rapptz/discord.py) — Modern, easy-to-use Python library for Discord bots.
* [Pterodactyl](https://pterodactyl.io/) — Open-source game server management panel.
* [qrcode](https://github.com/lincolnloop/python-qrcode) & [Pillow](https://python-pillow.org/) — Python QR image rendering engine.
* [Awesome README](https://github.com/matiassingers/awesome-readme)
