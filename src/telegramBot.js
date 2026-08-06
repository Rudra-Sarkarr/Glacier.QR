const TelegramBot = require('node-telegram-bot-api');
const storage = require('./storage');
const upiUtils = require('./upiUtils');

class CustomUpiBot {
  constructor(token) {
    this.token = token;
    this.bot = null;
    this.isRunning = false;
  }

  start() {
    if (this.isRunning) return;

    this.bot = new TelegramBot(this.token, { polling: true });
    this.isRunning = true;
    console.log('🤖 Telegram Bot Service started successfully!');

    // Catch polling errors cleanly
    this.bot.on('polling_error', (error) => {
      console.error('Telegram Bot Polling Error:', error.message);
    });

    this.registerHandlers();
  }

  stop() {
    if (this.bot && this.isRunning) {
      this.bot.stopPolling();
      this.isRunning = false;
      console.log('🛑 Telegram Bot Service stopped.');
    }
  }

  registerHandlers() {
    const bot = this.bot;

    // /start command
    bot.onText(/\/start/, async (msg) => {
      const chatId = msg.chat.id;
      const text = `✨ **Welcome to Custom Value UPI QR Generator Bot!** ✨\n\n` +
        `This bot lets you store up to 4 UPI IDs and quickly generate payment QR codes for any custom amount (e.g. ₹300, ₹500).\n\n` +
        `⚙️ **Available Commands:**\n` +
        `🔹 \`/upi set\` - Open menu to configure your 4 UPI ID slots\n` +
        `🔹 \`/qr\` - Select a UPI ID & choose an amount to generate QR\n` +
        `🔹 \`/myupi\` - View all configured UPI ID slots\n` +
        `🔹 \`/help\` - How to use this bot\n\n` +
        `👉 Type \`/upi set\` now to configure your first UPI ID!`;

      await bot.sendMessage(chatId, text, {
        parse_mode: 'Markdown',
        reply_markup: {
          inline_keyboard: [
            [
              { text: '⚙️ Configure UPI IDs (/upi set)', callback_data: 'cmd_upi_set' }
            ],
            [
              { text: '📱 Generate Custom QR (/qr)', callback_data: 'cmd_qr' }
            ]
          ]
        }
      });
    });

    // /help command
    bot.onText(/\/help/, async (msg) => {
      const chatId = msg.chat.id;
      const text = `ℹ️ **How to use Custom UPI QR Generator Bot:**\n\n` +
        `1️⃣ **Step 1:** Type \`/upi set\` to open the 4-slot UPI manager menu.\n` +
        `2️⃣ **Step 2:** Choose any slot (Slot 1 to 4) and enter your UPI ID (e.g., \`username@okicici\` or \`9876543210@paytm\`).\n` +
        `3️⃣ **Step 3:** Type \`/qr\` to select your desired UPI ID and pick an amount (e.g. ₹300).\n` +
        `4️⃣ **Step 4:** The bot will immediately reply with your custom-valued UPI QR Code!`;
      await bot.sendMessage(chatId, text, { parse_mode: 'Markdown' });
    });

    // /myupi command
    bot.onText(/\/myupi/, async (msg) => {
      const chatId = msg.chat.id;
      await this.sendUpiStatus(chatId);
    });

    // /upi set or /upiset command
    bot.onText(/\/(upi\s*set|upiset|upi)/i, async (msg) => {
      const chatId = msg.chat.id;
      await this.sendUpiSetMenu(chatId);
    });

    // /qr command
    bot.onText(/\/qr/i, async (msg) => {
      const chatId = msg.chat.id;
      await this.sendQrUpiSelectionMenu(chatId);
    });

    // Callback Query Handler for Inline Keyboards
    bot.on('callback_query', async (query) => {
      const chatId = query.message.chat.id;
      const messageId = query.message.message_id;
      const data = query.data;

      try {
        await bot.answerCallbackQuery(query.id);

        if (data === 'cmd_upi_set') {
          await this.sendUpiSetMenu(chatId, messageId);
        } else if (data === 'cmd_qr') {
          await this.sendQrUpiSelectionMenu(chatId, messageId);
        } else if (data.startsWith('set_slot_')) {
          const slotId = parseInt(data.replace('set_slot_', ''), 10);
          storage.setUserState(chatId, { step: 'AWAITING_UPI_INPUT', slotId });
          await bot.sendMessage(
            chatId,
            `✏️ **Configure Slot ${slotId}**\n\nPlease send your UPI ID for Slot ${slotId} (e.g., \`name@upi\` or \`9876543210@paytm\`):`,
            { parse_mode: 'Markdown' }
          );
        } else if (data.startsWith('clear_slot_')) {
          const slotId = parseInt(data.replace('clear_slot_', ''), 10);
          storage.deleteSlot(chatId, slotId);
          await bot.sendMessage(chatId, `🗑️ Slot ${slotId} cleared successfully.`);
          await this.sendUpiSetMenu(chatId);
        } else if (data.startsWith('select_qr_slot_')) {
          const slotId = parseInt(data.replace('select_qr_slot_', ''), 10);
          const profile = storage.getUserProfile(chatId);
          const slot = profile.slots.find(s => s.id === slotId);

          if (!slot || !slot.upiId) {
            await bot.sendMessage(chatId, `❌ Slot ${slotId} is empty. Please configure it first using \`/upi set\`.`);
            return;
          }

          // Move to amount selection menu
          await this.sendAmountSelectionMenu(chatId, slot, messageId);
        } else if (data.startsWith('qr_amt_')) {
          // Format: qr_amt_<slotId>_<amount>
          const parts = data.split('_');
          const slotId = parseInt(parts[2], 10);
          const amount = parts[3];

          if (amount === 'custom') {
            storage.setUserState(chatId, { step: 'AWAITING_CUSTOM_AMOUNT', slotId });
            await bot.sendMessage(chatId, `💵 **Enter Custom Amount:**\n\nPlease type the amount in ₹ (e.g., \`300\`, \`450.50\`, \`1200\`):`, {
              parse_mode: 'Markdown'
            });
          } else {
            const profile = storage.getUserProfile(chatId);
            const slot = profile.slots.find(s => s.id === slotId);
            if (slot && slot.upiId) {
              await this.generateAndSendQR(chatId, slot.upiId, slot.name, amount);
            }
          }
        }
      } catch (err) {
        console.error('Error handling callback query:', err);
      }
    });

    // Handle plain text messages (direct amount entry, setting UPI ID state, or typing numbers)
    bot.on('message', async (msg) => {
      // Ignore command triggers already handled by onText
      if (!msg.text || msg.text.startsWith('/')) return;

      const chatId = msg.chat.id;
      const text = msg.text.trim();
      const profile = storage.getUserProfile(chatId);
      const state = profile.state;

      // Case 1: Waiting for UPI ID input for a specific slot
      if (state && state.step === 'AWAITING_UPI_INPUT') {
        const slotId = state.slotId;
        if (!upiUtils.isValidUPI(text)) {
          await bot.sendMessage(
            chatId,
            `⚠️ **Invalid UPI ID format!**\n\nPlease send a valid UPI ID (e.g., \`merchant@okicici\`, \`9876543210@paytm\`, \`name@ybl\`):`,
            { parse_mode: 'Markdown' }
          );
          return;
        }

        // Ask for optional payee name or save with default label
        storage.updateSlot(chatId, slotId, text, `UPI Slot ${slotId}`);
        storage.setUserState(chatId, { step: 'AWAITING_NAME_INPUT', slotId, upiId: text });

        await bot.sendMessage(
          chatId,
          `✅ **UPI ID Saved for Slot ${slotId}!**\n\n📌 **UPI ID:** \`${text}\`\n\n(Optional) Reply with a Payee Name / Shop Name for this slot (e.g., "My Shop" or "John"), or send \`/skip\` to keep default:`,
          { parse_mode: 'Markdown' }
        );
        return;
      }

      // Case 2: Waiting for optional name input
      if (state && state.step === 'AWAITING_NAME_INPUT') {
        const slotId = state.slotId;
        const upiId = state.upiId;

        let name = text;
        if (text.toLowerCase() === '/skip' || text.toLowerCase() === 'skip') {
          name = `UPI Slot ${slotId}`;
        }

        storage.updateSlot(chatId, slotId, upiId, name);
        storage.clearUserState(chatId);

        await bot.sendMessage(
          chatId,
          `🎉 **Slot ${slotId} Setup Complete!**\n\n💳 **UPI ID:** \`${upiId}\`\n👤 **Name:** \`${name}\`\n\nNow send \`/qr\` to generate custom payment QR codes!`,
          { parse_mode: 'Markdown' }
        );

        await this.sendUpiSetMenu(chatId);
        return;
      }

      // Case 3: Waiting for custom amount input
      if (state && state.step === 'AWAITING_CUSTOM_AMOUNT') {
        const slotId = state.slotId;
        const formattedAmt = upiUtils.formatAmount(text);

        if (!formattedAmt) {
          await bot.sendMessage(chatId, `⚠️ **Invalid amount!** Please enter a valid positive number (e.g., \`300\` or \`500.50\`).`);
          return;
        }

        storage.clearUserState(chatId);
        const slot = profile.slots.find(s => s.id === slotId);

        if (slot && slot.upiId) {
          await this.generateAndSendQR(chatId, slot.upiId, slot.name, formattedAmt);
        } else {
          await bot.sendMessage(chatId, `❌ Selected slot is missing a UPI ID. Use \`/upi set\` first.`);
        }
        return;
      }

      // Case 4: User typed a raw number (e.g., "300" or "₹300")
      const extractedAmount = upiUtils.formatAmount(text);
      if (extractedAmount) {
        const configured = storage.getConfiguredSlots(chatId);
        if (configured.length === 0) {
          await bot.sendMessage(
            chatId,
            `💡 You entered **₹${extractedAmount}**, but no UPI ID is configured yet.\n\nType \`/upi set\` to configure your UPI ID first!`,
            { parse_mode: 'Markdown' }
          );
        } else if (configured.length === 1) {
          // Auto-generate for the single configured slot
          await this.generateAndSendQR(chatId, configured[0].upiId, configured[0].name, extractedAmount);
        } else {
          // Multiple slots available -> show slot picker for this amount
          await this.sendSlotPickerForAmount(chatId, extractedAmount);
        }
      }
    });
  }

