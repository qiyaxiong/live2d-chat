import asyncio
import os
import json
import sys
from typing import Optional
from contextlib import AsyncExitStack
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from dotenv import load_dotenv

# 设置标准输出和标准错误的编码
sys.stdout.reconfigure(encoding='utf-8')
sys.stderr.reconfigure(encoding='utf-8')

load_dotenv()


class MCPClient:
    def __init__(self):
        self.exit_stack = AsyncExitStack()
        self.session: Optional[ClientSession] = None

    async def initialize(self):
        """初始化MCP客户端"""
        print(json.dumps({
            "type": "status",
            "data": "初始化成功"
        }, ensure_ascii=False))
        return True

    async def connect_to_server(self, server_script_path: str):
        """连接到MCP服务器脚本"""
        is_python = server_script_path.endswith('.py')
        is_js = server_script_path.endswith('.js')
        if not (is_python or is_js):
            raise ValueError("服务器脚本必须是 .py 或 .js 文件")

        command = "python" if is_python else "node"
        server_params = StdioServerParameters(command=command, args=[server_script_path])
        stdio_transport = await self.exit_stack.enter_async_context(stdio_client(server_params))
        self.stdio, self.write = stdio_transport
        self.session = await self.exit_stack.enter_async_context(ClientSession(self.stdio, self.write))
        await self.session.initialize()

        response = await self.session.list_tools()
        # 将工具信息格式化为JSON输出
        print(json.dumps({
            "type": "tools",
            "data": [{
                "name": tool.name,
                "description": tool.description,
                "inputSchema": tool.inputSchema
            } for tool in response.tools]
        }, ensure_ascii=False))
        sys.stdout.flush()
        return response.tools

    async def call_tool(self, tool_name: str, args: dict):
        """调用MCP工具"""
        if not self.session:
            return {"success": False, "error": "未连接到服务器"}
        try:
            result = await self.session.call_tool(tool_name, args)
            
            if not result.content:
                return {
                    "success": False,
                    "error": "工具返回空结果"
                }
                
            if isinstance(result.content[0].text, str):
                try:
                    json_result = json.loads(result.content[0].text)
                    return {
                        "success": True,
                        "data": json_result
                    }
                except json.JSONDecodeError as e:
                    return {
                        "success": True,
                        "data": result.content[0].text
                    }
            return {
                "success": True,
                "data": result.content[0].text if result.content else None
            }
        except Exception as e:
            return {
                "success": False, 
                "error": f"工具调用失败: {str(e)}"
            }

    async def cleanup(self):
        """清理资源"""
        await self.exit_stack.aclose()
        print("🛑 MCP客户端已关闭")


async def handle_command(command, client):
    print(f"收到命令: {command}")  # 这里会打印收到的命令
    try:
        data = json.loads(command)
        if data.get('method'):  # 处理 JSON-RPC 格式
            tool_name = data['method']
            params = data['params']
            # 确保参数中的中文正确编码
            if isinstance(params, dict):
                params = {k: v.encode('utf-8').decode('utf-8') if isinstance(v, str) else v 
                         for k, v in params.items()}
            result = await client.call_tool(tool_name, params)
            print(json.dumps(result, ensure_ascii=False))
            sys.stdout.flush()
        elif data.get('tool'):  # 处理旧格式
            result = await client.call_tool(data['tool'], data.get('args', {}))
            print(json.dumps(result, ensure_ascii=False))
            sys.stdout.flush()
    except json.JSONDecodeError as e:
        print(json.dumps({
            'success': False,
            'error': f"JSON 解析错误: {str(e)}"
        }, ensure_ascii=False))
        sys.stdout.flush()
    except Exception as e:
        print(json.dumps({
            'success': False,
            'error': f"处理命令时出错: {str(e)}"
        }, ensure_ascii=False))
        sys.stdout.flush()


async def main():
    client = MCPClient()
    await client.initialize()

    # 示例：连接一个服务器并列出其支持的工具
    server_script_path = "D:\\knowledge\\repo\\ai_chat\\electron-live2d\\mcp-project\\news.py"  # 替换为你自己的路径
    try:
        tools = await client.connect_to_server(server_script_path)

        for tool in tools:
            print(f" - tool: {tool.name}")
            print(f"   descr: {tool.description}")
            print(f"   schema: {tool.inputSchema}")

    except Exception as e:
        print(f"❌ 连接服务器失败: {e}")

    # 继续监听命令（可选）
    while True:
        try:
            command = input()
            if not command.strip():
                continue
            await handle_command(command, client)
        except KeyboardInterrupt:
            break
        except Exception as e:
            print(json.dumps({'success': False, 'error': str(e)}))
            sys.stdout.flush()

    await client.cleanup()


if __name__ == "__main__":
    asyncio.run(main())