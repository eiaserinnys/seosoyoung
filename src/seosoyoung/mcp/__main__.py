"""MCP 서버 실행 진입점"""

from seosoyoung.mcp.server import mcp

if __name__ == "__main__":
    mcp.run(transport="stdio")