  /**
   * Display the 4-Slot Setup Menu (/upi set)
   */
  async sendUpiSetMenu(chatId, messageId = null) {
    const profile = storage.getUserProfile(chatId);
    const slots = profile.slots;

    let text = `⚙️ **UPI ID Manager (Up to 4 Slots)**\n\n`;
    text += `Click on any slot below to set or update its UPI ID:\n\n`;

    const keyboard = [];

    slots.forEach((s) => {
      const statusIcon = s.upiId ? '✅' : '❌';
      const label = s.upiId ? `${s.name} (${s.upiId})` : `Slot ${s.id}: [Not Set]`;
      text += `${s.id}️⃣ **${s.name}**: \`${s.upiId || 'Not Set'}\`\n`;

      keyboard.push([
        { text: `${statusIcon} ${s.id}. ${label}`, callback_data: `set_slot_${s.id}` }
      ]);
    });

    text += `\n💡 *Once configured, use /qr to generate custom QR codes anytime!*`;

    const options = {
      parse_mode: 'Markdown',
      reply_markup: { inline_keyboard: keyboard }
    };

    if (messageId) {
      await this.bot.editMessageText(text, { chat_id: chatId, message_id: messageId, ...options });
    } else {
      await this.bot.sendMessage(chatId, text, options);
    }
  }

