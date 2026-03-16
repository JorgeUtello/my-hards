/**
 * myHards — Electron main process
 * Spawns Python server.py / client.py as child processes,
 * streams their stdout to the renderer via IPC, and manages the tray icon.
 */

'use strict';

const { app, BrowserWindow, ipcMain, Tray, Menu, nativeImage, dialog } = require('electron');
const path = require('path');
const { spawn, exec } = require('child_process');
const fs   = require('fs');
const os   = require('os');

// ── Paths ─────────────────────────────────────────────────────────────────────
const ROOT        = path.join(__dirname, '..');
const CONFIG_PATH = path.join(ROOT, 'config.json');

// ── Defaults (mirrors config.py) ──────────────────────────────────────────────
const DEFAULT_CONFIG = {
  port: 24800,
  switch_edge: 'right',
  switch_margin: 2,
  client_screen_width: 1920,
  client_screen_height: 1080,
  client_pointer_speed: 1.0,
  clipboard_sync: true,
  heartbeat_interval: 5,
  switch_hotkey: '<ctrl>+<alt>+s',
  shared_secret: '',
  last_server_ip: '',
  // Webcam sharing
  webcam_share: false,
  camera_port: 24801,
  camera_fps: 15,
  camera_width: 640,
  camera_height: 480,
};

// ── State ─────────────────────────────────────────────────────────────────────
let mainWindow = null;
let tray       = null;
let serverProc = null;
let clientProc = null;

// ── Cached constants (computed once at startup) ───────────────────────────────
let   _localIp   = null;   // cached after first call
let   _config    = null;   // in-memory config cache
let   _trayIcon  = null;   // cached nativeImage

// ── Helpers ───────────────────────────────────────────────────────────────────
function getLocalIp() {
  if (_localIp) return _localIp;
  try {
    const interfaces = os.networkInterfaces();
    // Priority: prefer physical Wi-Fi / Ethernet over virtual and link-local.
    // Pass 1 — any routable (non-link-local) non-internal IPv4
    for (const name of Object.keys(interfaces)) {
      const isVirtual = /vethernet|hyper.?v|loopback|vmware|virtualbox|wsl|docker|vEthernet/i.test(name);
      if (isVirtual) continue;
      for (const iface of interfaces[name]) {
        if (iface.family === 'IPv4' && !iface.internal && !iface.address.startsWith('169.254.')) {
          _localIp = iface.address;
          return _localIp;
        }
      }
    }
    // Pass 2 — fallback: any non-internal IPv4 including link-local
    for (const name of Object.keys(interfaces)) {
      for (const iface of interfaces[name]) {
        if (iface.family === 'IPv4' && !iface.internal) {
          _localIp = iface.address;
          return _localIp;
        }
      }
    }
  } catch (_) {}
  _localIp = '127.0.0.1';
  return _localIp;
}

function loadConfig() {
  if (_config) return _config;
  try {
    const raw = fs.readFileSync(CONFIG_PATH, 'utf8');
    _config = Object.assign({}, DEFAULT_CONFIG, JSON.parse(raw));
  } catch (_) {
    _config = Object.assign({}, DEFAULT_CONFIG);
  }
  return _config;
}

function saveConfig(config) {
  const merged = Object.assign({}, DEFAULT_CONFIG, config);
  fs.writeFileSync(CONFIG_PATH, JSON.stringify(merged, null, 2), 'utf8');
  _config = merged;   // keep cache in sync
}

function resolvePythonCommand() {
  if (process.platform === 'win32') {
    const venvPython = path.join(ROOT, '.venv', 'Scripts', 'python.exe');
    if (fs.existsSync(venvPython)) return { command: venvPython, args: ['-u'] };
    return { command: 'py', args: ['-3', '-u'] };
  }

  const venvPython = path.join(ROOT, '.venv', 'bin', 'python');
  if (fs.existsSync(venvPython)) return { command: venvPython, args: ['-u'] };
  return { command: 'python3', args: ['-u'] };
}

function spawnPythonProcess(scriptName, extraArgs, prefix, stoppedEvent) {
  const python = resolvePythonCommand();
  const scriptPath = path.join(ROOT, scriptName);
  const proc = spawn(python.command, [...python.args, scriptPath, ...extraArgs], {
    cwd: ROOT,
    env: process.env,
    windowsHide: true,
  });

  attachOutput(proc, prefix);
  proc.once('error', (error) => {
    if (mainWindow && !mainWindow.isDestroyed()) {
      mainWindow.webContents.send('log', `[${prefix}] ERROR: ${error.message}`);
    }
  });
  proc.once('exit', () => {
    if (mainWindow && !mainWindow.isDestroyed()) {
      mainWindow.webContents.send(stoppedEvent);
    }
  });
  return proc;
}

