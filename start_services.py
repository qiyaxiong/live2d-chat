#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import multiprocessing
import subprocess
import sys
import os
import logging
from datetime import datetime
import uvicorn
from multiprocessing import Process

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('services.log'),
        logging.StreamHandler()
    ]
)

def get_python_path():
    """获取Python解释器路径"""
    venv_path = os.environ.get('VIRTUAL_ENV')
    if venv_path:
        return os.path.join(venv_path, 'Scripts', 'python.exe')
    return sys.executable

def run_service(command):
    """运行单个服务的函数"""
    try:
        # 设置工作目录
        working_dir = os.path.dirname(os.path.abspath(__file__))
        subprocess.run(
            command,
            shell=True,
            check=True,
            cwd=working_dir,
            env=dict(os.environ, PYTHONPATH=working_dir)
        )
    except subprocess.CalledProcessError as e:
        logging.error(f"服务执行错误: {e}")
        raise
    except Exception as e:
        logging.error(f"未知错误: {e}")
        raise

def start_services():
    """启动所有服务"""
    python_path = get_python_path()
    
    # 定义需要启动的服务
    services = [
        f'"{python_path}" edge-tts/edge-tts.py',       # TTS服务
        f'"{python_path}" edge-tts/memory_service.py',  # 记忆服务
        f'"{python_path}" edge-tts/emotion_service.py', # 表情服务
        f'"{python_path}" edge-tts/llm.py --enable-letta',  # LLM服务
        f'"{python_path}" edge-tts/vlm.py',            # VLM服务
        f'"{python_path}" vtuber_service.py',          # VTuber控制服务
        f'"{python_path}" mode_service.py'             # 模式切换服务
    ]

    processes = []
    try:
        # 启动所有服务
        for service in services:
            process = multiprocessing.Process(
                target=run_service,
                args=(service,)
            )
            process.start()
            processes.append(process)
            logging.info(f"已启动服务: {service}")

        # 等待所有进程
        logging.info("所有服务已启动，按 Ctrl+C 停止服务...")
        for process in processes:
            process.join()

    except KeyboardInterrupt:
        logging.warning("\n正在停止所有服务...")
        for process in processes:
            if process.is_alive():
                process.terminate()
                process.join(timeout=5)
                if process.is_alive():
                    process.kill()
        logging.info("所有服务已停止")
        return False
    except Exception as e:
        logging.error(f"启动服务时发生错误: {e}")
        for process in processes:
            if process.is_alive():
                process.terminate()
                process.join(timeout=5)
                if process.is_alive():
                    process.kill()
        return False
    return True

def run_edge_tts():
    """运行单个服务的函数"""
    try:
        # 设置工作目录
        working_dir = os.path.dirname(os.path.abspath(__file__))
        subprocess.run(
            command,
            shell=True,
            check=True,
            cwd=working_dir,
            env=dict(os.environ, PYTHONPATH=working_dir)
        )
    except subprocess.CalledProcessError as e:
        logging.error(f"服务执行错误: {e}")
        raise
    except Exception as e:
        logging.error(f"未知错误: {e}")
        raise

def run_mode_service():
    uvicorn.run("mode_service:app", host="0.0.0.0", port=8002)

if __name__ == "__main__":
    try:
        if not start_services():
            sys.exit(1)
    except KeyboardInterrupt:
        logging.info("程序已被用户终止")
        sys.exit(0)
    except Exception as e:
        logging.error(f"程序执行出错: {e}")
        sys.exit(1)

    processes = [
        Process(target=run_edge_tts),
        Process(target=run_mode_service),
        # 其他服务 ...
    ]
    
    for p in processes:
        p.start()
    
    for p in processes:
        p.join()