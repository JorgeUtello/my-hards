'use strict';

/**
 * Preload script — exposes a minimal, typed API to the renderer.
 * contextIsolation=true keeps Node.js APIs out of the renderer.
 */

const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('api', {
  // Window controls (custom titlebar)
  winMinimize:       ()  => ipcRenderer.invoke('win-minimize'),
  winMaximizeToggle: ()  => ipcRenderer.invoke('win-maximize-toggle'),
  winClose:          ()  => ipcRenderer.invoke('win-close'),
  winIsMaximized:    ()  => ipcRenderer.invoke('win-is-maximized'),
  onWinMaximized:    (cb) => { ipcRenderer.on('win-maximized', (_, v) => cb(v)); },

  // Config
  getConfig:  ()      => ipcRenderer.invoke('get-config'),
  getLocalIp: ()      => ipcRenderer.invoke('get-local-ip'),
  saveConfig: (cfg)   => ipcRenderer.invoke('save-config', cfg),

  // Server
  startServer: (cfg)  => ipcRenderer.invoke('start-server', cfg),
  stopServer:  ()     => ipcRenderer.invoke('stop-server'),

  // Client
  startClient: (cfg)  => ipcRenderer.invoke('start-client', cfg),
  stopClient:  ()     => ipcRenderer.invoke('stop-client'),

  // Virtual camera driver
  checkCameraDriver:   () => ipcRenderer.invoke('check-camera-driver'),
  installCameraDriver: () => ipcRenderer.invoke('install-camera-driver'),

  // Events from main → renderer
  onLog:           (cb) => { ipcRenderer.on('log',            (_, m) => cb(m)); },
  onServerStopped: (cb) => { ipcRenderer.on('server-stopped', ()    => cb()); },
  onClientStopped: (cb) => { ipcRenderer.on('client-stopped', ()    => cb()); },
  // Menu shortcuts
  onMenuSaveConfig:(cb) => { ipcRenderer.on('menu-save-config', ()  => cb()); },
  onMenuTab:       (cb) => { ipcRenderer.on('menu-tab', (_, t)      => cb(t)); },
});
