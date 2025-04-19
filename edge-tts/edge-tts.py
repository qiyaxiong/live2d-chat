import os
import re
import subprocess
import time
from flask import Flask, request, send_from_directory
from flask_cors import CORS
import aiohttp
import asyncio
from pydub import AudioSegment
from langdetect import detect
from flask import jsonify
from langdetect import detect, DetectorFactory
from threading import Lock
from config import config, OutputMode
import websockets
import json

# 初始化语言检测引擎
DetectorFactory.seed = 0
app = Flask(__name__, static_folder='tts')
CORS(app)  # 允许所有跨域请求

# 配置语音映射表
voiceMap = {
    "xiaoxiao": "zh-CN-XiaoxiaoNeural",
    "xiaoyi": "zh-CN-XiaoyiNeural",
    "yunjian": "zh-CN-YunjianNeural",
    "yunxi": "zh-CN-YunxiNeural",
    "yunxia": "zh-CN-YunxiaNeural",
    "yunyang": "zh-CN-YunyangNeural",
    "xiaobei": "zh-CN-liaoning-XiaobeiNeural",
    "xiaoni": "zh-CN-shaanxi-XiaoniNeural",
    "hiugaai": "zh-HK-HiuGaaiNeural",
    "hiumaan": "zh-HK-HiuMaanNeural",
    "wanlung": "zh-HK-WanLungNeural",
    "hsiaochen": "zh-TW-HsiaoChenNeural",
    "hsioayu": "zh-TW-HsiaoYuNeural",
    "yunjhe": "zh-TW-YunJheNeural",
    "nanami": "ja-JP-NanamiNeural",  # 日语女性语音
    "takumi": "ja-JP-TakumiNeural",  # 日语男性语音
}


# ================== 文件计数器 ==================
file_counter = 0
counter_lock = Lock()

def initialize_counter():
    """初始化文件计数器（服务启动时自动执行）"""
    global file_counter
    max_counter = 0
    
    try:
        for filename in os.listdir(app.static_folder):
            # 匹配包含数字的文件名（如 test123.mp3 或 audio456.wav）
            match = re.search(r'(\d+)\.\w+$', filename)
            if match:
                current = int(match.group(1))
                max_counter = max(max_counter, current)
    except FileNotFoundError:
        os.makedirs(app.static_folder, exist_ok=True)
    
    file_counter = max_counter

# 服务启动时初始化计数器
initialize_counter()

# ================== 工具函数 ==================
def remove_html(text):
    """移除HTML标签"""
    return re.sub(r'<[^>]+>', '', text)

def ensure_wav_format(file_path):
    """转换音频为WAV格式"""
    if file_path.endswith(".mp3"):
        wav_path = file_path[:-4] + ".wav"
        AudioSegment.from_mp3(file_path).export(wav_path, format="wav")
        os.remove(file_path)
        return wav_path
    return file_path

# ================== 语音服务接口 ==================
async def convert_with_so_vits_svc(audio_path):
    """调用so-vits-svc进行音色转换"""
    api_url = "http://127.0.0.1:1145/wav2wav"
    params = {
        "audio_path": audio_path,
        "tran": 0,
        "spk": "sparkle-hi3",
        "wav_format": "wav"
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(api_url, data=params, timeout=30) as response:
                if response.status == 200:
                    output_path = audio_path.replace(".wav", "_svc.wav")
                    with open(output_path, "wb") as f:
                        f.write(await response.read())
                    return output_path
                print(f"转换失败: {await response.text()}")
    except Exception as e:
        print(f"音色转换异常: {str(e)}")
    return None

# ================== 核心逻辑 ==================
def createAudio(text, base_name, voiceId):
    """生成音频主逻辑"""
    global file_counter
    
    # 清理输入文本
    clean_text = remove_html(text)[:500]  # 限制输入长度
    
    # 获取语音配置
    voice_config = voiceMap.get(voiceId, voiceMap["xiaoxiao"])
    
    # 生成唯一文件名
    with counter_lock:
        file_counter += 1
        file_name = f"{base_name}{file_counter}.mp3"
    
    file_path = os.path.join(app.static_folder, file_name)
    os.makedirs(os.path.dirname(file_path), exist_ok=True)

    # 生成原始音频
    try:
        subprocess.run([
            'edge-tts',
            '--voice', voice_config,
            '--text', clean_text,
            '--write-media', file_path
        ], check=True, timeout=30)
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
        print(f"语音合成失败: {str(e)}")
        return None

    # 格式转换
    wav_path = ensure_wav_format(file_path)
    
    # 音色转换
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        converted_path = loop.run_until_complete(
            convert_with_so_vits_svc(wav_path)
        )
    finally:
        loop.close()

    # 处理转换结果
    if converted_path and os.path.exists(converted_path):
        os.replace(converted_path, wav_path)
        return f"/tts/{os.path.basename(wav_path)}"
    
    return None

# ================== 路由处理 ==================
@app.route('/dealAudio', methods=['GET'])
def handle_audio_request():
    """处理语音请求"""
    text = request.args.get('text', '')
    base_name = request.args.get('base_name', 'audio')
    
    if not text:
        return jsonify({"error": "缺少文本参数"}), 400
    
    # 自动检测语言
    try:
        lang = detect(text)
        voice_id = 'nanami' if lang == 'ja' else 'xiaoxiao'
    except:
        voice_id = 'xiaoxiao'
    
    # 生成音频
    audio_url = createAudio(text, base_name, voice_id)
    
    if not audio_url:
        return jsonify({"error": "音频生成失败"}), 500
    
    return jsonify({
        "audioUrl": f"http://127.0.0.1:2020{audio_url}?v={int(time.time())}",
        "voice": voice_id
    })

@app.route('/tts/<path:filename>')
def serve_audio(filename):
    """提供音频文件访问"""
    return send_from_directory(app.static_folder, filename)

@app.route('/clean', methods=['POST'])
def clean_files():
    """清理生成的文件（测试用）"""
    for filename in os.listdir(app.static_folder):
        file_path = os.path.join(app.static_folder, filename)
        try:
            if os.path.isfile(file_path):
                os.remove(file_path)
        except Exception as e:
            print(f"删除 {filename} 失败: {str(e)}")
    initialize_counter()  # 重置计数器
    return jsonify({"status": "清理完成"})

# ================== 服务启动 ==================
if __name__ == "__main__":
    app.run(port=2020, host="0.0.0.0", debug=True)


async def process_audio(text, output_path):
    if config["output_mode"] == OutputMode.VTUBER:
        try:
            async with websockets.connect('ws://localhost:8001') as websocket:
                # 发送认证请求
                auth_message = {
                    "apiName": "VTubeStudioPublicAPI",
                    "apiVersion": "1.0",
                    "requestID": "authentication",
                    "messageType": "AuthenticationTokenRequest",
                    "data": {
                        "pluginName": "AI Chat TTS",
                        "pluginDeveloper": "AI Assistant",
                        "pluginIcon": ""
                    }
                }
                await websocket.send(json.dumps(auth_message))
                response = await websocket.recv()
                
                # 处理音频数据并发送到VTuber Studio
                # ... 音频处理代码 ...
        except Exception as e:
            print(f"VTuber Studio连接错误: {e}")
            
    return output_path