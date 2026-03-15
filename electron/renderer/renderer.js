'use strict';

/**
 * myHards — Renderer process
 * All DOM interaction, state management, and calls to the Python backend
 * happen here through window.api (exposed by preload.js).
 */

// ── State ─────────────────────────────────────────────────────────────────────
let serverRunning = false;
let clientRunning = false;
let config        = {};
const MAX_LOG_LINES = 500;
let logLines        = 0;
let logText         = '';   // shadow buffer — avoids reading back from DOM
// ── DOM refs ──────────────────────────────────────────────────────────────────
const $ = (id) => document.getElementById(id);

const serverDot    = $('server-dot');
const serverStatus = $('server-status');
const clientDot    = $('client-dot');
const clientStatus = $('client-status');
const localIpEl    = $('local-ip-large');
const statusText   = $('status-text');
const logContent   = $('log-content');
const logScroll    = $('log-scroll');
const inputIp      = $('input-ip');

const btnStartServer = $('btn-start-server');
const btnStopServer  = $('btn-stop-server');
const btnStartClient = $('btn-start-client');
const btnStopClient  = $('btn-stop-client');
const btnSaveConfig  = $('btn-save-config');
const btnResetConfig = $('btn-reset-config');

// Titlebar controls
const btnWinMinimize  = $('btn-win-minimize');
const btnWinMaximize  = $('btn-win-maximize');
const btnWinClose     = $('btn-win-close');

// Settings inputs
const cfgPort      = $('cfg-port');
const cfgEdge      = $('cfg-edge');
const cfgMargin    = $('cfg-margin');
const cfgSpeed     = $('cfg-speed');
const cfgHeartbeat = $('cfg-heartbeat');
const cfgHotkey    = $('cfg-hotkey');
const cfgSecret    = $('cfg-secret');
const cfgClipboard = $('cfg-clipboard');

// ── Logging ───────────────────────────────────────────────────────────────────
function log(msg) {
  const ts = new Date().toTimeString().slice(0, 8);
  const line = `[${ts}] ${msg}\n`;

  // Trim oldest 50 lines when cap is reached (operates on shadow buffer, one DOM write)
  if (logLines >= MAX_LOG_LINES) {
    const idx = nthNewline(logText, 50);
    logText  = logText.slice(idx + 1);
    logLines -= 50;
  }
  logText += line;
  logLines++;
  logContent.textContent = logText;

  // Auto-scroll only when already near the bottom
  if (logScroll.scrollHeight - logScroll.scrollTop - logScroll.clientHeight < 60)
    logScroll.scrollTop = logScroll.scrollHeight;
}

/** Return index of the n-th '\n' in str (0-based). */
function nthNewline(str, n) {
  let idx = -1;
  for (let i = 0; i < n; i++) {
    idx = str.indexOf('\n', idx + 1);
    if (idx === -1) return str.length - 1;
  }
  return idx;
}

// ── Status bar ────────────────────────────────────────────────────────────────
function updateStatusBar() {
  const parts = [];
  if (serverRunning) parts.push('Servidor: ON');
  if (clientRunning) parts.push('Cliente: ON');
  if (!serverRunning && !clientRunning) parts.push('Listo');
  statusText.textContent = parts.join('  |  ');
}

// ── Server state ──────────────────────────────────────────────────────────────
function setServerState(running) {
  serverRunning = running;
  btnStartServer.disabled = running;
  btnStopServer.disabled  = !running;
  serverDot.classList.toggle('on', running);
  serverStatus.textContent = running ? 'Ejecutando — esperando cliente…' : 'Detenido';
  serverStatus.style.color = running ? 'var(--green)' : 'var(--fg-dim)';
  updateStatusBar();
}

// ── Client state ──────────────────────────────────────────────────────────────
function setClientState(running) {
  clientRunning = running;
  btnStartClient.disabled = running;
  btnStopClient.disabled  = !running;
  inputIp.disabled        = running;
  clientDot.classList.toggle('on', running);
  clientStatus.textContent = running ? 'Conectado' : 'Desconectado';
  clientStatus.style.color = running ? 'var(--green)' : 'var(--fg-dim)';
  updateStatusBar();
}

// ── Config helpers ────────────────────────────────────────────────────────────
function configFromUi() {
  return {
    port:                  parseInt(cfgPort.value,      10) || 24800,
    switch_edge:           cfgEdge.value,
    switch_margin:         parseInt(cfgMargin.value,    10) || 2,
    client_screen_width:   1920,
    client_screen_height:  1080,
    client_pointer_speed:  parseFloat(cfgSpeed.value)  || 1.0,
    clipboard_sync:        cfgClipboard.checked,
    heartbeat_interval:    parseInt(cfgHeartbeat.value, 10) || 5,
    switch_hotkey:         cfgHotkey.value.trim() || '<ctrl>+<alt>+s',
    shared_secret:         cfgSecret.value.trim(),
    last_server_ip:        inputIp.value.trim(),
  };
}

