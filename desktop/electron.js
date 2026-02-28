const { app, BrowserWindow, ipcMain, Menu, shell } = require('electron');
const path = require('path');
const Store = require('electron-store');

require('dotenv').config({ path: path.join(__dirname, '.env') });

const store = new Store();
const BACKEND_URL = process.env.BACKEND_URL || 'http://localhost:8000';

let clientWindow = null;
let adminWindow = null;
let selectorWindow = null;

function createSelectorWindow() {
  selectorWindow = new BrowserWindow({
    width: 560,
    height: 400,
    resizable: false,
    center: true,
    title: 'RealEstate Bot - Select Portal',
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      nodeIntegration: false,
      contextIsolation: true,
    },
    autoHideMenuBar: true,
    backgroundColor: '#0f0f1a',
  });

  selectorWindow.loadFile(path.join(__dirname, 'src', 'selector.html'));
  selectorWindow.on('closed', () => { selectorWindow = null; });
}

function createClientWindow() {
  if (clientWindow) { clientWindow.focus(); return; }

  clientWindow = new BrowserWindow({
    width: 1280,
    height: 800,
    minWidth: 1280,
    minHeight: 800,
    title: 'RealEstate Bot - Client Portal',
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      nodeIntegration: false,
      contextIsolation: true,
    },
    backgroundColor: '#0f0f1a',
  });

  clientWindow.loadFile(path.join(__dirname, 'src', 'client', 'login.html'));
  clientWindow.on('closed', () => { clientWindow = null; });
  buildMenu(clientWindow, 'client');
}

function createAdminWindow() {
  if (adminWindow) { adminWindow.focus(); return; }

  adminWindow = new BrowserWindow({
    width: 1280,
    height: 800,
    minWidth: 1280,
    minHeight: 800,
    title: 'RealEstate Bot - Admin Portal',
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      nodeIntegration: false,
      contextIsolation: true,
    },
    backgroundColor: '#0f0f1a',
  });

  adminWindow.loadFile(path.join(__dirname, 'src', 'admin', 'login.html'));
  adminWindow.on('closed', () => { adminWindow = null; });
  buildMenu(adminWindow, 'admin');
}

function buildMenu(win, portalType) {
  const isClient = portalType === 'client';
  const viewItems = isClient
    ? [
        { label: 'Dashboard', click: () => win.loadFile(path.join(__dirname, 'src', 'client', 'dashboard.html')) },
        { label: 'Leads', click: () => win.loadFile(path.join(__dirname, 'src', 'client', 'leads.html')) },
        { label: 'Listings', click: () => win.loadFile(path.join(__dirname, 'src', 'client', 'listings.html')) },
        { label: 'Performance', click: () => win.loadFile(path.join(__dirname, 'src', 'client', 'performance.html')) },
        { label: 'Settings', click: () => win.loadFile(path.join(__dirname, 'src', 'client', 'settings.html')) },
      ]
    : [
        { label: 'Dashboard', click: () => win.loadFile(path.join(__dirname, 'src', 'admin', 'dashboard.html')) },
        { label: 'Clients', click: () => win.loadFile(path.join(__dirname, 'src', 'admin', 'clients.html')) },
        { label: 'Invoices', click: () => win.loadFile(path.join(__dirname, 'src', 'admin', 'invoices.html')) },
      ];

  const template = [
    {
      label: 'File',
      submenu: [
        {
          label: 'Switch Portal',
          click: () => {
            createSelectorWindow();
          },
        },
        { type: 'separator' },
        { label: 'Quit', accelerator: 'CmdOrCtrl+Q', click: () => app.quit() },
      ],
    },
    {
      label: 'View',
      submenu: [
        ...viewItems,
        { type: 'separator' },
        { label: 'Reload', accelerator: 'CmdOrCtrl+R', role: 'reload' },
        { label: 'Toggle DevTools', accelerator: 'F12', role: 'toggleDevTools' },
      ],
    },
    {
      label: 'Help',
      submenu: [
        {
          label: 'About RealEstate Bot',
          click: () => {
            const { dialog } = require('electron');
            dialog.showMessageBox(win, {
              type: 'info',
              title: 'About RealEstate Bot',
              message: 'RealEstate Bot v1.0.0',
              detail: 'Real Estate Agent Automation Platform\n\nBackend: ' + BACKEND_URL,
            });
          },
        },
        {
          label: 'Open Backend URL',
          click: () => shell.openExternal(BACKEND_URL),
        },
      ],
    },
  ];

  win.setMenu(Menu.buildFromTemplate(template));
}

// ── IPC Handlers ──────────────────────────────────────────────────────────────

ipcMain.handle('api-request', async (_event, method, apiPath, body, token) => {
  try {
    const url = `${BACKEND_URL}${apiPath}`;
    const options = {
      method: method.toUpperCase(),
      headers: {
        'Content-Type': 'application/json',
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
    };
    if (body && method.toUpperCase() !== 'GET') {
      options.body = JSON.stringify(body);
    }

    const res = await fetch(url, options);
    const text = await res.text();
    let data;
    try { data = JSON.parse(text); } catch { data = text; }

    return { ok: res.ok, status: res.status, data };
  } catch (err) {
    return { ok: false, status: 0, error: err.message };
  }
});

ipcMain.handle('store-get', (_event, key) => store.get(key));
ipcMain.handle('store-set', (_event, key, value) => { store.set(key, value); });
ipcMain.handle('store-delete', (_event, key) => { store.delete(key); });

ipcMain.handle('open-client-portal', () => {
  if (selectorWindow) { selectorWindow.close(); }
  createClientWindow();
});

ipcMain.handle('open-admin-portal', () => {
  if (selectorWindow) { selectorWindow.close(); }
  createAdminWindow();
});

// ── App lifecycle ─────────────────────────────────────────────────────────────

app.whenReady().then(() => {
  createSelectorWindow();

  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) createSelectorWindow();
  });
});

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') app.quit();
});