/** Kill a child process gracefully, then forcefully after 1.5 s. */
function killProc(proc) {
  if (!proc || proc.killed || proc.exitCode !== null) return;
  try { proc.kill('SIGTERM'); } catch (_) {}
  setTimeout(() => {
    try { if (!proc.killed) proc.kill('SIGKILL'); } catch (_) {}
  }, 1500);
}

/**
 * Attach stdout/stderr streaming to a child process.
 * Each complete line is forwarded to the renderer as a 'log' event.
 */
function attachOutput(proc, prefix) {
  let buf = '';
  function flush(chunk) {
    buf += chunk.toString();
    const lines = buf.split('\n');
    buf = lines.pop(); // keep incomplete last line
    for (const line of lines) {
      const trimmed = line.trimEnd();
      if (trimmed && mainWindow && !mainWindow.isDestroyed()) {
        mainWindow.webContents.send('log', `[${prefix}] ${trimmed}`);
      }
    }
  }
  proc.stdout.on('data', flush);
  proc.stderr.on('data', flush);
  proc.once('close', () => {
    const trimmed = buf.trimEnd();
    if (trimmed && mainWindow && !mainWindow.isDestroyed()) {
      mainWindow.webContents.send('log', `[${prefix}] ${trimmed}`);
    }
    buf = '';
  });
}

// ── Virtual camera driver (OBS VirtualCam) ─────────────────────────────────
// CLSID of the OBS VirtualCam DirectShow filter (64-bit)
const OBS_VIRTUALCAM_CLSID = '{A3FCE0F5-3493-419F-958A-ABA1283EFE48}';
const OBS_DLL_NAME          = 'obs-virtualcam-module64.dll';

// Locations to search for the DLL, in priority order:
// 1. Bundled inside the app (electron/resources/driver/)
// 2. OBS Studio already installed on the system
const OBS_DLL_SEARCH_PATHS = [
  // Bundled
  app.isPackaged
    ? path.join(process.resourcesPath, 'driver', OBS_DLL_NAME)
    : path.join(__dirname, 'resources', 'driver', OBS_DLL_NAME),
  // OBS installed — standard locations
  path.join('C:\\', 'Program Files', 'obs-studio', 'data', 'obs-plugins', 'win-dshow', OBS_DLL_NAME),
  path.join('C:\\', 'Program Files (x86)', 'obs-studio', 'data', 'obs-plugins', 'win-dshow', OBS_DLL_NAME),
  // OBS from winget / MSIX sometimes installs to LocalAppData
  path.join(os.homedir(), 'AppData', 'Local', 'Programs', 'obs-studio', 'data', 'obs-plugins', 'win-dshow', OBS_DLL_NAME),
];

/** Return the first path where the DLL actually exists, or null. */
function findObsDll() {
  for (const p of OBS_DLL_SEARCH_PATHS) {
    if (fs.existsSync(p)) return p;
  }
  return null;
}

function isCameraDriverInstalled() {
  return new Promise((resolve) => {
    exec(
      `reg query "HKCR\\CLSID\\${OBS_VIRTUALCAM_CLSID}" /ve`,
      { windowsHide: true },
      (err) => resolve(!err),
    );
  });
}

function installCameraDriver(customPath) {
  return new Promise((resolve, reject) => {
    const driverPath = customPath || findObsDll();
    if (!driverPath) {
      reject(new Error(
        'No se encontró obs-virtualcam-module64.dll.\n\n' +
        'Opciones:\n' +
        '1. Instala OBS Studio (obsproject.com) — el driver se detectará automáticamente.\n' +
        '2. Copia obs-virtualcam-module64.dll a electron/resources/driver/\n' +
        '3. Usa el botón "Buscar DLL…" para seleccionarlo manualmente.',
      ));
      return;
    }
    // Use PowerShell + RunAs verb to trigger a UAC elevation prompt.
    // Do NOT use -PassThru | Select-Object ExitCode — it fails with elevated processes.
    // Instead, fire-and-wait then verify via registry.
    const escaped = driverPath.replace(/\\/g, '\\\\').replace(/'/g, "''");
    const psCmd = `Start-Process regsvr32 -ArgumentList @('/s','${escaped}') -Verb RunAs -Wait`;
    exec(
      `powershell -WindowStyle Hidden -Command "${psCmd}"`,
      { windowsHide: true },
      async (err) => {
        if (err) { reject(err); return; }
        // Verify by checking if the CLSID is now in the registry
        const registered = await isCameraDriverInstalled();
        resolve(registered);
      },
    );
  });
}

// ── Window ────────────────────────────────────────────────────────────────────
function createWindow() {
  mainWindow = new BrowserWindow({
    width: 820,
    height: 720,
    minWidth: 720,
    minHeight: 600,
    backgroundColor: '#1a1a2e',
    title: 'myHards',
    icon: buildTrayIcon(),   // reuse the generated icon for taskbar/alt-tab
    frame: false,          // remove native titlebar completely
    show: false,           // shown after ready-to-show to avoid flicker
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
    },
  });

  mainWindow.loadFile(path.join(__dirname, 'renderer', 'index.html'));

  mainWindow.once('ready-to-show', () => mainWindow.show());

  // Notify renderer when maximize state changes so the icon updates
  mainWindow.on('maximize',   () => mainWindow.webContents.send('win-maximized', true));
  mainWindow.on('unmaximize', () => mainWindow.webContents.send('win-maximized', false));

  // Minimise to tray instead of closing
  mainWindow.on('close', (e) => {
    if (!app.isQuitting) {
      e.preventDefault();
      mainWindow.hide();
      if (!tray) createTray();
    }
  });
}

