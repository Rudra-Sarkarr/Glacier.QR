# ⚡ Glacier.QR - UPI QR, Invoicing & Staff Whitelist Discord Bot

[![Discord.js](https://img.shields.io/badge/Discord.py-v2.0-blue.svg)](https://discordpy.readthedocs.io/)
[![Python](https://img.shields.io/badge/Python-%3E%3D%203.9-green.svg)](https://www.python.org/)
[![Database](https://img.shields.io/badge/Database-JSON%20Storage-lightblue.svg)](storage.py)
[![Email](https://img.shields.io/badge/Email-SMTP%20SSL-orange.svg)](mailer.py)
[![License](https://img.shields.io/badge/License-MIT-purple.svg)](LICENSE)

> High-performance Discord bot featuring multi-slot custom UPI QR payment collection, one-click UPI app redirects, automated SMTP SSL email invoicing, admin verification alerts, and staff whitelist security lockdown.

---

## Description

**Glacier.QR** is a lightweight, modern Discord bot designed for communities, server hosts, and store managers in India to seamlessly manage payments, invoice customers via email, and maintain strict administrative access control.

It provides a multi-slot **UPI QR Code Payment Generator** supporting custom amounts (such as quick amount buttons or typing `300` directly in chat), one-click deep link redirection to installed UPI apps (GPay, PhonePe, Paytm, BHIM), and an automated **Payment Verification & Email Invoicing System** connected to your SMTP SSL server.

---

## Key Features

- **💳 Multi-Slot Custom Value UPI QR Generator**: Store up to 4 UPI IDs via popup modals and generate instant QR codes for custom amounts.
- **⚡ Direct Number Entry in Chat**: Type any number (e.g. `300` or `₹500`) to render a payment QR code directly in chat.
- **📲 One-Click UPI App Redirect**: Direct intent links and deep link redirection buttons allowing customers to open Google Pay, PhonePe, or Paytm with a single tap.
- **📧 Automated Email Invoicing & Receipts (SMTP SSL)**:
  - When a customer clicks **Payment Done**, they submit their Name, Email, and UTR number via a popup modal.
  - An instant **Invoice (Pending Verification)** is dispatched to their email address.
  - When the administrator reviews and approves the payment, an official **Payment Confirmed Receipt** email is automatically sent.
  - If rejected, an explanatory **Payment Not Received** email is sent.
- **🔔 Admin Verification Alert Workflow**: Admins receive instant interactive alerts with `✅ Payment Received` and `❌ Reject` buttons with automatic Discord DM notifications sent to the customer.
- **🔒 Guild Lockdown & Whitelist Security**: Restricts bot execution to a designated Server ID with an authorized staff whitelist (`/wl`, `/unwl`).
- **🔄 Live Auto-Reload Background Sync**: 5-second asynchronous sync loop keeping staff whitelists and status presence up to date.

---

## 🔄 Payment & Verification Flow

```text
1. QR Generation ──> Admin/User generates QR (via /qr or typing '300' in chat)
2. One-Click Pay ──> Customer taps '📱 Open UPI App' or scans QR code
3. Payment Done  ──> Customer clicks '✅ Payment Done' and confirms
4. Modal Form    ──> Customer enters Name, Email, and 12-digit UTR Number
5. Email Invoice ──> System immediately emails a Pending Verification Invoice
6. Admin Alert   ──> Admin receives verification embed with [Approve] / [Reject] buttons
7. Decision      ──> Admin reviews bank statement and taps [Payment Received] or [Reject]
8. Final Email   ──> System emails confirmed receipt (or rejection notice) & DMs user
```

---

## Getting Started

### Dependencies

* **Operating System**: Windows 10/11, Linux (Ubuntu, Debian, CentOS), or macOS
* **Python**: Version `3.9` or higher
* **Python Libraries**:
  * `discord.py` (v2.0+)
  * `qrcode` & `Pillow` (for dynamic QR image rendering)
  * `python-dotenv` (for secure environment variable handling)

### Installing

1. **Clone the repository**:
   ```bash
   git clone https://github.com/Rudra-Sarkarr/Glacier.QR.git
   cd Glacier.QR
   ```

2. **Install required Python dependencies**:
   ```bash
   pip install -r requirements.txt
   ```
   *(or: `pip install discord.py qrcode pillow python-dotenv aiohttp`)*

3. **Configure Environment Variables**:
   Copy `.env.example` to `.env`:
   ```bash
   cp .env.example .env
   ```

4. **Edit `.env` with your configuration**:
   ```env
   # DISCORD BOT CONFIGURATION
   DISCORD_BOT_TOKEN=your_discord_bot_token_here
   ALLOWED_GUILD_ID=your_discord_server_guild_id_here
   ADMIN_USER_ID=your_discord_user_id_here

   # (Optional) Dedicated Discord Channel ID for Staff Verification Alerts
   PAYMENT_LOG_CHANNEL_ID=0

   # SMTP EMAIL CONFIGURATION
   SMTP_HOST=host3.xhost.co.in
   SMTP_PORT=465
   SMTP_USER=your_smtp_user@example.com
   SMTP_PASSWORD=your_actual_smtp_password_here
   SMTP_FROM=your_smtp_user@example.com
   SMTP_FROM_NAME=Glacier.QR Payments
   ```

### Executing program

* **Start the Discord bot**:
  ```bash
  python bot.py
  ```
  *(on Windows: `py bot.py`)*

* **Step-by-step verification**:
  1. Ensure the bot console displays successful connection to the Discord Gateway and reports SMTP Invoicing Active.
  2. Verify slash command synchronization in your authorized Discord guild.
  3. Type `/ping` to confirm bot responsiveness and latency.
  4. Run `/upi-set` to configure your payment slots or `/cmd` to view all available commands.

---

## 📜 Commands Reference

| Command | Category | Description |
| :--- | :--- | :--- |
| `/ping` | Utility | Display current bot latency in milliseconds |
| `/wl` / `/unwl` | Admin | Add or remove server members from the staff whitelist |
| `/cmd` | Utility | Display full interactive commands control panel |
| `/upi-set` | UPI QR | Configure up to 4 stored UPI ID slots via modal popup dialogs |
| `/qr` | UPI QR | Select slot & amount to render payment QR code |
| `/myupi` | UPI QR | View all currently configured UPI ID slots |

---

## Help

### Common Issues & Solutions

* **Bot not responding to Slash Commands**:
  * Ensure the Discord Bot has been invited with `applications.commands` and `bot` scopes.
  * Verify that the bot is running inside the server specified by `ALLOWED_GUILD_ID`.
  * Ensure your Discord user ID is added to `ADMIN_USER_ID` or whitelisted via `/wl`.

* **Emails not being delivered**:
  * Check that `SMTP_PASSWORD` is properly set in `.env`.
  * Ensure port 465 is not blocked by your hosting provider or firewall.
  * Check the bot console logs for any SMTP authentication or connection errors.

### Helper Commands
To view the live command list and interactive help panel inside Discord, run:
```text
/cmd
```
or
```text
/help
```

---

## Authors

* **Rudra Sarkar** — Project Creator & Lead Developer
  * GitHub: [@Rudra-Sarkarr](https://github.com/Rudra-Sarkarr)
  * Email: [rudrasarkar7869@gmail.com](mailto:rudrasarkar7869@gmail.com)

---

## License

This project is licensed under the **MIT License** — see the [LICENSE](LICENSE) file for details.

---

## Acknowledgments

* [discord.py](https://github.com/Rapptz/discord.py) — Modern, easy-to-use Python library for Discord bots.
* [qrcode](https://github.com/lincolnloop/python-qrcode) & [Pillow](https://python-pillow.org/) — Python QR image rendering engine.
* [Awesome README](https://github.com/matiassingers/awesome-readme)
