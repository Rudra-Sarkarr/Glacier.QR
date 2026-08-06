const QRCode = require('qrcode');

// Regex for standard UPI VPA validation
const UPI_REGEX = /^[a-zA-Z0-9.\-_]{2,256}@[a-zA-Z]{2,64}$/;

/**
 * Validate standard UPI VPA format
 */
function isValidUPI(upiId) {
  if (!upiId || typeof upiId !== 'string') return false;
  return UPI_REGEX.test(upiId.trim());
}

/**
 * Format amount to 2 decimal places or clean integer format
 */
function formatAmount(amount) {
  const num = parseFloat(String(amount).replace(/[^0-9.]/g, ''));
  if (isNaN(num) || num <= 0) return null;
  // Return formatted float (e.g., 300 or 300.50)
  return Number.isInteger(num) ? num.toString() : num.toFixed(2);
}

/**
 * Build standard UPI payment URL (NPCI standard)
 * upi://pay?pa=VPA&pn=NAME&am=AMOUNT&cu=INR&tn=NOTE
 */
function buildUPIUrl(upiId, amount, name = '', note = '') {
  const cleanUpi = upiId.trim();
  const cleanAmount = formatAmount(amount);
  
  if (!cleanAmount) {
    throw new Error('Invalid amount specified');
  }

  const params = new URLSearchParams();
  params.append('pa', cleanUpi);
  
  if (name && name.trim()) {
    params.append('pn', name.trim());
  } else {
    params.append('pn', 'Payee');
  }

  params.append('am', cleanAmount);
  params.append('cu', 'INR');

  if (note && note.trim()) {
    params.append('tn', note.trim());
  } else {
    params.append('tn', `Payment of Rs ${cleanAmount}`);
  }

  return `upi://pay?${params.toString()}`;
}

/**
 * Generate PNG QR Code Buffer (for Telegram sending)
 */
async function generateQRBuffer(upiUrl, options = {}) {
  const defaultOpts = {
    errorCorrectionLevel: 'H',
    type: 'png',
    margin: 2,
    width: 512,
    color: {
      dark: '#0f172a',  // sleek dark navy dots
      light: '#ffffff' // pure white background
    }
  };

  return await QRCode.toBuffer(upiUrl, { ...defaultOpts, ...options });
}

/**
 * Generate Base64 Data URL (for Web UI rendering)
 */
async function generateQRDataURL(upiUrl, options = {}) {
  const defaultOpts = {
    errorCorrectionLevel: 'H',
    margin: 2,
    width: 400,
    color: {
      dark: '#0f172a',
      light: '#ffffff'
    }
  };

  return await QRCode.toDataURL(upiUrl, { ...defaultOpts, ...options });
}

/**
 * Deep link generators for specific UPI apps
 */
function getAppLinks(upiUrl) {
  const encoded = encodeURIComponent(upiUrl);
  return {
    generic: upiUrl,
    phonepe: `phonepe://pay?${upiUrl.replace('upi://pay?', '')}`,
    gpay: `gpay://upi/pay?${upiUrl.replace('upi://pay?', '')}`,
    paytm: `paytmmp://pay?${upiUrl.replace('upi://pay?', '')}`
  };
}

module.exports = {
  isValidUPI,
  formatAmount,
  buildUPIUrl,
  generateQRBuffer,
  generateQRDataURL,
  getAppLinks
};