// ── Window-control IPC (custom titlebar buttons) ──────────────────────────────
ipcMain.handle('win-minimize', () => {
  if (!mainWindow) return;
  mainWindow.hide();
  if (!tray) createTray();
});
ipcMain.handle('win-maximize-toggle', () => {
  if (!mainWindow) return;
  mainWindow.isMaximized() ? mainWindow.unmaximize() : mainWindow.maximize();
});
ipcMain.handle('win-close',           () => { mainWindow?.close(); });
ipcMain.handle('win-is-maximized',    () => mainWindow?.isMaximized() ?? false);

// ── Tray icon (generated once, cached) ───────────────────────────────────────
function buildTrayIcon() {
  if (_trayIcon) return _trayIcon;
  const S   = 32;
  const buf = Buffer.alloc(S * S * 4, 0); // all transparent

  // Set one pixel — Windows tray expects BGRA
  const px = (x, y, r, g, b) => {
    if (x < 0 || x >= S || y < 0 || y >= S) return;
    const i = (y * S + x) * 4;
    buf[i] = b; buf[i + 1] = g; buf[i + 2] = r; buf[i + 3] = 255;
  };
  const rect = (x1, y1, x2, y2, r, g, b) => {
    for (let y = y1; y <= y2; y++)
      for (let x = x1; x <= x2; x++) px(x, y, r, g, b);
  };
  const border = (x1, y1, x2, y2, r, g, b) => {
    for (let x = x1; x <= x2; x++) { px(x, y1, r, g, b); px(x, y2, r, g, b); }
    for (let y = y1; y <= y2; y++) { px(x1, y, r, g, b); px(x2, y, r, g, b); }
  };

  // Two overlapping squares design (mirrors the SVG in the titlebar)
  // Bottom-left: solid accent red
  rect(1, 9, 17, 25, 0xe9, 0x45, 0x60);
  // Top-right: dark fill + accent border
  rect(10, 1, 27, 18, 0x0f, 0x34, 0x60);
  border(10, 1, 27, 18, 0xe9, 0x45, 0x60);

  _trayIcon = nativeImage.createFromBuffer(buf, { width: S, height: S });
  return _trayIcon;
}

// ── Tray ──────────────────────────────────────────────────────────────────────
function createTray() {
  const icon = buildTrayIcon();

  tray = new Tray(icon);
  tray.setToolTip('myHards');
  tray.setContextMenu(Menu.buildFromTemplate([
    {
      label: 'Abrir myHards',
      click: () => { mainWindow.show(); mainWindow.focus(); },
    },
    { type: 'separator' },
    {
      label: 'Salir',
      click: () => {
        app.isQuitting = true;
        killProc(serverProc);
        killProc(clientProc);
        app.quit();
      },
    },
  ]));
  tray.on('double-click', () => { mainWindow.show(); mainWindow.focus(); });
}

// ── IPC handlers ──────────────────────────────────────────────────────────────
ipcMain.handle('get-config',   ()         => loadConfig());
ipcMain.handle('get-local-ip', ()         => getLocalIp());
ipcMain.handle('save-config',  (_, cfg)   => { saveConfig(cfg); return true; });

// ── Virtual camera driver IPC ─────────────────────────────────────────────────
ipcMain.handle('check-camera-driver', async () => {
  if (process.platform !== 'win32') return { installed: false, supported: false };
  const installed   = await isCameraDriverInstalled();
  const dllPath     = findObsDll();
  return { installed, supported: true, driverExists: !!dllPath, dllPath };
});

ipcMain.handle('browse-driver-dll', async () => {
  const result = await dialog.showOpenDialog(mainWindow, {
    title: 'Seleccionar obs-virtualcam-module64.dll',
    defaultPath: 'C:\\Program Files\\obs-studio',
    filters: [{ name: 'DLL de OBS VirtualCam', extensions: ['dll'] }],
    properties: ['openFile'],
  });
  if (result.canceled || !result.filePaths.length) return null;
  return result.filePaths[0];
});

