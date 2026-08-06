const {
  Client,
  GatewayIntentBits,
  EmbedBuilder,
  ActionRowBuilder,
  ButtonBuilder,
  ButtonStyle,
  StringSelectMenuBuilder,
  ModalBuilder,
  TextInputBuilder,
  TextInputStyle,
  AttachmentBuilder,
  REST,
  Routes,
  SlashCommandBuilder
} = require('discord.js');

const storage = require('./storage');
const upiUtils = require('./upiUtils');

class CustomUpiDiscordBot {
  constructor(token, clientId = null) {
    this.token = token;
    this.clientId = clientId;
    this.client = null;
    this.isRunning = false;
  }

  async start() {
    if (this.isRunning) return;

    this.client = new Client({
      intents: [
        GatewayIntentBits.Guilds,
        GatewayIntentBits.GuildMessages,
        GatewayIntentBits.MessageContent,
        GatewayIntentBits.DirectMessages
      ]
    });

    this.registerEvents();

    await this.client.login(this.token);
    this.isRunning = true;
    console.log(`🤖 Discord Bot logged in as ${this.client.user?.tag}`);

    // Register Slash Commands automatically if clientId is available or can be retrieved
    if (this.client.user?.id) {
      await this.registerSlashCommands(this.client.user.id);
    }
  }

  async stop() {
    if (this.client && this.isRunning) {
      await this.client.destroy();
      this.isRunning = false;
      console.log('🛑 Discord Bot logged out.');
    }
  }

  async registerSlashCommands(clientId) {
    try {
      const rest = new REST({ version: '10' }).setToken(this.token);

      const commands = [
        new SlashCommandBuilder()
          .setName('upi-set')
          .setDescription('Manage your 4 UPI ID slots using interactive popup modal'),
        new SlashCommandBuilder()
          .setName('qr')
          .setDescription('Generate a custom valued UPI QR Code (e.g. ₹300)'),
        new SlashCommandBuilder()
          .setName('myupi')
          .setDescription('View your saved UPI ID slots'),
        new SlashCommandBuilder()
          .setName('help')
          .setDescription('Learn how to use the Custom UPI QR Bot')
      ].map(cmd => cmd.toJSON());

      await rest.put(
        Routes.applicationCommands(clientId),
        { body: commands }
      );
      console.log('✅ Global Slash Commands registered successfully!');
    } catch (err) {
      console.error('Failed to register slash commands:', err.message);
    }
  }

