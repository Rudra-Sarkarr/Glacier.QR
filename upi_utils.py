import re
import io
import base64
from urllib.parse import urlencode
import qrcode

UPI_REGEX = re.compile(r'^[a-zA-Z0-9.\-_]{2,256}@[a-zA-Z]{2,64}$')

def is_valid_upi(upi_id: str) -> bool:
    if not upi_id or not isinstance(upi_id, str):
        return False
    return bool(UPI_REGEX.match(upi_id.strip()))

def format_amount(amount) -> str:
    try:
        clean_str = re.sub(r'[^0-9.]', '', str(amount))
        val = float(clean_str)
        if val <= 0:
            return None
        if val.is_integer():
            return str(int(val))
        return f"{val:.2f}"
    except (ValueError, TypeError):
        return None

def build_upi_url(upi_id: str, amount, name: str = "", note: str = "") -> str:
    clean_upi = upi_id.strip()
    clean_amt = format_amount(amount)
    if not clean_amt:
        raise ValueError("Invalid amount specified")

    params = {
        'pa': clean_upi,
        'pn': name.strip() if name and name.strip() else 'Payee',
        'am': clean_amt,
        'cu': 'INR',
        'tn': note.strip() if note and note.strip() else f"Payment of Rs {clean_amt}"
    }

    return f"upi://pay?{urlencode(params, safe='@')}"

def generate_qr_bytes(upi_url: str) -> bytes:
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_H,
        box_size=10,
        border=2,
    )
    qr.add_data(upi_url)
    qr.make(fit=True)
    img = qr.make_image(fill_color="#0f172a", back_color="white")
    
    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    buffer.seek(0)
    return buffer.getvalue()

def generate_qr_data_url(upi_url: str) -> str:
    png_bytes = generate_qr_bytes(upi_url)
    base64_encoded = base64.b64encode(png_bytes).decode('utf-8')
    return f"data:image/png;base64,{base64_encoded}"

def get_app_links(upi_url: str) -> dict:
    raw_params = upi_url.replace("upi://pay?", "")
    return {
        "generic": upi_url,
        "phonepe": f"phonepe://pay?{raw_params}",
        "gpay": f"gpay://upi/pay?{raw_params}",
        "paytm": f"paytmmp://pay?{raw_params}"
    }
