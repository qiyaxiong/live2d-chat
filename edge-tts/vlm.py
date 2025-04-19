import cv2
import base64
import numpy as np
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
import requests
import json
from typing import Optional
import os
from datetime import datetime
from openai import OpenAI

app = FastAPI()

# 允许跨域请求
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 配置
API_KEY = "sk-411c9eba3fa240169ce04eae5ab499ed"  # 替换为你的API密钥
client = OpenAI(
    api_key=API_KEY,
    base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
)

# 缓存目录
CACHE_DIR = "cache"
if not os.path.exists(CACHE_DIR):
    os.makedirs(CACHE_DIR)

async def process_image_with_qwen(image_base64: str, prompt: str) -> dict:
    """调用通义千问API处理图像"""
    try:
        # 确保image_base64不包含前缀
        if ',' in image_base64:
            image_base64 = image_base64.split(',')[1]
        
        completion = client.chat.completions.create(
            model="qwen-vl-plus",
            messages=[{
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image_base64}"}}
                ]
            }]
        )
        
        # 获取响应文本
        response_text = completion.choices[0].message.content
        return {
            "output": {
                "text": response_text
            }
        }
    except Exception as e:
        print(f"API调用错误: {str(e)}")
        raise

def save_debug_image(image_data: np.ndarray, prefix: str = "debug"):
    """保存调试图像"""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{CACHE_DIR}/{prefix}_{timestamp}.jpg"
    cv2.imwrite(filename, image_data)
    return filename

@app.post("/api/vision/camera")
async def process_camera_image(request: Request):
    """处理摄像头图像"""
    try:
        data = await request.json()
        image_data = data['image']
        prompt = data.get('prompt', "请详细描述这张图片中的内容，包括可见的人物、物体、场景等细节。")
        
        # 解码base64图像
        image_bytes = base64.b64decode(image_data.split(',')[1])
        nparr = np.frombuffer(image_bytes, np.uint8)
        image = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        
        # 保存调试图像
        debug_file = save_debug_image(image, "camera")
        print(f"调试图像已保存: {debug_file}")
        
        # 调用通义千问API
        response = await process_image_with_qwen(image_data, prompt)
        
        # 处理API响应
        if 'output' in response:
            return {
                "status": "success",
                "response": response['output']['text'],
                "source": "qwen"
            }
        else:
            raise Exception("API返回格式错误")
            
    except Exception as e:
        print(f"处理错误: {str(e)}")
        return {
            "status": "error",
            "error": str(e)
        }

@app.post("/api/vision/upload")
async def process_uploaded_image(request: Request):
    """处理上传的图像"""
    try:
        data = await request.json()
        image_data = data['image']
        prompt = data.get('prompt', "请详细描述这张图片中的内容，包括可见的人物、物体、场景等细节。")
        
        # 解码base64图像
        image_bytes = base64.b64decode(image_data.split(',')[1])
        nparr = np.frombuffer(image_bytes, np.uint8)
        image = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        
        # 保存调试图像
        debug_file = save_debug_image(image, "upload")
        print(f"调试图像已保存: {debug_file}")
        
        # 调用通义千问API
        response = await process_image_with_qwen(image_data, prompt)
        
        if 'output' in response:
            return {
                "status": "success",
                "response": response['output']['text'],
                "source": "qwen"
            }
        else:
            raise Exception("API返回格式错误")
            
    except Exception as e:
        print(f"处理错误: {str(e)}")
        return {
            "status": "error",
            "error": str(e)
        }

@app.get("/health")
async def health_check():
    """健康检查接口"""
    return {"status": "healthy"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=7856)