  registerEvents() {
    const client = this.client;

    client.on('ready', () => {
      console.log(`⚡ Discord Bot Ready: ${client.user.tag}`);
      client.user.setActivity('₹ Custom Value QR Generator | /qr', { type: 3 }); // Playing/Watching
    });

    // Handle Slash Commands, Buttons, Select Menus, & Modals
    client.on('interactionCreate', async (interaction) => {
      try {
        // 1. Slash Commands
        if (interaction.isChatInputCommand()) {
          const { commandName } = interaction;
          if (commandName === 'upi-set') {
            await this.handleUpiSetMenu(interaction);
          } else if (commandName === 'qr') {
            await this.handleQrMenu(interaction);
          } else if (commandName === 'myupi') {
            await this.handleMyUpi(interaction);
          } else if (commandName === 'help') {
            await this.handleHelp(interaction);
          }
        }

        // 2. Button Click Interactions
        else if (interaction.isButton()) {
          const customId = interaction.customId;

          if (customId.startsWith('btn_slot_modal_')) {
            // Open Discord Modal for setting up a slot
            const slotId = parseInt(customId.replace('btn_slot_modal_', ''), 10);
            await this.showSlotModal(interaction, slotId);
          } else if (customId.startsWith('btn_clear_slot_')) {
            const slotId = parseInt(customId.replace('btn_clear_slot_', ''), 10);
            storage.deleteSlot(interaction.user.id, slotId);
            await interaction.reply({ content: `🗑️ Slot ${slotId} cleared!`, ephemeral: true });
            await this.handleUpiSetMenu(interaction, true);
          } else if (customId.startsWith('btn_amt_')) {
            // Format: btn_amt_<slotId>_<amount>
            const parts = customId.split('_');
            const slotId = parseInt(parts[2], 10);
            const amount = parts[3];

            if (amount === 'custom') {
              await this.showCustomAmountModal(interaction, slotId);
            } else {
              await this.generateAndSendDiscordQR(interaction, slotId, amount);
            }
          } else if (customId === 'btn_trigger_upi_set') {
            await this.handleUpiSetMenu(interaction, true);
          } else if (customId === 'btn_trigger_qr') {
            await this.handleQrMenu(interaction, true);
          }
        }

        // 3. String Select Menu Interactions
        else if (interaction.isStringSelectMenu()) {
          if (interaction.customId === 'select_qr_slot') {
            const slotId = parseInt(interaction.values[0], 10);
            await this.handleAmountMenuForSlot(interaction, slotId);
          } else if (interaction.customId.startsWith('select_slot_for_amt_')) {
            const amount = interaction.customId.replace('select_slot_for_amt_', '');
            const slotId = parseInt(interaction.values[0], 10);
            await this.generateAndSendDiscordQR(interaction, slotId, amount);
          }
        }

        // 4. Modal Submissions (Popup forms)
        else if (interaction.isModalSubmit()) {
          if (interaction.customId.startsWith('modal_slot_')) {
            const slotId = parseInt(interaction.customId.replace('modal_slot_', ''), 10);
            const upiId = interaction.fields.getTextInputValue('input_upi_id').trim();
            const name = interaction.fields.getTextInputValue('input_payee_name').trim();

            if (!upiUtils.isValidUPI(upiId)) {
              await interaction.reply({
                content: `⚠️ **Invalid UPI ID format!** Please use format like \`user@okicici\` or \`9876543210@paytm\`.`,
                ephemeral: true
              });
              return;
            }

            storage.updateSlot(interaction.user.id, slotId, upiId, name || `UPI Slot ${slotId}`);

            const successEmbed = new EmbedBuilder()
              .setTitle(`✅ Slot ${slotId} Updated Successfully!`)
              .setColor('#10B981')
              .addFields(
                { name: '💳 UPI ID', value: `\`${upiId}\``, inline: true },
                { name: '👤 Payee Name', value: `\`${name || `UPI Slot ${slotId}`}\``, inline: true }
              )
              .setFooter({ text: 'Now run /qr to generate payment QR codes!' });

            await interaction.reply({ embeds: [successEmbed], ephemeral: true });
          } else if (interaction.customId.startsWith('modal_custom_amt_')) {
            const slotId = parseInt(interaction.customId.replace('modal_custom_amt_', ''), 10);
            const rawAmount = interaction.fields.getTextInputValue('input_custom_amount');
            const formattedAmt = upiUtils.formatAmount(rawAmount);

            if (!formattedAmt) {
              await interaction.reply({ content: `⚠️ Invalid amount. Please enter a valid positive number like 300 or 500.50`, ephemeral: true });
              return;
            }

            await this.generateAndSendDiscordQR(interaction, slotId, formattedAmt);
          }
        }
      } catch (err) {
        console.error('Error handling Discord interaction:', err);
        if (!interaction.replied && !interaction.deferred) {
          await interaction.reply({ content: `❌ Error: ${err.message}`, ephemeral: true }).catch(() => {});
        }
      }
    });

    // Message handler for text prefix commands & raw amount entries
    client.on('messageCreate', async (message) => {
      if (message.author.bot) return;

      const content = message.content.trim();

      if (content.toLowerCase().startsWith('!upi set') || content.toLowerCase().startsWith('!upiset') || content.toLowerCase() === '!upi') {
        await this.handleUpiSetMessage(message);
        return;
      }

      if (content.toLowerCase().startsWith('!qr')) {
        await this.handleQrMessage(message);
        return;
      }

      if (content.toLowerCase() === '!myupi') {
        await this.handleMyUpiMessage(message);
        return;
      }

      if (content.toLowerCase() === '!help') {
        await this.handleHelpMessage(message);
        return;
      }

      // Check if user sent a raw numeric amount (e.g. "300" or "₹300")
      const extractedAmount = upiUtils.formatAmount(content);
      if (extractedAmount && !content.includes(' ')) {
        const configured = storage.getConfiguredSlots(message.author.id);
        if (configured.length === 0) {
          await message.reply('💡 You entered an amount, but no UPI ID is saved yet! Use `/upi-set` or `!upi set` to configure your slots.');
        } else if (configured.length === 1) {
          // Direct generate for single slot
          await this.generateAndSendDiscordQRMessage(message, configured[0].id, extractedAmount);
        } else {
          // Multi slot menu for this amount
          await this.sendSlotPickerForAmountMessage(message, extractedAmount);
        }
      }
    });
  }