  /**
   * Step 1 of /qr: Choose UPI ID from configured slots
   */
  async sendQrUpiSelectionMenu(chatId, messageId = null) {
    const configuredSlots = storage.getConfiguredSlots(chatId);

    if (configuredSlots.length === 0) {
      const text = `⚠️ **No UPI IDs Configured Yet!**\n\nPlease set up at least 1 UPI ID first using \`/upi set\`.`;
      const keyboard = [
        [{ text: '⚙️ Configure UPI IDs Now', callback_data: 'cmd_upi_set' }]
      ];
      if (messageId) {
        await this.bot.editMessageText(text, { chat_id: chatId, message_id: messageId, parse_mode: 'Markdown', reply_markup: { inline_keyboard: keyboard } });
      } else {
        await this.bot.sendMessage(chatId, text, { parse_mode: 'Markdown', reply_markup: { inline_keyboard: keyboard } });
      }
      return;
    }

    const text = `📱 **Select UPI Slot to Generate QR:**\n\nChoose which UPI ID you want to receive payment into:`;
    const keyboard = configuredSlots.map(s => ([
      { text: `💳 ${s.name} (${s.upiId})`, callback_data: `select_qr_slot_${s.id}` }
    ]));

    const options = {
      parse_mode: 'Markdown',
      reply_markup: { inline_keyboard: keyboard }
    };

    if (messageId) {
      await this.bot.editMessageText(text, { chat_id: chatId, message_id: messageId, ...options });
    } else {
      await this.bot.sendMessage(chatId, text, options);
    }
  }

