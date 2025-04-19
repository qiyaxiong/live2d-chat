import websockets
import json
import asyncio
from fastapi import FastAPI, WebSocket
from fastapi.middleware.cors import CORSMiddleware
import sounddevice as sd
import numpy as np
import wave
import audioop

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class VTuberController:
    def __init__(self):
        self.uri = "ws://localhost:8001"
        self.websocket = None
        self.is_connected = False
        self.audio_task = None
        self.stop_audio = False
        
    async def connect(self):
        if self.is_connected:
            return True
            
        try:
            self.websocket = await websockets.connect(self.uri)
            auth_result = await self.authenticate()
            self.is_connected = True
            return True
        except Exception as e:
            print(f"VTuber Studio连接错误: {e}")
            return False
    
    async def monitor_audio(self):
        CHUNK = 1024
        RATE = 44100
        
        def audio_callback(indata, frames, time, status):
            if status:
                print(f"音频状态: {status}")
            if not self.stop_audio:
                # 计算音量级别
                volume = audioop.rms(indata.tobytes(), 2)
                # 将音量映射到0-1之间的值
                normalized_volume = min(1.0, volume / 32767)
                # 异步发送口型控制
                asyncio.create_task(self.control_mouth(normalized_volume))

        try:
            with sd.InputStream(channels=1, 
                              samplerate=RATE,
                              blocksize=CHUNK, 
                              callback=audio_callback):
                while not self.stop_audio:
                    await asyncio.sleep(0.01)
        except Exception as e:
            print(f"音频监控错误: {e}")

    async def start_audio_monitoring(self):
        self.stop_audio = False
        self.audio_task = asyncio.create_task(self.monitor_audio())

    async def stop_audio_monitoring(self):
        self.stop_audio = True
        if self.audio_task:
            await self.audio_task

    async def control_mouth(self, value):
        if not self.is_connected:
            success = await self.connect()
            if not success:
                return False
            
        try:
            message = {
                "apiName": "VTubeStudioPublicAPI",
                "apiVersion": "1.0",
                "requestID": "mouth_control",
                "messageType": "ParameterValueRequest",
                "data": {
                    "parameterValues": [
                        {
                            "id": "MouthOpen",
                            "value": value
                        }
                    ]
                }
            }
            await self.websocket.send(json.dumps(message))
            return True
        except Exception as e:
            print(f"口型控制错误: {e}")
            return False

controller = VTuberController()

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    try:
        # 启动音频监控
        await controller.start_audio_monitoring()
        
        while True:
            data = await websocket.receive_text()
            print(f"收到消息: {data}")
            
    except Exception as e:
        print(f"WebSocket错误: {e}")
    finally:
        # 停止音频监控
        await controller.stop_audio_monitoring()

@app.get("/status")
async def get_status():
    return {"connected": vtuber.is_connected}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8096)