  /**
   * Render /upi-set Popup Slot Selector Menu
   */
  async handleUpiSetMenu(interaction, isUpdate = false) {
    const userId = interaction.user.id;
    const profile = storage.getUserProfile(userId);

    const embed = new EmbedBuilder()
      .setTitle('⚙️ Multi-Slot UPI ID Manager')
      .setDescription('Store up to **4 UPI IDs** for your account. Click a button below to configure or edit that slot using a pop-up modal menu.')
      .setColor('#5865F2');

    const buttonsRow = new ActionRowBuilder();

    profile.slots.forEach((s) => {
      const statusIcon = s.upiId ? '✅' : '➕';
      const label = s.upiId ? `Slot ${s.id}: ${s.name}` : `Set Slot ${s.id}`;

      embed.addFields({
        name: `Slot ${s.id} ${statusIcon}`,
        value: s.upiId ? `💳 \`${s.upiId}\`\n👤 *${s.name}*` : `*Not Configured*`,
        inline: true
      });

      buttonsRow.addComponents(
        new ButtonBuilder()
          .setCustomId(`btn_slot_modal_${s.id}`)
          .setLabel(label.length > 80 ? label.substring(0, 77) + '...' : label)
          .setStyle(s.upiId ? ButtonStyle.Success : ButtonStyle.Primary)
      );
    });

    const payload = { embeds: [embed], components: [buttonsRow] };

    if (isUpdate) {
      if (interaction.isButton()) {
        await interaction.update(payload);
      } else {
        await interaction.editReply(payload);
      }
    } else {
      await interaction.reply(payload);
    }
  }

  /**
   * Show Discord Popup Modal for editing slot
   */
  async showSlotModal(interaction, slotId) {
    const profile = storage.getUserProfile(interaction.user.id);
    const slot = profile.slots.find(s => s.id === slotId) || { upiId: '', name: '' };

    const modal = new ModalBuilder()
      .setCustomId(`modal_slot_${slotId}`)
      .setTitle(`Configure UPI Slot ${slotId}`);

    const upiInput = new TextInputBuilder()
      .setCustomId('input_upi_id')
      .setLabel(`UPI ID / VPA for Slot ${slotId}:`)
      .setPlaceholder('e.g. merchant@okicici or 9876543210@paytm')
      .setValue(slot.upiId || '')
      .setStyle(TextInputStyle.Short)
      .setRequired(true);

    const nameInput = new TextInputBuilder()
      .setCustomId('input_payee_name')
      .setLabel(`Payee / Shop Name (Optional):`)
      .setPlaceholder('e.g. John Store or My Personal UPI')
      .setValue(slot.name && !slot.name.startsWith('Slot') ? slot.name : '')
      .setStyle(TextInputStyle.Short)
      .setRequired(false);

    const row1 = new ActionRowBuilder().addComponents(upiInput);
    const row2 = new ActionRowBuilder().addComponents(nameInput);

    modal.addComponents(row1, row2);

    await interaction.showModal(modal);
  }

