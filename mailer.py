import os
import sys
import smtplib
import asyncio
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
from dotenv import load_dotenv

if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace', line_buffering=True)
    except Exception:
        pass

load_dotenv(override=True)

def get_smtp_config():
    load_dotenv(override=True)
    return {
        "host": os.getenv("SMTP_HOST", "host3.xhost.co.in"),
        "port": int(os.getenv("SMTP_PORT", "465")),
        "user": os.getenv("SMTP_USER", "").strip(),
        "password": os.getenv("SMTP_PASSWORD", "").strip(),
        "from_addr": os.getenv("SMTP_FROM", "").strip(),
        "from_name": os.getenv("SMTP_FROM_NAME", "Glacier.QR Payments")
    }


def _get_base_email_template(title: str, badge_html: str, content_html: str, footer_note: str = "") -> str:
    current_year = datetime.now().year
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{title}</title>
  <style>
    body {{
      margin: 0;
      padding: 0;
      background-color: #0f172a;
      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;
      color: #e2e8f0;
    }}
    .wrapper {{
      width: 100%;
      background-color: #0f172a;
      padding: 40px 15px;
    }}
    .card {{
      max-width: 580px;
      margin: 0 auto;
      background: #1e293b;
      border: 1px solid #334155;
      border-radius: 16px;
      overflow: hidden;
      box-shadow: 0 10px 25px rgba(0, 0, 0, 0.4);
    }}
    .header {{
      background: linear-gradient(135deg, #3b82f6 0%, #1d4ed8 100%);
      padding: 30px;
      text-align: center;
    }}
    .header h1 {{
      margin: 0;
      color: #ffffff;
      font-size: 26px;
      font-weight: 700;
      letter-spacing: -0.5px;
    }}
    .header p {{
      margin: 6px 0 0;
      color: #bfdbfe;
      font-size: 14px;
    }}
    .content {{
      padding: 32px 28px;
    }}
    .status-container {{
      text-align: center;
      margin-bottom: 24px;
    }}
    .badge {{
      display: inline-block;
      padding: 8px 18px;
      border-radius: 9999px;
      font-size: 13px;
      font-weight: 700;
      letter-spacing: 0.5px;
      text-transform: uppercase;
    }}
    .badge-pending {{
      background-color: rgba(234, 179, 8, 0.15);
      color: #facc15;
      border: 1px solid #ca8a04;
    }}
    .badge-success {{
      background-color: rgba(34, 197, 94, 0.15);
      color: #4ade80;
      border: 1px solid #16a34a;
    }}
    .badge-rejected {{
      background-color: rgba(239, 68, 68, 0.15);
      color: #f87171;
      border: 1px solid #dc2626;
    }}
    .details-table {{
      width: 100%;
      border-collapse: collapse;
      margin-top: 20px;
      background-color: #0f172a;
      border-radius: 12px;
      overflow: hidden;
      border: 1px solid #334155;
    }}
    .details-table td {{
      padding: 14px 18px;
      font-size: 14px;
      border-bottom: 1px solid #1e293b;
    }}
    .details-table tr:last-child td {{
      border-bottom: none;
    }}
    .label {{
      color: #94a3b8;
      width: 40%;
      font-weight: 500;
    }}
    .value {{
      color: #f8fafc;
      font-weight: 600;
      text-align: right;
    }}
    .amount-highlight {{
      font-size: 20px;
      color: #38bdf8;
      font-weight: 700;
    }}
    .footer {{
      padding: 20px 30px;
      background-color: #0f172a;
      text-align: center;
      border-top: 1px solid #334155;
      font-size: 12px;
      color: #64748b;
    }}
  </style>
</head>
<body>
  <div class="wrapper">
    <div class="card">
      <div class="header">
        <h1>⚡ Glacier.QR</h1>
        <p>Automated Billing & Payment Receipt System</p>
      </div>
      <div class="content">
        <div class="status-container">
          {badge_html}
        </div>
        {content_html}
      </div>
      <div class="footer">
        <p>{footer_note or "This is an automated notification. Please do not reply directly to this email."}</p>
        <p>&copy; {current_year} Glacier.QR. All rights reserved.</p>
      </div>
    </div>
  </div>
</body>
</html>
"""


def _send_smtp_ssl(to_email: str, subject: str, html_body: str, text_body: str = "") -> bool:
    """Send an email using SMTP SSL (Port 465)."""
    cfg = get_smtp_config()
    host = cfg["host"]
    port = cfg["port"]
    user = cfg["user"]
    password = cfg["password"]
    from_addr = cfg["from_addr"]
    from_name = cfg["from_name"]

    if not password:
        print(f"[Mailer] ⚠️ Cannot send email to {to_email}: SMTP_PASSWORD is not set in .env! Please configure SMTP_PASSWORD.", flush=True)
        return False

    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = f"{from_name} <{from_addr}>"
        msg["To"] = to_email

        if text_body:
            msg.attach(MIMEText(text_body, "plain", "utf-8"))
        msg.attach(MIMEText(html_body, "html", "utf-8"))

        with smtplib.SMTP_SSL(host, port, timeout=15) as server:
            server.login(user, password)
            server.sendmail(from_addr, [to_email], msg.as_string())

        try:
            print(f"[Mailer] Successfully sent '{subject}' to {to_email} via {host}:{port}", flush=True)
        except Exception:
            pass
        return True
    except Exception as e:
        try:
            print(f"[Mailer] Failed to send email to {to_email}: {e}", flush=True)
        except Exception:
            pass
        return False


async def send_invoice_email(
    to_email: str,
    customer_name: str,
    tx_id: str,
    amount: str,
    payee_name: str,
    upi_id: str,
    utr: str,
    date_str: str = ""
) -> bool:
    """Dispatches the initial invoice confirming payment submission (Pending Verification)."""
    if not date_str:
        date_str = datetime.now().strftime("%d %b %Y, %I:%M %p")

    title = f"Invoice - Payment Pending: ₹{amount}"
    badge_html = '<span class="badge badge-pending">🟡 Payment Submitted - Pending Verification</span>'
    content_html = f"""
      <p style="font-size: 15px; color: #cbd5e1; line-height: 1.6; margin-top: 0;">
        Hello <strong>{customer_name}</strong>,<br>
        Thank you for submitting your payment confirmation. Your transaction has been recorded and is currently awaiting staff verification.
      </p>
      <table class="details-table">
        <tr>
          <td class="label">Invoice / TXN ID</td>
          <td class="value"><code>{tx_id}</code></td>
        </tr>
        <tr>
          <td class="label">Submission Date</td>
          <td class="value">{date_str}</td>
        </tr>
        <tr>
          <td class="label">Payee</td>
          <td class="value">{payee_name}</td>
        </tr>
        <tr>
          <td class="label">Receiving UPI ID</td>
          <td class="value"><code>{upi_id}</code></td>
        </tr>
        <tr>
          <td class="label">UTR / Reference No</td>
          <td class="value"><code>{utr or 'N/A'}</code></td>
        </tr>
        <tr>
          <td class="label">Total Amount</td>
          <td class="value amount-highlight">₹{amount}</td>
        </tr>
      </table>
      <p style="font-size: 13px; color: #94a3b8; margin-top: 24px; line-height: 1.5;">
        ⏳ Our administrators have been notified. Once your payment is verified, you will receive a final confirmation receipt.
      </p>
    """
    html_body = _get_base_email_template(title, badge_html, content_html)
    return await asyncio.to_thread(_send_smtp_ssl, to_email, title, html_body)


async def send_payment_received_email(
    to_email: str,
    customer_name: str,
    tx_id: str,
    amount: str,
    payee_name: str,
    upi_id: str,
    utr: str,
    date_str: str = ""
) -> bool:
    """Dispatches the confirmed payment receipt when Admin approves."""
    if not date_str:
        date_str = datetime.now().strftime("%d %b %Y, %I:%M %p")

    title = f"Payment Confirmed - Receipt for ₹{amount}"
    badge_html = '<span class="badge badge-success">✅ Payment Received & Verified</span>'
    content_html = f"""
      <p style="font-size: 15px; color: #cbd5e1; line-height: 1.6; margin-top: 0;">
        Hello <strong>{customer_name}</strong>,<br>
        We are pleased to inform you that your payment of <strong>₹{amount}</strong> has been successfully verified and confirmed by our administration!
      </p>
      <table class="details-table">
        <tr>
          <td class="label">Receipt / TXN ID</td>
          <td class="value"><code>{tx_id}</code></td>
        </tr>
        <tr>
          <td class="label">Verification Date</td>
          <td class="value">{date_str}</td>
        </tr>
        <tr>
          <td class="label">Payee</td>
          <td class="value">{payee_name}</td>
        </tr>
        <tr>
          <td class="label">Paid to UPI ID</td>
          <td class="value"><code>{upi_id}</code></td>
        </tr>
        <tr>
          <td class="label">UTR / Reference No</td>
          <td class="value"><code>{utr or 'N/A'}</code></td>
        </tr>
        <tr>
          <td class="label">Amount Paid</td>
          <td class="value amount-highlight">₹{amount}</td>
        </tr>
      </table>
      <div style="margin-top: 24px; padding: 16px; background-color: rgba(34, 197, 94, 0.1); border-left: 4px solid #22c55e; border-radius: 6px;">
        <p style="margin: 0; font-size: 13px; color: #86efac;">
          🎉 <strong>Payment Verified!</strong> Thank you for your business. Please save this receipt for your records.
        </p>
      </div>
    """
    html_body = _get_base_email_template(title, badge_html, content_html)
    return await asyncio.to_thread(_send_smtp_ssl, to_email, title, html_body)


async def send_payment_rejected_email(
    to_email: str,
    customer_name: str,
    tx_id: str,
    amount: str,
    payee_name: str,
    upi_id: str,
    utr: str,
    date_str: str = ""
) -> bool:
    """Dispatches the rejection notification when Admin rejects."""
    if not date_str:
        date_str = datetime.now().strftime("%d %b %Y, %I:%M %p")

    title = f"Payment Verification Failed - ₹{amount}"
    badge_html = '<span class="badge badge-rejected">❌ Payment Not Received / Rejected</span>'
    content_html = f"""
      <p style="font-size: 15px; color: #cbd5e1; line-height: 1.6; margin-top: 0;">
        Hello <strong>{customer_name}</strong>,<br>
        Your payment submission of <strong>₹{amount}</strong> could not be verified by our administration and has been marked as <strong>Not Received</strong>.
      </p>
      <table class="details-table">
        <tr>
          <td class="label">TXN ID</td>
          <td class="value"><code>{tx_id}</code></td>
        </tr>
        <tr>
          <td class="label">Reviewed Date</td>
          <td class="value">{date_str}</td>
        </tr>
        <tr>
          <td class="label">Claimed UTR No</td>
          <td class="value"><code>{utr or 'N/A'}</code></td>
        </tr>
        <tr>
          <td class="label">Amount</td>
          <td class="value amount-highlight">₹{amount}</td>
        </tr>
      </table>
      <div style="margin-top: 24px; padding: 16px; background-color: rgba(239, 68, 68, 0.1); border-left: 4px solid #ef4444; border-radius: 6px;">
        <p style="margin: 0; font-size: 13px; color: #fca5a5;">
          ⚠️ <strong>Possible reasons:</strong> The payment was not credited to our UPI account, the UTR number was invalid, or the transaction was declined by your bank. Please check your bank statement or contact staff on Discord.
        </p>
      </div>
    """
    html_body = _get_base_email_template(title, badge_html, content_html)
    return await asyncio.to_thread(_send_smtp_ssl, to_email, title, html_body)
