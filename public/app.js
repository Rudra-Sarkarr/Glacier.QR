// Client Application Logic for Discord UPI QR Generator Bot
const USER_ID = 'web_user_demo';
let userProfile = { slots: [] };

document.addEventListener('DOMContentLoaded', () => {
  initTabs();
  loadUserProfile();
  initSimulator();
  initStudio();
  initBotController();
  checkBotStatus();
});

/* Tab Switching Logic */
function initTabs() {
  const tabBtns = document.querySelectorAll('.tab-btn');
  const tabContents = document.querySelectorAll('.tab-content');

  tabBtns.forEach(btn => {
    btn.addEventListener('click', () => {
      const target = btn.dataset.tab;

      tabBtns.forEach(b => b.classList.remove('active'));
      tabContents.forEach(c => c.classList.remove('active'));

      btn.classList.add('active');
      document.getElementById(`tab-${target}`).classList.add('active');
    });
  });
}

/* API Calls & Slot Management */
async function loadUserProfile() {
  try {
    const res = await fetch(`/api/user/${USER_ID}`);
    const data = await res.json();
    if (data.success) {
      userProfile = data.profile;
      renderSlotsGrid();
      populateStudioSlotSelect();
    }
  } catch (err) {
    console.error('Failed to load profile:', err);
  }
}

function renderSlotsGrid() {
  const grid = document.getElementById('slotsGrid');
  if (!grid) return;

  grid.innerHTML = '';

  userProfile.slots.forEach(slot => {
    const card = document.createElement('div');
    card.className = 'slot-card';

    const isSet = Boolean(slot.upiId);
    const statusText = isSet ? 'Configured' : 'Empty';
    const statusClass = isSet ? 'active' : 'empty';

    card.innerHTML = `
      <div class="slot-header">
        <span class="slot-num">Slot ${slot.id}</span>
        <span class="slot-status ${statusClass}">${statusText}</span>
      </div>
      <div class="slot-body">
        <strong>${slot.name || `Slot ${slot.id}`}</strong>
        <code>${slot.upiId || 'Not Configured'}</code>
      </div>
      <div class="slot-actions">
        <button class="btn-sm btn-edit" onclick="openWebSlotModal(${slot.id})">✏️ Edit Slot</button>
        ${isSet ? `<button class="btn-sm btn-delete" onclick="deleteSlot(${slot.id})">🗑️ Reset</button>` : ''}
      </div>
    `;

    grid.appendChild(card);
  });
}

function populateStudioSlotSelect() {
  const select = document.getElementById('studioSlotSelect');
  if (!select) return;

  select.innerHTML = '<option value="">-- Choose Stored Slot --</option>';

  userProfile.slots.forEach(s => {
    if (s.upiId) {
      const opt = document.createElement('option');
      opt.value = s.id;
      opt.textContent = `Slot ${s.id}: ${s.name} (${s.upiId})`;
      select.appendChild(opt);
    }
  });

  select.onchange = () => {
    const sId = parseInt(select.value, 10);
    const found = userProfile.slots.find(s => s.id === sId);
    if (found && found.upiId) {
      document.getElementById('studioUpiId').value = found.upiId;
      document.getElementById('studioPayeeName').value = found.name;
    }
  };
}

/* Modal Slot Editor for Web UI */
function openWebSlotModal(slotId) {
  const slot = userProfile.slots.find(s => s.id === slotId) || { upiId: '', name: '' };
  document.getElementById('modalTitle').textContent = `Configure UPI Slot ${slotId}`;
  document.getElementById('modalSlotId').value = slotId;
  document.getElementById('modalUpiId').value = slot.upiId || '';
  document.getElementById('modalPayeeName').value = slot.name && !slot.name.startsWith('Slot') ? slot.name : '';

  document.getElementById('webSlotModal').classList.remove('hidden');
}

document.getElementById('closeModalBtn')?.addEventListener('click', () => {
  document.getElementById('webSlotModal').classList.add('hidden');
});

