# -*- coding: utf-8 -*-
import os
import json
import sys
import asyncio
from datetime import datetime
from mcp.server.fastmcp import FastMCP
import httpx
from dotenv import load_dotenv

# 启用调试日志
import logging
logging.basicConfig(level=logging.DEBUG, 
                   format='%(asctime)s - %(levelname)s - %(message)s',
                   stream=sys.stderr)
logger = logging.getLogger(__name__)

load_dotenv()

# 初始化 MCP 服务器
mcp = FastMCP(
    name="news-service",
    version="0.1.0",
    description="提供 Google 新闻搜索功能",
    logging_level='DEBUG',  # 修改为 DEBUG 级别
    tools=None,
)

@mcp.tool()
async def search_google_news(keyword: str) -> str:
    """
    根据关键词搜索 Google 新闻。
    参数:
        keyword (str): 搜索关键词
    返回:
        str: 搜索结果的 JSON 字符串
    """
    logger.debug(f"开始搜索关键词: {keyword}")
    
    api_key = os.getenv("SERPER_API_KEY")
    if not api_key:
        logger.error("未找到 SERPER_API_KEY")
        return json.dumps({
            "success": False,
            "error": "❌ 未配置 SERPER_API_KEY，请在 .env 文件中设置"
        }, ensure_ascii=False)

    url = "https://google.serper.dev/news"
    headers = {
        "X-API-KEY": api_key,
        "Content-Type": "application/json"
    }
    payload = {"q": keyword}

    try:
        logger.debug("开始发送 API 请求")
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.post(url, headers=headers, json=payload)
            data = response.json()
        logger.debug("API 请求完成")

        if "news" not in data:
            logger.error("API 响应中没有 news 字段")
            return json.dumps({
                "success": False,
                "error": "❌ 未获取到搜索结果"
            }, ensure_ascii=False)

        articles = [
            {
                "title": item.get("title"),
                "desc": item.get("snippet"),
                "url": item.get("link")
            } for item in data["news"][:5]
        ]

        output_dir = "./google_news"
        os.makedirs(output_dir, exist_ok=True)
        filename = f"google_news_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        file_path = os.path.join(output_dir, filename)

        logger.debug(f"保存结果到文件: {file_path}")
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(articles, f, ensure_ascii=False, indent=2)

        result = {
            "success": True,
            "data": {
                "message": f"✅ 已获取与 [{keyword}] 相关的前5条 Google 新闻：",
                "articles": articles,
                "file_path": file_path
            }
        }
        logger.debug("搜索完成，返回结果")
        return json.dumps(result, ensure_ascii=False)

    except Exception as e:
        logger.error(f"发生错误: {str(e)}", exc_info=True)
        return json.dumps({
            "success": False,
            "error": f"❌ 请求失败: {str(e)}"
        }, ensure_ascii=False)

# 在文件开头添加
import sys
sys.stdout.reconfigure(encoding='utf-8')
sys.stderr.reconfigure(encoding='utf-8')

if __name__ == "__main__":
    logger.info("新闻服务启动")
    
    # 主动发送工具描述
    tool_description = {
        "type": "tools",
        "data": [{
            "name": "search_google_news",
            "description": "Search news content using the Serper API based on a keyword...",
            "inputSchema": {
                "properties": {
                    "keyword": {
                        "title": "Keyword",
                        "type": "string"
                    }
                },
                "required": ["keyword"],
                "title": "search_google_newsArguments",
                "type": "object"
            }
        }]
    }

    print(json.dumps(tool_description, ensure_ascii=False))
    sys.stdout.flush()
    logger.info("工具描述已发送")

    try:
        # 添加更多调试信息
        logger.info("启动 FastMCP 服务")
        logger.debug("等待命令输入...")
        mcp.run(transport='stdio')
    except Exception as e:
        logger.error(f"服务运行出错: {str(e)}", exc_info=True)
        sys.exit(1)