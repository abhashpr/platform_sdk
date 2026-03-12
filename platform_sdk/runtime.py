import importlib.util
import sys
import json
import asyncio
from fastmcp import FastMCP

async def run_local(agent_file: str, input_data: dict, tool_name: str = None):
    """
    Simulates the platform execution locally.
    1. Loads the FastMCP instance from the file.
    2. Finds the requested tool.
    3. Executes it with provided input.
    """
    # 1. Load the module dynamically
    spec = importlib.util.spec_from_file_location("agent_module", agent_file)
    module = importlib.util.module_from_spec(spec)
    # sys.modules["agent_module"] = module
    spec.loader.exec_module(module)

    # 2. Find the FastMCP instance
    mcp_instance = None
    for attr in dir(module):
        val = getattr(module, attr)
        if isinstance(val, FastMCP):
            mcp_instance = val
            break
    
    if not mcp_instance:
        raise ValueError("No FastMCP instance found in the provided agent file.")

    # 3. FIX: Await the list_tools() coroutine
    available_tools = await mcp_instance.list_tools()
    
    if not available_tools:
        raise ValueError("No tools found in the FastMCP instance.")
    
    # 4. Determine target tool
    target_tool = tool_name or available_tools[0].name
    
    # 5. FIX: Directly await the call_tool instead of using loop.run_until_complete
    # Since run_local is already async, we just await the result.
    result = await mcp_instance.call_tool(target_tool, input_data)
    
    # 6. Convert ToolResult to serializable format
    # FastMCP returns a ToolResult object with content attribute
    if hasattr(result, 'content'):
        # result.content is a list of content items
        content = result.content
        if isinstance(content, list) and len(content) > 0:
            # Extract text or data from first content item
            item = content[0]
            if hasattr(item, 'text'):
                # TextContent - try to parse as JSON, else return as string
                try:
                    return json.loads(item.text)
                except (json.JSONDecodeError, TypeError):
                    return {"output": item.text}
            elif hasattr(item, 'data'):
                return {"data": item.data}
            else:
                return {"output": str(item)}
        return {"output": str(content)}
    
    # Fallback: try to convert to dict or return as string
    if hasattr(result, '__dict__'):
        return result.__dict__
    return {"output": str(result)}