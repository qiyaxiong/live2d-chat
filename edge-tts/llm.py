#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
优化版大语言模型服务 - 按优先级查询不同知识源
优先级顺序：1.记忆服务 -> 2.AnythingLLM知识库 -> 3.大模型API
"""

import os
import json
import time
import logging
import requests as rq
from datetime import datetime
from typing import List, Dict, Any, Optional, Union, Tuple
from flask import Flask, request, jsonify
from flask_cors import CORS

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

app = Flask(__name__)
CORS(app)  # 启用跨域支持

# API配置
API_CONFIG = {
    "openai": {
        "url": "https://api.bianxie.ai/v1/chat/completions",
        "model": "gpt-3.5-turbo",
        "api_key": "Bearer sk-ShxdOGzMSwzR8H2wfTBfbntZYYkz62IVBu1qDp2rLURSHnTG"
    },
    "deepseek": {
        "url": "https://api.deepseek.com/v1/chat/completions",
        "model": "deepseek-reasoner",
        "api_key": "Bearer sk-079e918cde4345c2b069969f3b60fc65"
    }
}

# 服务配置
SERVICE_CONFIG = {
    # 记忆服务 (ChromaDB)
    "memory": {
        "enabled": True,
        "url": "http://localhost:5090",
        "priority": 1,  # 最高优先级
        "similarity_threshold": 0.82,  # 相似度阈值，高于此值才考虑有效
        "recency_boost": True  # 最近的记忆有加成
    },
    # AnythingLLM知识库
    "knowledge_base": {
        "enabled": True,
        "url": "http://localhost:3001",
        "workspace": "test",  # 你的workspace名称
        "api_key": "KD1DB6E-9WYMEDG-N27JDK1-YB18BNN",  # 你的API密钥
        "priority": 2,
        "confidence_threshold": 0.60,
        "max_retries": 3,  # 添加重试次数
        "verify_ssl": False  # 如果需要，可以禁用SSL验证
    },
    # Letta长期记忆
    "letta": {
        "enabled": True,  # 默认禁用，可按需启用
        "db_path": "data/db/letta.db",
        "username": "小柒",  # 替换为默认用户名
        "prompt": "你是一个智能助手，拥有长期记忆能力",  # 替换为实际的persona prompt
        "priority": 3  # 第三优先级
    }
}

# 对话历史缓存
chat_history = []

# Letta客户端导入（如果启用）
if SERVICE_CONFIG["letta"]["enabled"]:
    try:
        from letta import create_client, ChatMemory, LLMConfig, EmbeddingConfig
        letta_available = True
    except ImportError:
        logger.warning("Letta模块导入失败，将禁用Letta长期记忆功能")
        SERVICE_CONFIG["letta"]["enabled"] = False
        letta_available = False
else:
    letta_available = False

def current_time():
    """获取当前格式化时间"""
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def query_memory_service(query: str, limit: int = 3) -> Tuple[bool, str, List[Dict]]:
    """
    查询记忆服务获取相关记忆
    
    Args:
        query: 用户查询
        limit: 返回结果数量限制
        
    Returns:
        (是否找到有效记忆, 记忆响应, 原始记忆列表)
    """
    config = SERVICE_CONFIG["memory"]
    if not config["enabled"]:
        return False, "", []
        
    try:
        response = rq.post(
            f"{config['url']}/retrieve_memories",
            json={"query": query, "limit": limit},
            timeout=5
        )
        
        if response.status_code != 200:
            logger.error(f"记忆服务返回错误: {response.status_code}")
            return False, "", []
            
        result = response.json()
        memories = result.get("memories", [])
        
        if not memories:
            return False, "", []
            
        # 检查最高相似度是否超过阈值
        best_memory = max(memories, key=lambda m: m.get("similarity_score", 0))
        if best_memory.get("similarity_score", 0) < config["similarity_threshold"]:
            logger.info(f"最佳记忆相似度 {best_memory.get('similarity_score', 0)} 低于阈值 {config['similarity_threshold']}")
            return False, "", memories
            
        # 从最佳记忆中提取助手回复
        memory_text = best_memory.get("text", "")
        assistant_response = ""
        
        if "Assistant:" in memory_text:
            assistant_response = memory_text.split("Assistant:", 1)[1].strip()
        
        # 添加置信度说明
        confidence = int(best_memory.get("similarity_score", 0) * 100)
        if assistant_response:
            logger.info(f"从记忆中找到高度相关回复，相似度: {confidence}%")
            return True, assistant_response, memories
        else:
            return False, "", memories
            
    except Exception as e:
        logger.error(f"查询记忆服务出错: {str(e)}")
        return False, "", []

def query_knowledge_base(query: str) -> Tuple[bool, str]:
    """查询知识库"""
    config = SERVICE_CONFIG["knowledge_base"]
    if not config["enabled"]:
        return False, ""
        
    try:
        url = f"{config['url']}/api/v1/workspace/{config['workspace']}/chat"
        headers = {
            "Authorization": f"Bearer {config['api_key']}", 
            "Content-Type": "application/json"
        }
        data = {"message": query}
        
        # 设置无限超时
        response = rq.post(
            url, 
            json=data, 
            headers=headers,
            timeout=None,  # None 表示无限等待
            verify=config.get("verify_ssl", True)
        )
        
        if response.status_code == 200:
            result = response.json()
            return True, result.get("textResponse", "")
        else:
            logger.error(f"知识库API返回错误: {response.status_code}")
            return False, ""
            
    except Exception as e:
        logger.error(f"查询知识库出错: {str(e)}")
        return False, ""

def query_letta_memory(query: str) -> Tuple[bool, str]:
    """
    查询Letta长期记忆
    
    Args:
        query: 用户查询
        
    Returns:
        (是否找到有效回复, Letta回复)
    """
    config = SERVICE_CONFIG["letta"]
    if not config["enabled"] or not letta_available:
        return False, ""
        
    try:
        from letta import create_client, ChatMemory, LLMConfig, EmbeddingConfig
        
        config = SERVICE_CONFIG["letta"]
        username = config["username"]
        prompt = config["prompt"]
        
        client = create_client()
        
        # 读取或创建agent状态
        try:
            with open(config["db_path"], 'r', encoding='utf-8') as f:
                agent_state_id = f.read().strip()
                
            # 检查ID是否有效
            if len(agent_state_id) < 10:
                raise ValueError("无效的agent ID")
                
        except (FileNotFoundError, ValueError):
            # 创建目录（如果不存在）
            os.makedirs(os.path.dirname(config["db_path"]), exist_ok=True)
            
            # 创建新的agent
            agent_state = client.create_agent(
                memory=ChatMemory(persona=prompt, human=f"Name: {username}"),
                llm_config=LLMConfig.default_config(model_name="letta"),
                embedding_config=EmbeddingConfig.default_config(model_name="text-embedding-ada-002")
            )
            
            with open(config["db_path"], 'w', encoding='utf-8') as f:
                f.write(agent_state.id)
                
            agent_state_id = agent_state.id
        
        # 发送消息
        response = client.send_message(
            agent_id=agent_state_id,
            role="user", 
            message=f"[{current_time()}]{query}"
        )
        
        # 处理响应
        response_text = None
        for message in response.messages:
            if message.message_type == 'tool_call_message':
                function_arguments = message.tool_call.arguments
                if function_arguments:
                    arguments_dict = json.loads(function_arguments)
                    response_text = arguments_dict.get("message")
                    break
        
        # 如果未找到工具调用消息，尝试获取最后一条助手消息
        if not response_text:
            for message in reversed(response.messages):
                if message.role == "assistant":
                    response_text = message.content
                    break
        
        if response_text:
            return True, response_text
        else:
            return False, "Letta无法生成有效回复"
        
    except Exception as e:
        logger.error(f"查询Letta长期记忆出错: {str(e)}")
        return False, "Letta长期记忆服务暂时不可用"

def call_ai_api(provider: str, message: str, 
                temperature: float = 0.7, max_tokens: int = 500) -> str:
    """
    调用AI API获取回复
    
    Args:
        provider: API提供商 ('openai' 或 'deepseek')
        message: 用户消息
        temperature: 采样温度
        max_tokens: 最大生成token数
        
    Returns:
        AI生成的回复
    """
    config = API_CONFIG.get(provider)
    if not config:
        raise ValueError(f"无效的API提供商: {provider}")
    
    try:
        # 准备请求数据
        payload = {
            "model": config["model"],
            "messages": [
                *chat_history[-6:],
                {"role": "user", "content": message}
            ],
            "temperature": temperature,
            "max_tokens": max_tokens
        }
        
        # 设置请求头
        headers = {
            "Authorization": config["api_key"],
            "Content-Type": "application/json"
        }
        
        # 发送请求
        response = rq.post(
            config["url"],
            json=payload,
            headers=headers,
            timeout=10.0
        )
        
        # 检查响应状态
        response.raise_for_status()
        data = response.json()
        
        # 提取回复内容
        content = data["choices"][0]["message"]["content"]
        return content
        
    except rq.RequestException as e:
        logger.error(f"{provider} API错误: {str(e)}")
        raise

def merge_responses(responses: List[str]) -> str:
    """
    融合多个模型的回复
    
    Args:
        responses: 多个模型的回复列表
        
    Returns:
        融合后的回复
    """
    try:
        if len(responses) < 2:
            return responses[0] if responses else ""
        
        # 构建融合提示
        summary_prompt = f"""请综合以下回答生成最佳回复：
        【回复1】{responses[0]}
        【回复2】{responses[1]}
        要求：
        1. 保留所有重要信息
        2. 消除重复内容
        3. 使用自然的口语化中文
        4. 长度控制在100-150字"""
        
        # 调用OpenAI进行融合
        merged = call_ai_api('openai', summary_prompt)
        return merged.replace("\n", "<br>")
        
    except Exception as e:
        logger.error(f"回复融合失败: {str(e)}")
        return responses[0]

def update_chat_history(user_message: str, ai_message: str) -> None:
    """
    更新对话历史
    
    Args:
        user_message: 用户消息
        ai_message: AI回复
    """
    global chat_history
    
    chat_history.append(
        {"role": "user", "content": user_message}
    )
    chat_history.append(
        {"role": "assistant", "content": ai_message}
    )
    
    # 保持历史记录不超过10轮对话
    if len(chat_history) > 20:
        chat_history = chat_history[-20:]

def save_to_memory_service(user_message: str, assistant_response: str) -> bool:
    """
    将对话保存到记忆服务
    
    Args:
        user_message: 用户消息
        assistant_response: 助手回复
        
    Returns:
        保存是否成功
    """
    config = SERVICE_CONFIG["memory"]
    if not config["enabled"]:
        return False
        
    try:
        response = rq.post(
            f"{config['url']}/save_memory",
            json={
                "user_message": user_message,
                "assistant_response": assistant_response,
                "timestamp": datetime.now().isoformat()
            },
            timeout=5
        )
        
        if response.status_code == 200:
            return True
        else:
            logger.error(f"保存到记忆服务失败: {response.status_code}")
            return False
            
    except Exception as e:
        logger.error(f"保存到记忆服务出错: {str(e)}")
        return False

def process_user_message(message: str, is_voice: bool = False) -> Dict[str, Any]:
    """
    按照优先级顺序处理用户消息
    优先级：记忆服务 > 知识库 > 大模型API
    
    Args:
        message: 用户消息内容
        is_voice: 是否为语音消息
        
    Returns:
        处理结果
    """
    try:
        # 初始化返回结果
        result = {
            "status": "error",
            "is_voice": is_voice,
            "message": message,
            "source": None,
            "response": None,
            "sources": {
                "memory": False,
                "knowledge_base": False,
                "letta": False,
                "openai": False,
                "deepseek": False
            },
            "raw_responses": {}
        }
        
        # 第1步：查询记忆服务
        memory_found, memory_response, memories = query_memory_service(message)
        result["raw_responses"]["memories"] = memories
        
        # 如果记忆服务有高置信度回复，直接返回
        if memory_found and memory_response:
            logger.info("使用记忆服务的回复")
            result["status"] = "success"
            result["source"] = "memory"
            result["response"] = memory_response
            result["sources"]["memory"] = True
            
            # 记得更新对话历史
            update_chat_history(message, memory_response)
            return result
        
        # 第2步：查询知识库
        kb_found, kb_response = query_knowledge_base(message)
        result["raw_responses"]["knowledge_base"] = kb_response
        
        # 如果知识库有高置信度回复，直接返回
        if kb_found and kb_response:
            logger.info("使用知识库的回复")
            result["status"] = "success"
            result["source"] = "knowledge_base"
            result["response"] = kb_response
            result["sources"]["knowledge_base"] = True
            
            # 保存到记忆服务和对话历史
            save_to_memory_service(message, kb_response)
            update_chat_history(message, kb_response)
            return result
        
        # 第3步：查询Letta长期记忆（如果启用）
# 第3步：查询Letta长期记忆（如果启用）
        letta_found = False
        letta_response = ""
        if SERVICE_CONFIG["letta"]["enabled"]:
            letta_found, letta_response = query_letta_memory(message)
            result["raw_responses"]["letta"] = letta_response
            
            # 如果Letta有有效回复，直接返回
            if letta_found and letta_response:
                logger.info("使用Letta长期记忆的回复")
                result["status"] = "success"
                result["source"] = "letta"
                result["response"] = letta_response
                result["sources"]["letta"] = True
                
                # 保存到记忆服务和对话历史
                save_to_memory_service(message, letta_response)
                update_chat_history(message, letta_response)
                return result
        
        # 第4步：调用大模型API
        # 先尝试OpenAI
        openai_response = None
        try:
            openai_response = call_ai_api('openai', message)
            result["raw_responses"]["openai"] = openai_response
            result["sources"]["openai"] = True
        except Exception as e:
            logger.error(f"OpenAI响应失败: {str(e)}")
        
        # 再尝试DeepSeek
        deepseek_response = None
        try:
            deepseek_response = call_ai_api('deepseek', message)
            result["raw_responses"]["deepseek"] = deepseek_response
            result["sources"]["deepseek"] = True
        except Exception as e:
            logger.error(f"DeepSeek响应失败: {str(e)}")
        
        # 处理大模型响应
        final_response = None
        
        if openai_response and deepseek_response:
            # 融合两个大模型的回复
            final_response = merge_responses([openai_response, deepseek_response])
            result["source"] = "merged_llm"
        elif openai_response:
            final_response = openai_response
            result["source"] = "openai"
        elif deepseek_response:
            final_response = deepseek_response
            result["source"] = "deepseek"
        elif kb_response:
            # 如果知识库有低置信度回复，也可以使用
            final_response = kb_response
            result["source"] = "knowledge_base_low_confidence"
            result["sources"]["knowledge_base"] = True
        elif letta_response:
            # 如果Letta有低置信度回复，也可以使用
            final_response = letta_response
            result["source"] = "letta_low_confidence"
            result["sources"]["letta"] = True
        else:
            # 所有渠道都失败，返回错误消息
            final_response = "抱歉，我现在无法处理您的请求。请稍后再试。"
            result["source"] = "fallback"
        
        if final_response:
            result["status"] = "success"
            result["response"] = final_response
            
            # 保存到记忆服务和对话历史
            save_to_memory_service(message, final_response)
            update_chat_history(message, final_response)
        
        return result
            
    except Exception as e:
        logger.error(f"消息处理失败: {str(e)}")
        return {
            "status": "error",
            "error": str(e),
            "message": message,
            "is_voice": is_voice
        }

@app.route('/api/chat', methods=['POST'])
def handle_chat():
    """处理聊天请求API端点"""
    try:
        data = request.json
        message = data.get('message', '')
        is_voice = data.get('is_voice', False)
        
        if not message:
            return jsonify({
                "status": "error",
                "error": "消息不能为空"
            }), 400
        
        result = process_user_message(message, is_voice)
        return jsonify(result)
        
    except Exception as e:
        logger.error(f"处理聊天请求失败: {str(e)}")
        return jsonify({
            "status": "error",
            "error": str(e)
        }), 500

@app.route('/api/merge', methods=['POST'])
def handle_merge():
    """响应融合API端点"""
    try:
        data = request.json
        responses = data.get('responses', [])
        
        if len(responses) < 1:
            return jsonify({
                "status": "error",
                "error": "需要至少一个响应来融合"
            }), 400
        
        merged = merge_responses(responses)
        return jsonify({
            "status": "success",
            "merged": merged
        })
        
    except Exception as e:
        logger.error(f"处理融合请求失败: {str(e)}")
        return jsonify({
            "status": "error",
            "error": str(e)
        }), 500

@app.route('/health', methods=['GET'])
def health_check():
    """健康检查API端点"""
    memory_status = "unknown"
    kb_status = "unknown"
    letta_status = "unknown"
    
    # 检查记忆服务状态
    if SERVICE_CONFIG["memory"]["enabled"]:
        try:
            response = rq.get(f"{SERVICE_CONFIG['memory']['url']}/health", timeout=2)
            memory_status = "healthy" if response.status_code == 200 else "unhealthy"
        except:
            memory_status = "unavailable"
    else:
        memory_status = "disabled"
    
       # 检查知识库状态
    # 检查知识库状态
    if SERVICE_CONFIG["knowledge_base"]["enabled"]:
        try:
            url = f"{SERVICE_CONFIG['knowledge_base']['url']}/api/v1/auth"
            headers = {
                "Authorization": f"Bearer {SERVICE_CONFIG['knowledge_base']['api_key']}",
                "Content-Type": "application/json"
            }
            logger.info(f"尝试连接知识库验证端点: {url}")
            response = rq.get(url, headers=headers, timeout=2, verify=False)
            logger.info(f"知识库验证响应: {response.status_code}")
            
            if response.status_code == 200:
                auth_result = response.json()
                kb_status = "healthy" if auth_result.get("authenticated") else "unhealthy"
            else:
                kb_status = "unhealthy"
                
        except rq.Timeout:
            logger.error("知识库验证超时")
            kb_status = "unavailable" 
        except rq.ConnectionError:
            logger.error("无法连接到知识库服务")
            kb_status = "unavailable"
        except Exception as e:
            logger.error(f"知识库验证失败: {str(e)}")
            kb_status = "unavailable"
    else:
        kb_status = "disabled"
    
    # 检查Letta状态
    if SERVICE_CONFIG["letta"]["enabled"]:
        letta_status = "enabled" if letta_available else "import_failed"
    else:
        letta_status = "disabled"
    
    return jsonify({
        "status": "healthy",
        "timestamp": time.time(),
        "services": {
            "memory": memory_status,
            "knowledge_base": kb_status,
            "letta": letta_status
        },
        "config": {
            "memory_priority": SERVICE_CONFIG["memory"]["priority"],
            "knowledge_base_priority": SERVICE_CONFIG["knowledge_base"]["priority"],
            "letta_priority": SERVICE_CONFIG["letta"]["priority"],
            "llm_providers": list(API_CONFIG.keys())
        }
    })

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description='启动优化版LLM服务')
    parser.add_argument('--port', type=int, default=7000, help='服务端口')
    parser.add_argument('--host', type=str, default='0.0.0.0', help='服务主机')
    parser.add_argument('--enable-letta', action='store_true', help='启用Letta长期记忆')
    
    args = parser.parse_args()
    
    # 应用命令行配置

    if args.enable_letta:
        SERVICE_CONFIG["letta"]["enabled"] = True
        logger.info("Letta长期记忆已启用")
    
    # 启动服务
    logger.info(f"启动优化版LLM服务于 http://{args.host}:{args.port}")
    logger.info(f"服务优先级: 1.记忆服务({'启用' if SERVICE_CONFIG['memory']['enabled'] else '禁用'}) -> " +
                f"2.知识库({'启用' if SERVICE_CONFIG['knowledge_base']['enabled'] else '禁用'}) -> " +
                f"3.Letta({'启用' if SERVICE_CONFIG['letta']['enabled'] else '禁用'}) -> 4.大模型API")
    app.run(host=args.host, port=args.port)