  /**
   * Render /qr UPI Selector Menu
   */
  async handleQrMenu(interaction, isUpdate = false) {
    const configuredSlots = storage.getConfiguredSlots(interaction.user.id);

    if (configuredSlots.length === 0) {
      const embed = new EmbedBuilder()
        .setTitle('⚠️ No UPI IDs Configured Yet!')
        .setDescription('Please configure at least 1 UPI ID slot before generating QR codes.')
        .setColor('#EF4444');

      const actionRow = new ActionRowBuilder().addComponents(
        new ButtonBuilder()
          .setCustomId('btn_trigger_upi_set')
          .setLabel('⚙️ Configure UPI IDs Now')
          .setStyle(ButtonStyle.Primary)
      );

      const payload = { embeds: [embed], components: [actionRow], ephemeral: true };
      if (isUpdate) await interaction.update(payload);
      else await interaction.reply(payload);
      return;
    }

    const embed = new EmbedBuilder()
      .setTitle('📱 Select UPI Slot for Custom QR')
      .setDescription('Choose which saved UPI ID you want to receive the payment into:')
      .setColor('#5865F2');

    const selectMenu = new StringSelectMenuBuilder()
      .setCustomId('select_qr_slot')
      .setPlaceholder('Select a UPI ID slot...');

    configuredSlots.forEach((s) => {
      selectMenu.addOptions({
        label: `Slot ${s.id}: ${s.name}`,
        description: s.upiId,
        value: String(s.id),
        emoji: '💳'
      });
    });

    const row = new ActionRowBuilder().addComponents(selectMenu);
    const payload = { embeds: [embed], components: [row] };

    if (isUpdate) await interaction.update(payload);
    else await interaction.reply(payload);
  }

  /**
   * Step 2 of /qr: Amount Selection Buttons for selected slot
   */
  async handleAmountMenuForSlot(interaction, slotId) {
    const profile = storage.getUserProfile(interaction.user.id);
    const slot = profile.slots.find(s => s.id === slotId);

    if (!slot || !slot.upiId) {
      await interaction.reply({ content: `❌ Slot ${slotId} is empty.`, ephemeral: true });
      return;
    }

    const embed = new EmbedBuilder()
      .setTitle(`💰 Select Amount for QR Code`)
      .setDescription(`💳 **Selected Payee:** \`${slot.name}\` (\`${slot.upiId}\`)\n\nClick a quick amount button below or enter a custom amount:`)
      .setColor('#3B82F6');

    const row1 = new ActionRowBuilder().addComponents(
      new ButtonBuilder().setCustomId(`btn_amt_${slot.id}_50`).setLabel('₹50').setStyle(ButtonStyle.Secondary),
      new ButtonBuilder().setCustomId(`btn_amt_${slot.id}_100`).setLabel('₹100').setStyle(ButtonStyle.Secondary),
      new ButtonBuilder().setCustomId(`btn_amt_${slot.id}_200`).setLabel('₹200').setStyle(ButtonStyle.Secondary),
      new ButtonBuilder().setCustomId(`btn_amt_${slot.id}_300`).setLabel('₹300').setStyle(ButtonStyle.Success)
    );

    const row2 = new ActionRowBuilder().addComponents(
      new ButtonBuilder().setCustomId(`btn_amt_${slot.id}_500`).setLabel('₹500').setStyle(ButtonStyle.Success),
      new ButtonBuilder().setCustomId(`btn_amt_${slot.id}_1000`).setLabel('₹1000').setStyle(ButtonStyle.Primary),
      new ButtonBuilder().setCustomId(`btn_amt_${slot.id}_2000`).setLabel('₹2000').setStyle(ButtonStyle.Primary),
      new ButtonBuilder().setCustomId(`btn_amt_${slot.id}_custom`).setLabel('✏️ Custom Amount').setStyle(ButtonStyle.Danger)
    );

    await interaction.update({ embeds: [embed], components: [row1, row2] });
  }

  /**
   * Show Custom Amount Modal
   */
  async showCustomAmountModal(interaction, slotId) {
    const modal = new ModalBuilder()
      .setCustomId(`modal_custom_amt_${slotId}`)
      .setTitle('Enter Custom Payment Amount');

    const amtInput = new TextInputBuilder()
      .setCustomId('input_custom_amount')
      .setLabel('Amount in ₹ (e.g. 300, 450.50):')
      .setPlaceholder('300')
      .setStyle(TextInputStyle.Short)
      .setRequired(true);

    modal.addComponents(new ActionRowBuilder().addComponents(amtInput));
    await interaction.showModal(modal);
  }

