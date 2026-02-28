const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('electronAPI', {
  apiRequest: (method, path, body, token) =>
    ipcRenderer.invoke('api-request', method, path, body, token),

  storeGet: (key) => ipcRenderer.invoke('store-get', key),
  storeSet: (key, value) => ipcRenderer.invoke('store-set', key, value),
  storeDelete: (key) => ipcRenderer.invoke('store-delete', key),

  openClientPortal: () => ipcRenderer.invoke('open-client-portal'),
  openAdminPortal: () => ipcRenderer.invoke('open-admin-portal'),

  onNotification: (callback) => {
    ipcRenderer.on('notification', (_event, data) => callback(data));
  },
});
