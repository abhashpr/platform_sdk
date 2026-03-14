"""External Server for Federated Mode.

This module allows agents to run as standalone HTTP servers, exposing their
tools via the MCP protocol over HTTP/SSE.

Usage:
    from platform_sdk import serve
    from fastmcp import FastMCP
    
    mcp = FastMCP("My Agent")
    
    @mcp.tool()
    def my_tool(input: str) -> str:
        return f"Processed: {input}"
    
    # Run as a standalone server
    if __name__ == "__main__":
        serve(mcp, port=8000)

Or programmatically:
    from platform_sdk import ExternalServer
    
    server = ExternalServer(mcp, port=8000)
    server.run()
"""

import asyncio
import json
import uuid
from typing import Any, Dict, List, Optional, Union

from pydantic import BaseModel

try:
    from fastapi import FastAPI, HTTPException, Request
    from fastapi.middleware.cors import CORSMiddleware
    from fastapi.responses import JSONResponse, StreamingResponse
    import uvicorn
except ImportError:
    FastAPI = None
    uvicorn = None

try:
    from fastmcp import FastMCP
except ImportError:
    FastMCP = None


class RunRequest(BaseModel):
    """Request payload for /run endpoint."""
    instructions: str
    user_id: Optional[str] = None
    run_id: Optional[str] = None
    agent_id: Optional[str] = None
    model: Optional[str] = None
    temperature: Optional[float] = None
    max_tokens: Optional[int] = None


class ToolInvokeRequest(BaseModel):
    """Request payload for /tools/{name}/invoke endpoint."""
    arguments: Dict[str, Any]
    user_id: Optional[str] = None
    run_id: Optional[str] = None


