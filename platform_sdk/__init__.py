# platform_sdk/__init__.py

"""
Platform SDK - Internal Agent Development Kit

This SDK supports two modes:

1. **In-Process Mode** (default):
   Agents run inside the DE platform, imported directly.
   Use `context` and `get_llm` for governed LLM access.

2. **Federated Mode** (remote):
   Agents run on external infrastructure (e.g., AWS Lightsail).
   Use `RemoteAgentContext` for proxy-based LLM access.
   Use `serve()` to run as a standalone HTTP server.
   Include `de-bridge.js` in custom UIs for postMessage communication.

Quick Start (In-Process):
    from platform_sdk import context
    llm = context.get_llm(model="gpt-4")

Quick Start (Federated):
    from platform_sdk import RemoteAgentContext, serve
    from fastmcp import FastMCP
    
    mcp = FastMCP("My Agent")
    context = RemoteAgentContext(
        platform_url="https://de.example.com",
        agent_key="your-key",
    )
    
    @mcp.tool()
    def my_tool(input: str) -> str:
        llm = context.get_llm()
        return llm.invoke(input)
    
    if __name__ == "__main__":
        serve(mcp, port=8000)
"""

# Core (In-Process mode)
from .context import context, AgentContext
from .llm import get_llm, RouterLLM

# Remote/Federated mode
from .remote_context import (
    RemoteAgentContext,
    RemoteRouterLLM,
    get_remote_context,
)

# Server mode
from .server import (
    ExternalServer,
    serve,
    create_server,
)

# UI Bridge helpers
from .ui_bridge import (
    get_ui_bridge_script,
    generate_ui_bridge_html,
    generate_vue_composable,
    generate_react_hook,
    save_bridge_assets,
)

__version__ = "2.1.0-federated"

__all__ = [
    # Core
    "context",
    "AgentContext",
    "get_llm",
    "RouterLLM",
    # Remote
    "RemoteAgentContext",
    "RemoteRouterLLM",
    "get_remote_context",
    # Server
    "ExternalServer",
    "serve",
    "create_server",
    # UI Bridge
    "get_ui_bridge_script",
    "generate_ui_bridge_html",
    "generate_vue_composable",
    "generate_react_hook",
    "save_bridge_assets",
]