  /**
   * Generate QR Code & Send to Discord Channel via Interaction
   */
  async generateAndSendDiscordQR(interaction, slotId, amount) {
    const userId = interaction.user.id;
    const profile = storage.getUserProfile(userId);
    const slot = profile.slots.find(s => s.id === slotId);

    if (!slot || !slot.upiId) {
      await interaction.reply({ content: `❌ Slot ${slotId} is empty!`, ephemeral: true });
      return;
    }

    if (!interaction.deferred && !interaction.replied) {
      await interaction.deferReply();
    }

    const upiUrl = upiUtils.buildUPIUrl(slot.upiId, amount, slot.name, `Payment of Rs ${amount}`);
    const qrBuffer = await upiUtils.generateQRBuffer(upiUrl);

    const attachment = new AttachmentBuilder(qrBuffer, { name: `upi_qr_${amount}.png` });

    const embed = new EmbedBuilder()
      .setTitle(`⚡ Custom Value UPI QR Generated`)
      .setColor('#10B981')
      .setImage(`attachment://upi_qr_${amount}.png`)
      .addFields(
        { name: '💵 Amount', value: `**₹${amount}**`, inline: true },
        { name: '💳 UPI ID', value: `\`${slot.upiId}\``, inline: true },
        { name: '👤 Payee Name', value: `\`${slot.name}\``, inline: true },
        { name: '🔗 Direct UPI Link', value: `[Tap to Pay (${upiUrl})](${upiUrl})` }
      )
      .setFooter({ text: 'Scan with GPay, PhonePe, Paytm, BHIM, Cred or any UPI app to pay!' });

    const actionRow = new ActionRowBuilder().addComponents(
      new ButtonBuilder().setLabel('Open in PhonePe').setStyle(ButtonStyle.Link).setURL(`phonepe://pay?${upiUrl.replace('upi://pay?', '')}`),
      new ButtonBuilder().setLabel('Open in GPay').setStyle(ButtonStyle.Link).setURL(`gpay://upi/pay?${upiUrl.replace('upi://pay?', '')}`),
      new ButtonBuilder().setLabel('Open in Paytm').setStyle(ButtonStyle.Link).setURL(`paytmmp://pay?${upiUrl.replace('upi://pay?', '')}`)
    );

    await interaction.editReply({ embeds: [embed], files: [attachment], components: [actionRow] });
  }

  /**
   * Prefix command handlers for Discord messages (!upi set, !qr, !myupi, !help)
   */
  async handleUpiSetMessage(message) {
    const profile = storage.getUserProfile(message.author.id);
    const embed = new EmbedBuilder()
      .setTitle('⚙️ Multi-Slot UPI ID Manager')
      .setDescription('Use slash command `/upi-set` in chat to open interactive popup modals and configure your 4 UPI slots!')
      .setColor('#5865F2');

    profile.slots.forEach(s => {
      embed.addFields({
        name: `Slot ${s.id} ${s.upiId ? '✅' : '❌'}`,
        value: s.upiId ? `💳 \`${s.upiId}\` (${s.name})` : `*Not set*`,
        inline: true
      });
    });

    await message.reply({ embeds: [embed] });
  }

  async handleQrMessage(message) {
    await message.reply('📱 Please type `/qr` as a slash command to open the interactive UPI & amount selection menu!');
  }

  async handleMyUpi(interaction) {
    const profile = storage.getUserProfile(interaction.user.id);
    const embed = new EmbedBuilder().setTitle('💳 Stored UPI ID Slots').setColor('#3B82F6');
    profile.slots.forEach(s => {
      embed.addFields({
        name: `Slot ${s.id}: ${s.name}`,
        value: s.upiId ? `\`${s.upiId}\`` : `*Not Configured*`,
        inline: true
      });
    });
    await interaction.reply({ embeds: [embed], ephemeral: true });
  }