document.getElementById('webSlotForm')?.addEventListener('submit', async (e) => {
  e.preventDefault();
  const slotId = parseInt(document.getElementById('modalSlotId').value, 10);
  const upiId = document.getElementById('modalUpiId').value.trim();
  const name = document.getElementById('modalPayeeName').value.trim();

  try {
    const res = await fetch('/api/user/slot', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ userId: USER_ID, slotId, upiId, name })
    });
    const data = await res.json();
    if (data.success) {
      document.getElementById('webSlotModal').classList.add('hidden');
      await loadUserProfile();
    } else {
      alert(`Error: ${data.error}`);
    }
  } catch (err) {
    alert(`Failed to save slot: ${err.message}`);
  }
});

async function deleteSlot(slotId) {
  if (!confirm(`Are you sure you want to reset Slot ${slotId}?`)) return;
  try {
    const res = await fetch('/api/user/slot', {
      method: 'DELETE',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ userId: USER_ID, slotId })
    });
    const data = await res.json();
    if (data.success) {
      await loadUserProfile();
    }
  } catch (err) {
    console.error('Error resetting slot:', err);
  }
}

/* Discord Bot Simulator Logic */
function initSimulator() {
  const chatForm = document.getElementById('chatForm');
  const chatInput = document.getElementById('chatInput');

  // Quick Action Buttons
  document.getElementById('simCmdHelp')?.addEventListener('click', () => sendSimMessage('/help'));
  document.getElementById('simCmdUpiSet')?.addEventListener('click', () => sendSimMessage('/upi-set'));
  document.getElementById('simCmdQr')?.addEventListener('click', () => sendSimMessage('/qr'));
  document.getElementById('simCmd300')?.addEventListener('click', () => sendSimMessage('300'));

  // Welcome message
  addSimBotEmbed({
    title: '✨ Welcome to Custom Value UPI QR Discord Bot!',
    description: 'Store up to 4 UPI IDs and generate custom amount payment QR codes (e.g., ₹300) directly in Discord.\n\nType `/upi-set` or `/qr` to get started!',
    color: '#5865F2',
    buttons: [
      { text: '⚙️ Configure UPI Slots (/upi-set)', action: () => handleSimUpiSet() },
      { text: '📱 Generate Custom QR (/qr)', action: () => handleSimQr() }
    ]
  });

  chatForm?.addEventListener('submit', (e) => {
    e.preventDefault();
    const txt = chatInput.value.trim();
    if (txt) {
      sendSimMessage(txt);
      chatInput.value = '';
    }
  });
}

function sendSimMessage(text) {
  addSimUserMessage(text);

  const lower = text.toLowerCase();

  setTimeout(async () => {
    if (lower === '/help' || lower === '!help') {
      addSimBotEmbed({
        title: 'ℹ️ Custom UPI QR Discord Bot Help',
        description: '1️⃣ Run `/upi-set` to open slot configuration pop-up menu.\n2️⃣ Save your UPI ID (e.g. `shop@paytm`).\n3️⃣ Run `/qr` to select slot & amount (e.g., ₹300).\n4️⃣ Or type any number directly (e.g. `300`)!',
        color: '#5865F2'
      });
    } else if (lower === '/upi-set' || lower === '!upi set' || lower === '!upiset') {
      handleSimUpiSet();
    } else if (lower === '/qr' || lower === '!qr') {
      handleSimQr();
    } else if (!isNaN(parseFloat(text))) {
      const amt = parseFloat(text);
      handleSimAmountEntry(amt);
    } else {
      addSimBotEmbed({
        title: '🤖 Unknown Command',
        description: `Command \`${text}\` not recognized. Try \`/upi-set\` or \`/qr\`!`,
        color: '#EF4444'
      });
    }
  }, 400);
}

function addSimUserMessage(text) {
  const body = document.getElementById('chatBody');
  const row = document.createElement('div');
  row.className = 'msg-row';
  row.innerHTML = `
    <div class="msg-user-avatar">U</div>
    <div class="msg-content">
      <div class="msg-author">You <span class="time">${new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}</span></div>
      <div class="msg-bubble">${escapeHtml(text)}</div>
    </div>
  `;
  body.appendChild(row);
  body.scrollTop = body.scrollHeight;
}

