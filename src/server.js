const express = require('express');
const cors = require('cors');
const path = require('path');
const storage = require('./storage');
const upiUtils = require('./upiUtils');
const CustomUpiDiscordBot = require('./discordBot');

const app = express();
const PORT = process.env.PORT || 3000;

app.use(cors());
app.use(express.json());
app.use(express.static(path.join(__dirname, '../public')));

// Global Discord bot instance container
let activeDiscordBot = null;

// REST API Endpoints

/**
 * Get profile and 4 slots for web user / simulator
 */
app.get('/api/user/:userId', (req, res) => {
  try {
    const profile = storage.getUserProfile(req.params.userId);
    res.json({ success: true, profile });
  } catch (err) {
    res.status(500).json({ success: false, error: err.message });
  }
});

/**
 * Update slot UPI ID & Name
 */
app.post('/api/user/slot', (req, res) => {
  try {
    const { userId, slotId, upiId, name } = req.body;

    if (!userId || !slotId || !upiId) {
      return res.status(400).json({ success: false, error: 'Missing userId, slotId, or upiId' });
    }

    if (!upiUtils.isValidUPI(upiId)) {
      return res.status(400).json({ success: false, error: 'Invalid UPI ID format. Must be e.g. name@bank' });
    }

    const updatedProfile = storage.updateSlot(userId, slotId, upiId, name);
    res.json({ success: true, profile: updatedProfile });
  } catch (err) {
    res.status(500).json({ success: false, error: err.message });
  }
});

/**
 * Delete / Reset slot
 */
app.delete('/api/user/slot', (req, res) => {
  try {
    const { userId, slotId } = req.body;
    if (!userId || !slotId) {
      return res.status(400).json({ success: false, error: 'Missing userId or slotId' });
    }
    const updatedProfile = storage.deleteSlot(userId, slotId);
    res.json({ success: true, profile: updatedProfile });
  } catch (err) {
    res.status(500).json({ success: false, error: err.message });
  }
});

/**
 * Generate UPI QR Code Base64 Data URL
 */
app.post('/api/qr/generate', async (req, res) => {
  try {
    const { upiId, amount, name, note } = req.body;

    if (!upiId || !upiUtils.isValidUPI(upiId)) {
      return res.status(400).json({ success: false, error: 'Valid upiId is required' });
    }

    const formattedAmount = upiUtils.formatAmount(amount);
    if (!formattedAmount) {
      return res.status(400).json({ success: false, error: 'Valid positive amount is required' });
    }

    const upiUrl = upiUtils.buildUPIUrl(upiId, formattedAmount, name, note);
    const qrDataUrl = await upiUtils.generateQRDataURL(upiUrl);
    const appLinks = upiUtils.getAppLinks(upiUrl);

    res.json({
      success: true,
      upiUrl,
      qrDataUrl,
      amount: formattedAmount,
      upiId,
      payeeName: name || 'Payee',
      appLinks
    });
  } catch (err) {
    res.status(500).json({ success: false, error: err.message });
  }
});

/**
 * Start Discord Bot instance using user token
 */
app.post('/api/bot/start', async (req, res) => {
  try {
    const { token, clientId } = req.body;
    if (!token || typeof token !== 'string' || token.length < 20) {
      return res.status(400).json({ success: false, error: 'Invalid Discord Bot token format' });
    }

    if (activeDiscordBot) {
      await activeDiscordBot.stop();
    }

    activeDiscordBot = new CustomUpiDiscordBot(token.trim(), clientId ? clientId.trim() : null);
    await activeDiscordBot.start();

    res.json({ success: true, message: 'Discord Bot successfully logged in & started!' });
  } catch (err) {
    console.error('Discord bot launch error:', err);
    res.status(500).json({ success: false, error: err.message });
  }
});

/**
 * Stop active Discord Bot instance
 */
app.post('/api/bot/stop', async (req, res) => {
  try {
    if (activeDiscordBot) {
      await activeDiscordBot.stop();
      activeDiscordBot = null;
      res.json({ success: true, message: 'Discord Bot stopped successfully.' });
    } else {
      res.json({ success: true, message: 'No active Discord bot running.' });
    }
  } catch (err) {
    res.status(500).json({ success: false, error: err.message });
  }
});

/**
 * Get Discord Bot status
 */
app.get('/api/bot/status', (req, res) => {
  res.json({
    success: true,
    active: activeDiscordBot ? activeDiscordBot.isRunning : false,
    botUser: activeDiscordBot && activeDiscordBot.client ? activeDiscordBot.client.user?.tag : null
  });
});

app.listen(PORT, () => {
  console.log(`================================================`);
  console.log(`🚀 Custom UPI QR Discord Bot Server running on port ${PORT}`);
  console.log(`🌐 Open http://localhost:${PORT} in your browser`);
  console.log(`================================================`);
});