  async handleHelp(interaction) {
    const embed = new EmbedBuilder()
      .setTitle('ℹ️ Custom UPI QR Discord Bot Help')
      .setDescription(
        '1️⃣ Use `/upi-set` to open the slot configuration pop-up menu.\n' +
        '2️⃣ Choose Slot 1, 2, 3, or 4 and type your UPI ID in the modal window.\n' +
        '3️⃣ Use `/qr` to pick your UPI ID and select an amount (e.g. ₹300).\n' +
        '4️⃣ Or type any number directly in chat (e.g. `300`) to generate your payment QR code instantly!'
      )
      .setColor('#5865F2');
    await interaction.reply({ embeds: [embed], ephemeral: true });
  }

  async handleMyUpiMessage(message) {
    const profile = storage.getUserProfile(message.author.id);
    const embed = new EmbedBuilder().setTitle('💳 Stored UPI ID Slots').setColor('#3B82F6');
    profile.slots.forEach(s => {
      embed.addFields({
        name: `Slot ${s.id}: ${s.name}`,
        value: s.upiId ? `\`${s.upiId}\`` : `*Not Configured*`,
        inline: true
      });
    });
    await message.reply({ embeds: [embed] });
  }

  async handleHelpMessage(message) {
    const embed = new EmbedBuilder()
      .setTitle('ℹ️ Custom UPI QR Discord Bot Help')
      .setDescription(
        '1️⃣ Use `/upi-set` to open the slot configuration pop-up menu.\n' +
        '2️⃣ Choose Slot 1, 2, 3, or 4 and type your UPI ID in the modal window.\n' +
        '3️⃣ Use `/qr` to pick your UPI ID and select an amount (e.g. ₹300).\n' +
        '4️⃣ Or type any number directly in chat (e.g. `300`) to generate your payment QR code instantly!'
      )
      .setColor('#5865F2');
    await message.reply({ embeds: [embed] });
  }

  async generateAndSendDiscordQRMessage(message, slotId, amount) {
    const profile = storage.getUserProfile(message.author.id);
    const slot = profile.slots.find(s => s.id === slotId);
    if (!slot || !slot.upiId) return;

    const upiUrl = upiUtils.buildUPIUrl(slot.upiId, amount, slot.name, `Payment of Rs ${amount}`);
    const qrBuffer = await upiUtils.generateQRBuffer(upiUrl);
    const attachment = new AttachmentBuilder(qrBuffer, { name: `upi_qr_${amount}.png` });

    const embed = new EmbedBuilder()
      .setTitle(`⚡ Custom Value UPI QR Generated`)
      .setColor('#10B981')
      .setImage(`attachment://upi_qr_${amount}.png`)
      .addFields(
        { name: '💵 Amount', value: `**₹${amount}**`, inline: true },
        { name: '💳 UPI ID', value: `\`${slot.upiId}\``, inline: true },
        { name: '👤 Payee Name', value: `\`${slot.name}\``, inline: true }
      );

    await message.reply({ embeds: [embed], files: [attachment] });
  }

  async sendSlotPickerForAmountMessage(message, amount) {
    const configuredSlots = storage.getConfiguredSlots(message.author.id);
    const embed = new EmbedBuilder()
      .setTitle(`💸 Select UPI Slot for ₹${amount}`)
      .setDescription(`Select which UPI ID slot to generate the QR code for:`)
      .setColor('#3B82F6');

    const selectMenu = new StringSelectMenuBuilder()
      .setCustomId(`select_slot_for_amt_${amount}`)
      .setPlaceholder('Choose a UPI ID...');

    configuredSlots.forEach(s => {
      selectMenu.addOptions({
        label: `Slot ${s.id}: ${s.name}`,
        description: s.upiId,
        value: String(s.id),
        emoji: '💳'
      });
    });

    const row = new ActionRowBuilder().addComponents(selectMenu);
    await message.reply({ embeds: [embed], components: [row] });
  }
}

module.exports = CustomUpiDiscordBot;
