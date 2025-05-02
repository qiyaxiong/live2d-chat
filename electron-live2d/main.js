const {
  app,
  BrowserWindow,
  ipcMain,
  Menu,
  Tray,
  screen,
  nativeImage
} = require('electron');
const path = require('path');

// 正确导入 aiService 实例
const aiService = require('./services/ai-service'); // 根据你的路径调整

// 全局变量
let mainWindow;
let tray = null;
let isQuitting = false;

// 创建主窗口
async function createWindow() {
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

  if (process.platform === 'win32') {
    mainWindow.setThumbarButtons([]);
  }

  // 加载 Live2D 页面
  mainWindow.loadFile(path.join(__dirname, 'index.html'));

  // 窗口关闭事件处理
  mainWindow.on('closed', () => {
    mainWindow = null;
  });

  createTray();
}

// 创建系统托盘图标和菜单
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
app.whenReady().then(async () => {
  // macOS 上隐藏 Dock 图标
  if (process.platform === 'darwin') {
    app.dock.hide();
  }

  // 初始化 AI 服务
  console.log('⏳ 正在初始化 AI 服务...');
  const initialized = await aiService.initialize();
  if (!initialized) {
    console.error('❌ AI 服务初始化失败，应用将退出');
    app.quit();
    return;
  }

  // 创建窗口
  console.log('🔧 开始创建主窗口...');
  await createWindow();
  console.log('✅ 主窗口已创建');

  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) {
      createWindow();
    }
  });
});

// 所有窗口关闭时退出（macOS 除外）
app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') {
    app.quit();
  }
});

// 退出前清理资源
app.on('before-quit', async () => {
  isQuitting = true;
  if (aiService && aiService.cleanup) {
    await aiService.cleanup();
  }
});

// IPC 处理器：发送消息给AI助手
ipcMain.handle('send-message', async (event, text) => {
  if (!aiService) {
    return { output: { text: 'AI 服务尚未准备好，请稍后再试。' } };
  }

  try {
    const response = await aiService.generateResponse(text);
    if (response && response.output && response.output.text) {
      return response;
    }
    return { output: { text: '抱歉，我现在无法回答。' } };
  } catch (error) {
    console.error('消息处理失败:', error);
    return { output: { text: '发生错误，请稍后再试。' } };
  }
});

// MCP 工具调用
ipcMain.handle('mcp-call-tool', async (event, { service, tool, args }) => {
  if (!aiService) {
    return { success: false, error: 'AI 服务未初始化' };
  }

  try {
    const result = await aiService.callMCPTool(service, tool, args);
    return result;
  } catch (error) {
    console.error(`MCP工具调用失败: ${tool}`, error.message);
    return { success: false, error: error.message };
  }
});

// 设置模型是否允许拖动
ipcMain.handle('set-model-drag', (event, isDragging) => {
  if (mainWindow) {
    mainWindow.setIgnoreMouseEvents(isDragging, { forward: true });
    return true;
  }
  return false;
});

// 获取当前窗口位置
ipcMain.handle('get-window-position', (event) => {
  const window = BrowserWindow.getFocusedWindow();
  if (!window) return null;
  const [x, y] = window.getPosition();
  return { x, y };
});

// 健康检查接口（可选）
ipcMain.handle('check-health', () => {
  return {
    status: 'ok',
    aiServiceInitialized: !!aiService,
    mcpServers: Object.keys(aiService?.mcpServers || {}),
    toolsAvailable: Object.keys(aiService?.toolsCache || {})
  };
});

// 错误处理兜底
process.on('uncaughtException', (error) => {
  console.error('❌ 未捕获的异常:', error);
});

process.on('unhandledRejection', (reason) => {
  console.error('⚠️ 未处理的Promise拒绝:', reason);
});