class ExternalServer:
    """Wraps a FastMCP agent into a standalone HTTP server.
    
    This server exposes:
    - GET /schema - Returns the agent's tool schema
    - POST /run - Executes the agent with given instructions
    - POST /run/stream - Executes with SSE streaming
    - POST /tools/{name}/invoke - Invokes a specific tool
    - GET /health - Health check endpoint
    
    Example:
        from fastmcp import FastMCP
        from platform_sdk import ExternalServer
        
        mcp = FastMCP("Data Transformer")
        
        @mcp.tool()
        def transform(data: str) -> str:
            return data.upper()
        
        server = ExternalServer(mcp, port=8000)
        server.run()
    """
    
    def __init__(
        self,
        mcp: "FastMCP",
        port: int = 8000,
        host: str = "0.0.0.0",
        title: Optional[str] = None,
        description: Optional[str] = None,
        cors_origins: List[str] = None,
    ):
        """Initialize the external server.
        
        Args:
            mcp: The FastMCP instance containing the agent's tools
            port: Port to listen on (default: 8000)
            host: Host to bind to (default: 0.0.0.0)
            title: API title (default: uses MCP name)
            description: API description
            cors_origins: Allowed CORS origins (default: ["*"])
        """
        if FastAPI is None:
            raise ImportError(
                "FastAPI is required for server mode. "
                "Install with: pip install fastapi uvicorn"
            )
        
        self.mcp = mcp
        self.port = port
        self.host = host
        self.title = title or getattr(mcp, 'name', 'MCP Agent Server')
        self.description = description or f"External server for {self.title}"
        self.cors_origins = cors_origins or ["*"]
        
        self.app = self._create_app()
    
    def _create_app(self) -> "FastAPI":
        """Create the FastAPI application."""
        app = FastAPI(
            title=self.title,
            description=self.description,
        )
        
        # Add CORS middleware
        app.add_middleware(
            CORSMiddleware,
            allow_origins=self.cors_origins,
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )
        
        # Register routes
        self._register_routes(app)
        
        return app
    
    def _register_routes(self, app: "FastAPI"):
        """Register API endpoints."""
        
        @app.get("/health")
        async def health():
            """Health check endpoint."""
            return {"status": "ok", "agent": self.title}
        
        @app.get("/schema")
        async def get_schema():
            """Return the agent's tool schema."""
            tools = await self.mcp.list_tools()
            
            tool_schemas = []
            for tool in tools:
                tool_schema = {
                    "name": tool.name,
                    "description": tool.description or "",
                    "inputSchema": tool.inputSchema if hasattr(tool, 'inputSchema') else {},
                }
                tool_schemas.append(tool_schema)
            
            # Build a unified input schema from the first tool (usually "run")
            run_tool = next((t for t in tools if t.name == "run"), None)
            input_schema = {}
            if run_tool and hasattr(run_tool, 'inputSchema'):
                input_schema = run_tool.inputSchema
            elif len(tools) > 0 and hasattr(tools[0], 'inputSchema'):
                input_schema = tools[0].inputSchema
            
            return {
                "name": self.title,
                "description": self.description,
                "source": "remote_mcp",
                "tools": tool_schemas,
                "input_schema": input_schema,
            }
        
        @app.post("/run")
        async def run_agent(request: RunRequest):
            """Execute the agent with given instructions."""
            run_id = request.run_id or str(uuid.uuid4())
            
            # Find the primary tool (usually "run" or the first tool)
            tools = await self.mcp.list_tools()
            run_tool = next((t for t in tools if t.name == "run"), None)
            target_tool = run_tool or (tools[0] if tools else None)
            
            if not target_tool:
                raise HTTPException(status_code=400, detail="No tools available")
            
            # Build arguments from request
            args = {"instructions": request.instructions}
            if request.model:
                args["model"] = request.model
            if request.temperature is not None:
                args["temperature"] = request.temperature
            if request.max_tokens is not None:
                args["max_tokens"] = request.max_tokens
            
            try:
                result = await self.mcp.call_tool(target_tool.name, args)
                
                # Parse result
                output = self._parse_tool_result(result)
                
                return {
                    "run_id": run_id,
                    "result": output,
                    "trace": [
                        {
                            "node": "remote_mcp",
                            "tool": target_tool.name,
                            "agent": self.title,
                        }
                    ],
                }
            except Exception as e:
                raise HTTPException(status_code=500, detail=str(e))
        
        @app.post("/run/stream")
        async def run_agent_stream(request: RunRequest):
            """Execute the agent with SSE streaming response."""
            run_id = request.run_id or str(uuid.uuid4())
            
            async def event_generator():
                # Send start event
                yield f"data: {json.dumps({'type': 'start', 'run_id': run_id})}\n\n"
                
                try:
                    tools = await self.mcp.list_tools()
                    run_tool = next((t for t in tools if t.name == "run"), None)
                    target_tool = run_tool or (tools[0] if tools else None)
                    
                    if not target_tool:
                        yield f"data: {json.dumps({'type': 'error', 'error': 'No tools available'})}\n\n"
                        return
                    
                    args = {"instructions": request.instructions}
                    result = await self.mcp.call_tool(target_tool.name, args)
                    output = self._parse_tool_result(result)
                    
                    # Send result
                    yield f"data: {json.dumps({'type': 'result', 'result': output})}\n\n"
                    
                except Exception as e:
                    yield f"data: {json.dumps({'type': 'error', 'error': str(e)})}\n\n"
                
                # Send done event
                yield f"data: {json.dumps({'type': 'done', 'run_id': run_id})}\n\n"
            
            return StreamingResponse(
                event_generator(),
                media_type="text/event-stream",
                headers={
                    "Cache-Control": "no-cache",
                    "Connection": "keep-alive",
                },
            )
        
        @app.post("/tools/{tool_name}/invoke")
        async def invoke_tool(tool_name: str, request: ToolInvokeRequest):
            """Invoke a specific tool by name."""
            run_id = request.run_id or str(uuid.uuid4())
            
            try:
                result = await self.mcp.call_tool(tool_name, request.arguments)
                output = self._parse_tool_result(result)
                
                return {
                    "run_id": run_id,
                    "tool": tool_name,
                    "result": output,
                }
            except Exception as e:
                raise HTTPException(status_code=500, detail=str(e))
    
    def _parse_tool_result(self, result) -> Any:
        """Parse a FastMCP ToolResult into a serializable format."""
        if hasattr(result, 'content'):
            content = result.content
            if isinstance(content, list) and len(content) > 0:
                item = content[0]
                if hasattr(item, 'text'):
                    try:
                        return json.loads(item.text)
                    except (json.JSONDecodeError, TypeError):
                        return item.text
                elif hasattr(item, 'data'):
                    return item.data
                else:
                    return str(item)
            return str(content)
        
        if hasattr(result, '__dict__'):
            return result.__dict__
        return str(result)
    
    def run(self):
        """Start the server (blocking)."""
        if uvicorn is None:
            raise ImportError("uvicorn is required. Install with: pip install uvicorn")
        
        print(f"🚀 Starting {self.title} on http://{self.host}:{self.port}")
        print(f"📄 Schema: http://{self.host}:{self.port}/schema")
        print(f"▶️  Run: POST http://{self.host}:{self.port}/run")
        
        uvicorn.run(self.app, host=self.host, port=self.port)
    
    async def run_async(self):
        """Start the server (async)."""
        if uvicorn is None:
            raise ImportError("uvicorn is required.")
        
        config = uvicorn.Config(self.app, host=self.host, port=self.port)
        server = uvicorn.Server(config)
        await server.serve()


def serve(
    mcp: "FastMCP",
    port: int = 8000,
    host: str = "0.0.0.0",
    **kwargs,
):
    """Convenience function to serve a FastMCP agent.
    
    Usage:
        from platform_sdk import serve
        from fastmcp import FastMCP
        
        mcp = FastMCP("My Agent")
        
        @mcp.tool()
        def hello(name: str) -> str:
            return f"Hello, {name}!"
        
        if __name__ == "__main__":
            serve(mcp, port=8000)
    """
    server = ExternalServer(mcp, port=port, host=host, **kwargs)
    server.run()


def create_server(
    mcp: "FastMCP",
    **kwargs,
) -> ExternalServer:
    """Create an ExternalServer without starting it.
    
    Useful for integrating into larger applications or testing.
    """
    return ExternalServer(mcp, **kwargs)