function addSimBotEmbed(options) {
  const body = document.getElementById('chatBody');
  const row = document.createElement('div');
  row.className = 'msg-row';

  let embedHtml = `
    <div class="discord-embed" style="border-left-color: ${options.color || '#5865F2'}">
      <div class="embed-title">${options.title}</div>
      ${options.description ? `<div class="embed-desc">${options.description.replace(/\n/g, '<br>')}</div>` : ''}
  `;

  if (options.fields && options.fields.length > 0) {
    embedHtml += `<div class="embed-fields">`;
    options.fields.forEach(f => {
      embedHtml += `<div><div class="embed-field-title">${f.name}</div><div class="embed-field-val">${f.value}</div></div>`;
    });
    embedHtml += `</div>`;
  }

  if (options.qrDataUrl) {
    embedHtml += `<img src="${options.qrDataUrl}" class="embed-qr-img" alt="UPI QR Code">`;
  }

  if (options.buttons && options.buttons.length > 0) {
    embedHtml += `<div class="discord-actions" id="btnGroup_${Date.now()}"></div>`;
  }

  if (options.selectOptions && options.selectOptions.length > 0) {
    embedHtml += `<select class="d-select" id="selectGroup_${Date.now()}">
      <option value="">Choose a slot...</option>
      ${options.selectOptions.map(o => `<option value="${o.value}">${o.label}</option>`).join('')}
    </select>`;
  }

  embedHtml += `</div>`;

  row.innerHTML = `
    <div class="chat-bot-avatar">🤖</div>
    <div class="msg-content">
      <div class="msg-author">UPI QR Bot <span class="bot-tag">BOT</span> <span class="time">${new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}</span></div>
      ${embedHtml}
    </div>
  `;

  body.appendChild(row);

  // Attach button event handlers
  if (options.buttons) {
    const btnGroup = row.querySelector('.discord-actions');
    options.buttons.forEach(b => {
      const btn = document.createElement('button');
      btn.className = `d-btn ${b.style || 'primary'}`;
      btn.textContent = b.text;
      btn.onclick = b.action;
      btnGroup.appendChild(btn);
    });
  }

  // Attach select event handlers
  if (options.selectOptions && options.onSelect) {
    const select = row.querySelector('.d-select');
    select.onchange = (e) => {
      if (e.target.value) {
        options.onSelect(e.target.value);
      }
    };
  }

  body.scrollTop = body.scrollHeight;
}

function handleSimUpiSet() {
  const fields = userProfile.slots.map(s => ({
    name: `Slot ${s.id} ${s.upiId ? '✅' : '❌'}`,
    value: s.upiId ? `💳 \`${s.upiId}\`<br>👤 ${s.name}` : `*Not Set*`
  }));

  const buttons = userProfile.slots.map(s => ({
    text: s.upiId ? `Edit Slot ${s.id} (${s.name})` : `Set Slot ${s.id}`,
    style: s.upiId ? 'success' : 'primary',
    action: () => openWebSlotModal(s.id)
  }));

  addSimBotEmbed({
    title: '⚙️ Multi-Slot UPI ID Manager',
    description: 'Store up to 4 UPI IDs. Click any button below to open pop-up modal configuration:',
    color: '#5865F2',
    fields,
    buttons
  });
}

function handleSimQr() {
  const configured = userProfile.slots.filter(s => s.upiId);

  if (configured.length === 0) {
    addSimBotEmbed({
      title: '⚠️ No UPI IDs Configured Yet!',
      description: 'Please set up at least 1 UPI ID slot before generating QR codes.',
      color: '#EF4444',
      buttons: [{ text: '⚙️ Configure UPI Slots', action: () => handleSimUpiSet() }]
    });
    return;
  }

  const selectOptions = configured.map(s => ({
    value: s.id,
    label: `Slot ${s.id}: ${s.name} (${s.upiId})`
  }));

  addSimBotEmbed({
    title: '📱 Select UPI Slot for Custom QR',
    description: 'Choose which saved UPI ID you want to receive payment into:',
    color: '#5865F2',
    selectOptions,
    onSelect: (slotId) => handleSimAmountMenu(parseInt(slotId, 10))
  });
}