function applyConfigToUi(cfg) {
  cfgPort.value      = cfg.port ?? 24800;
  cfgEdge.value      = cfg.switch_edge ?? 'right';
  cfgMargin.value    = cfg.switch_margin ?? 2;
  cfgSpeed.value     = cfg.client_pointer_speed ?? 1.0;
  cfgHeartbeat.value = cfg.heartbeat_interval ?? 5;
  cfgHotkey.value    = cfg.switch_hotkey ?? '<ctrl>+<alt>+s';
  cfgSecret.value    = cfg.shared_secret ?? '';
  cfgClipboard.checked = cfg.clipboard_sync !== false;
  if (cfg.last_server_ip) inputIp.value = cfg.last_server_ip;
}

// ── Tabs ──────────────────────────────────────────────────────────────────────
const tabBtns   = document.querySelectorAll('.tab-btn');
const tabPanels = document.querySelectorAll('.tab-panel');

function activateTab(name) {
  tabBtns.forEach(b => b.classList.toggle('active', b.dataset.tab === name));
  tabPanels.forEach(p => p.classList.toggle('active', p.id === `tab-${name}`));
}

tabBtns.forEach(btn => btn.addEventListener('click', () => activateTab(btn.dataset.tab)));

// Enter on IP field triggers connect
inputIp.addEventListener('keydown', (e) => {
  if (e.key === 'Enter') btnStartClient.click();
});

// ── Button handlers ───────────────────────────────────────────────────────────
btnStartServer.addEventListener('click', async () => {
  const cfg = configFromUi();
  log('Iniciando servidor…');
  const ok = await window.api.startServer(cfg);
  if (ok) setServerState(true);
  else    log('El servidor ya está en ejecución.');
});

btnStopServer.addEventListener('click', async () => {
  log('Deteniendo servidor…');
  btnStopServer.disabled = true;
  await window.api.stopServer();
});

btnStartClient.addEventListener('click', async () => {
  const ip = inputIp.value.trim();
  if (!ip) { log('ERROR: Ingresa la IP del servidor primero.'); inputIp.focus(); return; }
  const cfg = { ...configFromUi(), last_server_ip: ip };
  log(`Cliente conectando a ${ip}…`);
  const ok = await window.api.startClient(cfg);
  if (ok) setClientState(true);
  else    log('El cliente ya está en ejecución.');
});

btnStopClient.addEventListener('click', async () => {
  log('Desconectando cliente…');
  btnStopClient.disabled = true;
  await window.api.stopClient();
});

btnSaveConfig.addEventListener('click', async () => {
  await window.api.saveConfig(configFromUi());
  log('Configuración guardada en config.json');
});

btnResetConfig.addEventListener('click', async () => {
  const defaults = {
    port: 24800, switch_edge: 'right', switch_margin: 2,
    client_screen_width: 1920, client_screen_height: 1080,
    client_pointer_speed: 1.0, clipboard_sync: true,
    heartbeat_interval: 5, switch_hotkey: '<ctrl>+<alt>+s',
    shared_secret: '', last_server_ip: '',
  };
  await window.api.saveConfig(defaults);
  // Re-read from main process so the UI reflects what was actually persisted
  // (main process fills shared_secret with a new token if empty)
  const saved = await window.api.getConfig();
  applyConfigToUi(saved);
  log('Configuración restablecida a valores por defecto');
});

// ── Events from main process ──────────────────────────────────────────────────
window.api.onLog((msg) => log(msg));

window.api.onServerStopped(() => {
  setServerState(false);
  log('Servidor detenido');
});

window.api.onClientStopped(() => {
  setClientState(false);
  log('Cliente desconectado');
});

// ── Titlebar window controls ──────────────────────────────────────────────────
btnWinMinimize.addEventListener('click', () => window.api.winMinimize());

btnWinMaximize.addEventListener('click', () => window.api.winMaximizeToggle());

btnWinClose.addEventListener('click', () => window.api.winClose());

// Update maximize icon when the window is maximized/restored
function setMaximizeIcon(isMax) {
  // ❐ restore symbol when maximized, □ maximize symbol when normal
  btnWinMaximize.innerHTML = isMax ? '&#x2752;' : '&#x25A1;';
  btnWinMaximize.title     = isMax ? 'Restaurar' : 'Maximizar';
}

window.api.onWinMaximized((isMax) => setMaximizeIcon(isMax));

// Sync on load
window.api.winIsMaximized().then((isMax) => setMaximizeIcon(isMax));

// ── Menu shortcuts from main process ─────────────────────────────────────────
window.api.onMenuSaveConfig(async () => {
  await window.api.saveConfig(configFromUi());
  log('Configuración guardada en config.json');
});

window.api.onMenuTab((tab) => activateTab(tab));

// ── Init ──────────────────────────────────────────────────────────────────────
(async () => {
  const [ip, cfg] = await Promise.all([
    window.api.getLocalIp(),
    window.api.getConfig(),
  ]);
  config._localIp = ip;
  config = { ...cfg, _localIp: ip };
  if (localIpEl) localIpEl.textContent = ip;
  applyConfigToUi(cfg);
  updateStatusBar();
  log('myHards listo.');
})();
