const fs = require('fs');
const path = require('path');

const DB_FILE = path.join(__dirname, '../data/users_db.json');

// Ensure data directory exists
const dataDir = path.dirname(DB_FILE);
if (!fs.existsSync(dataDir)) {
  fs.mkdirSync(dataDir, { recursive: true });
}

// Load DB
function loadDB() {
  if (!fs.existsSync(DB_FILE)) {
    return {};
  }
  try {
    const raw = fs.readFileSync(DB_FILE, 'utf8');
    return JSON.parse(raw || '{}');
  } catch (err) {
    console.error('Error reading DB file, resetting:', err.message);
    return {};
  }
}

// Save DB
function saveDB(db) {
  try {
    fs.writeFileSync(DB_FILE, JSON.stringify(db, null, 2), 'utf8');
  } catch (err) {
    console.error('Error writing DB file:', err.message);
  }
}

// Initialize default slots for user
function defaultProfile(userId) {
  return {
    userId: String(userId),
    createdAt: new Date().toISOString(),
    slots: [
      { id: 1, upiId: '', name: 'Slot 1' },
      { id: 2, upiId: '', name: 'Slot 2' },
      { id: 3, upiId: '', name: 'Slot 3' },
      { id: 4, upiId: '', name: 'Slot 4' }
    ],
    state: null // transient conversation state, e.g. { step: 'AWAITING_UPI_INPUT', targetSlot: 1 }
  };
}

// Public Methods
function getUserProfile(userId) {
  const db = loadDB();
  const uid = String(userId);
  if (!db[uid]) {
    db[uid] = defaultProfile(uid);
    saveDB(db);
  }
  // Ensure array has 4 slots
  if (!db[uid].slots || !Array.isArray(db[uid].slots) || db[uid].slots.length < 4) {
    db[uid].slots = defaultProfile(uid).slots;
    saveDB(db);
  }
  return db[uid];
}

function updateSlot(userId, slotId, upiId, name = '') {
  const db = loadDB();
  const uid = String(userId);
  if (!db[uid]) {
    db[uid] = defaultProfile(uid);
  }

  const sId = parseInt(slotId, 10);
  const slotIndex = db[uid].slots.findIndex(s => s.id === sId);
  if (slotIndex !== -1) {
    db[uid].slots[slotIndex].upiId = upiId.trim();
    if (name && name.trim()) {
      db[uid].slots[slotIndex].name = name.trim();
    } else if (!db[uid].slots[slotIndex].name || db[uid].slots[slotIndex].name.startsWith('Slot')) {
      db[uid].slots[slotIndex].name = `UPI Slot ${sId}`;
    }
  }
  saveDB(db);
  return db[uid];
}

function deleteSlot(userId, slotId) {
  const db = loadDB();
  const uid = String(userId);
  if (db[uid]) {
    const sId = parseInt(slotId, 10);
    const slotIndex = db[uid].slots.findIndex(s => s.id === sId);
    if (slotIndex !== -1) {
      db[uid].slots[slotIndex].upiId = '';
      db[uid].slots[slotIndex].name = `Slot ${sId}`;
      saveDB(db);
    }
  }
  return db[uid];
}

function setUserState(userId, stateObject) {
  const db = loadDB();
  const uid = String(userId);
  if (!db[uid]) {
    db[uid] = defaultProfile(uid);
  }
  db[uid].state = stateObject;
  saveDB(db);
}

function clearUserState(userId) {
  setUserState(userId, null);
}

function getConfiguredSlots(userId) {
  const profile = getUserProfile(userId);
  return profile.slots.filter(s => s.upiId && s.upiId.trim().length > 0);
}

module.exports = {
  getUserProfile,
  updateSlot,
  deleteSlot,
  setUserState,
  clearUserState,
  getConfiguredSlots
};
