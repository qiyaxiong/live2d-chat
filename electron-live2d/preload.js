const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('electronAPI', {
  quit: () => ipcRenderer.send('app-quit'),
  windowDrag: (x, y) => ipcRenderer.send('window-drag', { x, y }),
  setModelDrag: async (isDragging) => {
    return await ipcRenderer.invoke('set-model-drag', isDragging);
  },
  getWindowPosition: async () => {
    return await ipcRenderer.invoke('get-window-position');
  },
  // 新增 AI 相关功能
  sendMessage: (text) => ipcRenderer.invoke('send-message', text),
  onReceiveMessage: (callback) => ipcRenderer.on('receive-message', callback)
});