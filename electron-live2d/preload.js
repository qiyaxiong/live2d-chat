const { contextBridge, ipcRenderer } = require('electron');

// Expose IPC functions to the renderer process
contextBridge.exposeInMainWorld('electronAPI', {
  // Quit the application
  quit: () => ipcRenderer.send('app-quit'),
  
  // 窗口拖动
  windowDrag: (x, y) => ipcRenderer.send('window-drag', { x, y }),
  
  // 设置模型拖动模式
  setModelDrag: async (isDragging) => {
    return await ipcRenderer.invoke('set-model-drag', isDragging);
  },
  
  // 获取窗口位置
  getWindowPosition: async () => {
    return await ipcRenderer.invoke('get-window-position');
  }
}); 