"""MCP 서버 실행 진입점"""

import sys

from seosoyoung.mcp.server import mcp

if __name__ == "__main__":
    transport = "stdio"
    host = "127.0.0.1"
    port = 3104

    for arg in sys.argv[1:]:
        if arg.startswith("--transport="):
            transport = arg.split("=", 1)[1]
        elif arg.startswith("--port="):
            port = int(arg.split("=", 1)[1])
        elif arg.startswith("--host="):
            host = arg.split("=", 1)[1]

    if transport == "sse":
        mcp.run(transport="sse", host=host, port=port)
    else:
        mcp.run(transport="stdio")