function handleSimAmountMenu(slotId) {
  const slot = userProfile.slots.find(s => s.id === slotId);
  if (!slot) return;

  const amounts = [50, 100, 200, 300, 500, 1000];
  const buttons = amounts.map(amt => ({
    text: `₹${amt}`,
    style: amt === 300 ? 'success' : 'primary',
    action: () => generateSimQR(slot, amt)
  }));

  buttons.push({
    text: '✏️ Custom Amount',
    style: 'danger',
    action: () => {
      const customVal = prompt('Enter custom amount in ₹:', '300');
      if (customVal && !isNaN(parseFloat(customVal))) {
        generateSimQR(slot, parseFloat(customVal));
      }
    }
  });

  addSimBotEmbed({
    title: `💰 Select Amount for QR Code`,
    description: `💳 **Payee:** \`${slot.name}\` (\`${slot.upiId}\`)\n\nClick a quick amount button below:`,
    color: '#3B82F6',
    buttons
  });
}

function handleSimAmountEntry(amount) {
  const configured = userProfile.slots.filter(s => s.upiId);
  if (configured.length === 0) {
    addSimBotEmbed({
      title: '💡 Amount Entered',
      description: `You requested a QR code for **₹${amount}**, but no UPI slot is configured yet!\n\nClick below to configure:`,
      color: '#F59E0B',
      buttons: [{ text: '⚙️ Configure UPI Slots', action: () => handleSimUpiSet() }]
    });
  } else if (configured.length === 1) {
    generateSimQR(configured[0], amount);
  } else {
    const selectOptions = configured.map(s => ({
      value: s.id,
      label: `Slot ${s.id}: ${s.name} (${s.upiId})`
    }));

    addSimBotEmbed({
      title: `💸 Select UPI Slot for ₹${amount}`,
      description: `Which UPI ID slot should receive ₹${amount}?`,
      color: '#3B82F6',
      selectOptions,
      onSelect: (slotId) => {
        const slot = configured.find(s => s.id === parseInt(slotId, 10));
        if (slot) generateSimQR(slot, amount);
      }
    });
  }
}

async function generateSimQR(slot, amount) {
  try {
    const res = await fetch('/api/qr/generate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ upiId: slot.upiId, amount, name: slot.name })
    });

    const data = await res.json();
    if (data.success) {
      addSimBotEmbed({
        title: `⚡ Custom Value UPI QR Generated`,
        description: `Scan with GPay, PhonePe, Paytm, BHIM, Cred or any UPI app!`,
        color: '#10B981',
        fields: [
          { name: '💵 Amount', value: `**₹${data.amount}**` },
          { name: '💳 UPI ID', value: `\`${data.upiId}\`` },
          { name: '👤 Payee Name', value: `\`${data.payeeName}\`` }
        ],
        qrDataUrl: data.qrDataUrl,
        buttons: [
          { text: '⚡ Open in PhonePe', style: 'primary', action: () => window.open(data.appLinks.phonepe) },
          { text: '🔵 Open in GPay', style: 'primary', action: () => window.open(data.appLinks.gpay) },
          { text: '📲 Open in Paytm', style: 'primary', action: () => window.open(data.appLinks.paytm) }
        ]
      });
    }
  } catch (err) {
    console.error('Error generating sim QR:', err);
  }
}

