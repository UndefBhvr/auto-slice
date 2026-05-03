#!/bin/bash
# Start UI with proper CJK font support for WSL

# For WSL2 with GUI support or X server
export DISPLAY=$(cat /etc/resolv.conf | grep nameserver | awk '{print $2}'):0

# Ensure UTF-8 locale
export LANG=en_US.UTF-8
export LC_ALL=en_US.UTF-8

# For Windows Python running in WSL, set environment for proper font rendering
export QT_QPA_PLATFORM=windows

python3 -c "
import sys
sys.path.insert(0, sys.path[0] if sys.path[0] else '.')

import json
import httpx
from ui.app import SegmentApp

# Test connection to MCP server
try:
    response = httpx.get('http://127.0.0.1:8765/segments', timeout=5.0)
    print('MCP server connection: OK')
    print('Response encoding:', response.encoding)
except Exception as e:
    print(f'MCP server connection failed: {e}')
    print('Make sure MCP server is running: python3 -m mcp_server.server')

app = SegmentApp()
app.run()
"