ipcMain.handle('install-camera-driver', async (_, customPath) => {
  if (process.platform !== 'win32') return { success: false, error: 'Solo disponible en Windows' };
  try {
    const success = await installCameraDriver(customPath || null);
    if (!success) return { success: false, error: 'No se pudo registrar el driver. ¿Se canceló el prompt de UAC?' };
    return { success: true };
  } catch (e) {
    return { success: false, error: e.message };
  }
});

ipcMain.handle('start-server', (_, cfg) => {
  if (serverProc && serverProc.exitCode === null) return false;
  saveConfig(cfg);
  serverProc = spawnPythonProcess('server.py', [], 'SERVER', 'server-stopped');
  serverProc.once('exit', () => {
    serverProc = null;
  });
  return true;
});

ipcMain.handle('stop-server', () => {
  killProc(serverProc);
  return true;
});

ipcMain.handle('start-client', (_, cfg) => {
  if (clientProc && clientProc.exitCode === null) return false;
  saveConfig(cfg);
  clientProc = spawnPythonProcess('client.py', [cfg.last_server_ip], 'CLIENT', 'client-stopped');
  clientProc.once('exit', () => {
    clientProc = null;
  });
  return true;
});

ipcMain.handle('stop-client', () => {
  killProc(clientProc);
  return true;
});

// ── Custom menu (replaces native Electron menu) ─────────────────────────────
function buildAppMenu() {
  const template = [
    {
      label: 'Archivo',
      submenu: [
        {
          label: 'Guardar configuración',
          accelerator: 'CmdOrCtrl+S',
          click: () => mainWindow?.webContents.send('menu-save-config'),
        },
        { type: 'separator' },
        {
          label: 'Minimizar al tray',
          accelerator: 'CmdOrCtrl+W',
          click: () => { mainWindow?.hide(); if (!tray) createTray(); },
        },
        { type: 'separator' },
        {
          label: 'Salir',
          accelerator: 'CmdOrCtrl+Q',
          click: () => {
            app.isQuitting = true;
            killProc(serverProc);
            killProc(clientProc);
            app.quit();
          },
        },
      ],
    },
    {
      label: 'Ver',
      submenu: [
        {
          label: 'Pestaña Conexión',
          accelerator: 'CmdOrCtrl+1',
          click: () => mainWindow?.webContents.send('menu-tab', 'connection'),
        },
        {
          label: 'Pestaña Ajustes',
          accelerator: 'CmdOrCtrl+2',
          click: () => mainWindow?.webContents.send('menu-tab', 'settings'),
        },
        { type: 'separator' },
        {
          label: 'Recargar',
          accelerator: 'CmdOrCtrl+R',
          click: () => mainWindow?.reload(),
        },
        {
          label: 'Herramientas de desarrollador',
          accelerator: 'F12',
          click: () => mainWindow?.webContents.toggleDevTools(),
        },
      ],
    },
    {
      label: 'Ayuda',
      submenu: [
        {
          label: 'Acerca de myHards',
          click: () => {
            dialog.showMessageBox(mainWindow, {
              type: 'info',
              title: 'myHards',
              message: 'myHards',
              detail: 'Compartición de teclado y ratón entre PCs.\nVersión 0.1.0',
              buttons: ['Cerrar'],
            });
          },
        },
      ],
    },
  ];
  Menu.setApplicationMenu(Menu.buildFromTemplate(template));
}

// ── Auto-register OBS VirtualCam driver on startup ───────────────────────────
async function ensureCameraDriverRegistered() {
  if (process.platform !== 'win32') return;
  try {
    const already = await isCameraDriverInstalled();
    if (already) return;  // already registered — nothing to do

    const dllPath = findObsDll();
    if (!dllPath) return;  // DLL not found — skip silently

    // Register silently via PowerShell RunAs (triggers one-time UAC prompt)
    const escaped = dllPath.replace(/\\/g, '\\\\').replace(/'/g, "''");
    const psCmd   = `Start-Process regsvr32 -ArgumentList @('/s','${escaped}') -Verb RunAs -Wait`;
    exec(`powershell -WindowStyle Hidden -Command "${psCmd}"`, { windowsHide: true });
  } catch (_) {}
}

// ── App lifecycle ─────────────────────────────────────────────────────────────
app.whenReady().then(() => {
  ensureCameraDriverRegistered();   // silent auto-install on first run
  buildAppMenu();
  createWindow();
  app.on('activate', () => {
    if (mainWindow) { mainWindow.show(); mainWindow.focus(); }
  });
});

// Keep the app alive in tray after all windows close
app.on('window-all-closed', () => { /* intentional no-op */ });

app.on('before-quit', () => {
  app.isQuitting = true;
  killProc(serverProc);
  killProc(clientProc);
});