/* Quick QR Code Studio */
function initStudio() {
  const form = document.getElementById('studioForm');
  const presetBtns = document.querySelectorAll('.preset-btn');

  presetBtns.forEach(btn => {
    btn.addEventListener('click', () => {
      document.getElementById('studioAmount').value = btn.dataset.val;
    });
  });

  form?.addEventListener('submit', async (e) => {
    e.preventDefault();
    const upiId = document.getElementById('studioUpiId').value.trim();
    const amount = document.getElementById('studioAmount').value.trim();
    const name = document.getElementById('studioPayeeName').value.trim();
    const note = document.getElementById('studioNote').value.trim();

    try {
      const res = await fetch('/api/qr/generate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ upiId, amount, name, note })
      });

      const data = await res.json();
      if (data.success) {
        document.getElementById('qrPlaceholder').classList.add('hidden');
        const img = document.getElementById('qrImage');
        img.src = data.qrDataUrl;
        img.classList.remove('hidden');

        document.getElementById('detAmount').textContent = `₹${data.amount}`;
        document.getElementById('detUpi').textContent = data.upiId;
        document.getElementById('detName').textContent = data.payeeName;
        document.getElementById('downloadQrBtn').href = data.qrDataUrl;

        const appContainer = document.getElementById('appButtons');
        appContainer.innerHTML = `
          <a href="${data.appLinks.phonepe}" class="app-link">PhonePe</a>
          <a href="${data.appLinks.gpay}" class="app-link">GPay</a>
          <a href="${data.appLinks.paytm}" class="app-link">Paytm</a>
        `;

        document.getElementById('qrDetails').classList.remove('hidden');
      } else {
        alert(`Error: ${data.error}`);
      }
    } catch (err) {
      alert(`Failed to generate QR: ${err.message}`);
    }
  });
}

/* Discord Bot Controller */
function initBotController() {
  const startBtn = document.getElementById('startBotBtn');
  const stopBtn = document.getElementById('stopBotBtn');
  const tokenInput = document.getElementById('botTokenInput');
  const clientIdInput = document.getElementById('clientIdInput');
  const msgBox = document.getElementById('botConsoleMsg');

  startBtn?.addEventListener('click', async () => {
    const token = tokenInput.value.trim();
    const clientId = clientIdInput.value.trim();

    if (!token) {
      showConsole('Please paste your Discord Bot Token first!', 'error');
      return;
    }

    showConsole('Logging into Discord...', 'success');

    try {
      const res = await fetch('/api/bot/start', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ token, clientId })
      });

      const data = await res.json();
      if (data.success) {
        showConsole('✅ Discord Bot launched successfully & online!', 'success');
        updateStatusBadge(true);
        startBtn.classList.add('hidden');
        stopBtn.classList.remove('hidden');
      } else {
        showConsole(`❌ Launch Failed: ${data.error}`, 'error');
      }
    } catch (err) {
      showConsole(`❌ Connection Error: ${err.message}`, 'error');
    }
  });

  stopBtn?.addEventListener('click', async () => {
    try {
      const res = await fetch('/api/bot/stop', { method: 'POST' });
      const data = await res.json();
      if (data.success) {
        showConsole('🛑 Discord Bot stopped.', 'error');
        updateStatusBadge(false);
        startBtn.classList.remove('hidden');
        stopBtn.classList.add('hidden');
      }
    } catch (err) {
      console.error(err);
    }
  });

  function showConsole(msg, type) {
    msgBox.textContent = msg;
    msgBox.className = `console-message ${type}`;
    msgBox.classList.remove('hidden');
  }
}

async function checkBotStatus() {
  try {
    const res = await fetch('/api/bot/status');
    const data = await res.json();
    updateStatusBadge(data.active, data.botUser);

    if (data.active) {
      document.getElementById('startBotBtn')?.classList.add('hidden');
      document.getElementById('stopBotBtn')?.classList.remove('hidden');
    }
  } catch (err) {
    console.error(err);
  }
}

function updateStatusBadge(active, botUser = null) {
  const badge = document.getElementById('botStatusBadge');
  if (!badge) return;

  const dot = badge.querySelector('.status-dot');
  const txt = badge.querySelector('.status-text');

  if (active) {
    dot.className = 'status-dot online';
    txt.textContent = botUser ? `Online (${botUser})` : 'Discord Bot Online';
  } else {
    dot.className = 'status-dot offline';
    txt.textContent = 'Discord Bot Offline';
  }
}

function escapeHtml(str) {
  return str.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}
