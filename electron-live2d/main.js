const { app, BrowserWindow, ipcMain, Menu, Tray, screen, nativeImage } = require('electron');
const path = require('path');
const aiService = require('./services/ai-service');

// 全局变量
let mainWindow;
let tray = null;
let isQuitting = false;
let isModelDragMode = false; // 是否处于模型拖动模式

function createWindow() {
  const { width, height } = screen.getPrimaryDisplay().workAreaSize;
  
  // 创建浏览器窗口，设置为透明、无边框
  mainWindow = new BrowserWindow({
    width: 400,
    height: 500,
    minWidth: 200,
    minHeight: 300,
    frame: false,         // 无边框
    transparent: true,    // 背景透明
    backgroundColor: '#00000000', // 完全透明背景
    hasShadow: false,     // 无阴影
    titleBarStyle: 'hidden',
    alwaysOnTop: false,   // 默认不置顶
    resizable: true,      // 可调整大小
    skipTaskbar: false,   // 在任务栏显示
    webPreferences: {
      nodeIntegration: false,
      contextIsolation: true,
      preload: path.join(__dirname, 'preload.js'),
      backgroundThrottling: false // 防止背景节流
    }
  });

  // 设置窗口类型为工具窗口，确保在某些平台上更好地支持透明
  if (process.platform === 'win32') {
    mainWindow.setThumbarButtons([]);
  }

  // 加载 Live2D 页面
  mainWindow.loadFile(path.join(__dirname, 'index.html'));

  // 窗口关闭事件处理
  mainWindow.on('closed', () => {
    mainWindow = null;
  });

  // 创建系统托盘
  createTray();
  
  // 添加加载完成事件
  mainWindow.webContents.on('did-finish-load', () => {
    console.log("页面加载完成");
  });
  
  // 重新添加IPC监听器，用于窗口拖动
  ipcMain.on('window-drag', (event, { x, y }) => {
    if (mainWindow && !isModelDragMode) {
      mainWindow.setPosition(x, y);
    }
  });
  
  // 添加拖动区域更新
  ipcMain.handle('set-model-drag', (event, isDragging) => {
    isModelDragMode = isDragging;
    return true;
  });
  
  // 获取窗口位置
  ipcMain.handle('get-window-position', (event) => {
    if (mainWindow) {
      return mainWindow.getPosition();
    }
    return [0, 0];
  });
}

function createTray() {
  // 创建一个空白图标
  const emptyIcon = nativeImage.createEmpty();
  tray = new Tray(emptyIcon);
  
  const contextMenu = Menu.buildFromTemplate([
    { 
      label: '显示/隐藏', 
      click: () => {
        if (mainWindow) {
          if (mainWindow.isVisible()) {
            mainWindow.hide();
          } else {
            mainWindow.show();
          }
        }
      }
    },
    {
      label: '始终置顶',
      type: 'checkbox',
      checked: false,
      click: () => {
        if (mainWindow) {
          const isAlwaysOnTop = mainWindow.isAlwaysOnTop();
          mainWindow.setAlwaysOnTop(!isAlwaysOnTop);
        }
      }
    },
    { type: 'separator' },
    { 
      label: '退出', 
      click: () => {
        isQuitting = true;
        app.quit();
      }
    }
  ]);
  
  tray.setToolTip('Live2D 模型');
  tray.setContextMenu(contextMenu);
  
  tray.on('click', () => {
    if (mainWindow) {
      if (mainWindow.isVisible()) {
        mainWindow.hide();
      } else {
        mainWindow.show();
      }
    }
  });
}

// 应用程序就绪事件
app.whenReady().then(() => {
  // 确保应用在macOS上支持透明窗口
  if (process.platform === 'darwin') {
    app.dock.hide();
  }
  
  createWindow();

  app.on('activate', () => {
    // 在 macOS 上，当点击 dock 图标且没有其他窗口打开时，
    // 通常在应用程序中重新创建一个窗口
    if (BrowserWindow.getAllWindows().length === 0) {
      createWindow();
    }
  });
});

// 当所有窗口关闭时退出应用，macOS 除外
app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') {
    app.quit();
  }
});

app.on('before-quit', () => {
  isQuitting = true;
});

// IPC 处理器
ipcMain.on('app-quit', () => {
  isQuitting = true;
  app.quit();
});

// 添加 AI 消息处理
ipcMain.handle('send-message', async (event, text) => {
  try {
    const response = await aiService.generateResponse(text);
    if (response && response.output && response.output.text) {
      return response.output.text;
    }
    return '抱歉，我现在无法回答。';
  } catch (error) {
    console.error('消息处理失败:', error);
    return '发生错误，请稍后再试。';
  }
});