  /**
   * Step 2 of /qr: Choose/Type Amount
   */
  async sendAmountSelectionMenu(chatId, slot, messageId = null) {
    const text = `💰 **Select Amount for QR Code:**\n\n` +
      `💳 **Payee:** \`${slot.name}\` (\`${slot.upiId}\`)\n\n` +
      `Choose a quick amount button below or tap ✏️ Custom Amount:`;

    const keyboard = [
      [
        { text: '₹50', callback_data: `qr_amt_${slot.id}_50` },
        { text: '₹100', callback_data: `qr_amt_${slot.id}_100` },
        { text: '₹200', callback_data: `qr_amt_${slot.id}_200` }
      ],
      [
        { text: '₹300', callback_data: `qr_amt_${slot.id}_300` },
        { text: '₹500', callback_data: `qr_amt_${slot.id}_500` },
        { text: '₹1000', callback_data: `qr_amt_${slot.id}_1000` }
      ],
      [
        { text: '₹2000', callback_data: `qr_amt_${slot.id}_2000` },
        { text: '₹5000', callback_data: `qr_amt_${slot.id}_5000` }
      ],
      [
        { text: '✏️ Enter Custom Amount', callback_data: `qr_amt_${slot.id}_custom` }
      ]
    ];

    const options = {
      parse_mode: 'Markdown',
      reply_markup: { inline_keyboard: keyboard }
    };

    if (messageId) {
      await this.bot.editMessageText(text, { chat_id: chatId, message_id: messageId, ...options });
    } else {
      await this.bot.sendMessage(chatId, text, options);
    }
  }

  /**
   * Show slot selection when user directly sends a number
   */
  async sendSlotPickerForAmount(chatId, amount) {
    const configuredSlots = storage.getConfiguredSlots(chatId);
    const text = `💸 You requested a QR code for **₹${amount}**!\n\nSelect which UPI ID slot to generate the QR for:`;

    const keyboard = configuredSlots.map(s => ([
      { text: `💳 ${s.name} (${s.upiId})`, callback_data: `qr_amt_${s.id}_${amount}` }
    ]));

    await this.bot.sendMessage(chatId, text, {
      parse_mode: 'Markdown',
      reply_markup: { inline_keyboard: keyboard }
    });
  }

  /**
   * Generate QR buffer and send photo with caption & direct deep links
   */
  async generateAndSendQR(chatId, upiId, payeeName, amount) {
    try {
      const upiUrl = upiUtils.buildUPIUrl(upiId, amount, payeeName, `Payment of Rs ${amount}`);
      const qrBuffer = await upiUtils.generateQRBuffer(upiUrl);

      const caption = `✅ **Custom Value UPI QR Generated!**\n\n` +
        `👤 **Payee Name:** ${payeeName || 'Payee'}\n` +
        `💳 **UPI ID:** \`${upiId}\`\n` +
        `💵 **Amount:** ₹${amount}\n` +
        `📝 **Note:** Payment of Rs ${amount}\n\n` +
        `📲 *Scan with GPay, PhonePe, Paytm, BHIM, Cred or any UPI app to pay!*`;

      const deepLinks = upiUtils.getAppLinks(upiUrl);

      await this.bot.sendPhoto(chatId, qrBuffer, {
        caption,
        parse_mode: 'Markdown',
        reply_markup: {
          inline_keyboard: [
            [
              { text: '⚡ Open in PhonePe', url: deepLinks.phonepe },
              { text: '🔵 Open in GPay', url: deepLinks.gpay }
            ],
            [
              { text: '📲 Open in Paytm', url: deepLinks.paytm },
              { text: '🔗 UPI DeepLink', url: deepLinks.generic }
            ],
            [
              { text: '🔄 Generate Another QR (/qr)', callback_data: 'cmd_qr' }
            ]
          ]
        }
      });
    } catch (err) {
      console.error('Error generating/sending QR code:', err);
      await this.bot.sendMessage(chatId, `❌ Failed to generate QR Code: ${err.message}`);
    }
  }

  /**
   * Overview of configured UPI slots
   */
  async sendUpiStatus(chatId) {
    const profile = storage.getUserProfile(chatId);
    let text = `💳 **Your Configured UPI Slots:**\n\n`;

    profile.slots.forEach(s => {
      if (s.upiId) {
        text += `🔹 **Slot ${s.id} (${s.name}):** \`${s.upiId}\`\n`;
      } else {
        text += `🔸 **Slot ${s.id}:** _Not Configured_\n`;
      }
    });

    text += `\nUse \`/upi set\` to modify your slots or \`/qr\` to generate custom valued QR codes.`;

    await this.bot.sendMessage(chatId, text, { parse_mode: 'Markdown' });
  }
}

module.exports = CustomUpiBot;
