import click
import json
import os
import asyncio
from platform_sdk.runtime import run_local
from platform_sdk.publisher import register_mcp_agent  # Updated for MCP
from dotenv import load_dotenv

load_dotenv() # This looks for a .env file in the current directory

@click.group()
def cli():
    """Platform SDK - Data Engineering AI Agent Orchestrator
    
    Supports two modes:
    - In-Process: Agents run inside the DE platform
    - Federated: Agents run on external infrastructure
    """
    pass

@cli.command()
@click.option("--file", required=True, type=click.Path(exists=True), help="Path to the agent .py file")
@click.option("--tool", required=False, help="Specific MCP tool name to run (defaults to first tool found)")
@click.option("--input", required=True, help="JSON input for the tool (e.g. '{\"table_name\": \"users\"}')")
def run(file, tool, input):
    """Run an MCP agent locally using the remote ModelRouter."""
    try:
        # Parse the input string into a dict to ensure it's valid JSON before sending
        input_data = json.loads(input)
        
        # ⚡️ The Fix: Wrap the sync call to handle the async runtime
        async def execute():
            # We assume run_local is now an async function or 
            # handles the await internally.
            return await run_local(file, input_data, tool_name=tool)
        
        # Pass the 'tool' parameter to the runtime so it knows which function to call
        output = asyncio.run(execute())
        
        click.secho("\n🚀 Agent Output:", fg="green", bold=True)
        click.echo(json.dumps(output, indent=2))
        
    except json.JSONDecodeError:
        click.secho("❌ Error: --input must be a valid JSON string.", fg="red")
    except Exception as e:
        click.secho(f"❌ Execution Failed: {str(e)}", fg="red")

@cli.command("register")
@click.option("--file", required=True, type=click.Path(exists=True), help="The .py file containing the FastMCP agent")
@click.option("--name", required=True, help="Display name for the marketplace")
@click.option("--category", default="General", help="Marketplace category (Migration, Modeling, etc.)")
def register(file, name, category):
    """Push a local MCP agent to the Lightsail Control Plane."""
    click.echo(f"📦 Preparing to publish '{name}'...")
    
    # ⚡️ Fix: Use asyncio to run the registration if it performs MCP inspection
    async def execute_registration():
        # Passing context/env vars here ensures the publisher knows WHERE to push
        return await register_mcp_agent(file_path=file, name=name, category=category)
    
    try:
        # Use the new publisher that handles the file-to-metadata conversion
        result = asyncio.run(execute_registration())
    
        if result.get("success"):
            click.secho(f"✅ Successfully registered '{name}'!", fg="green", bold=True)
            # Ensure we show the port in the link if necessary
            base_url = os.getenv('PLATFORM_BASE_URL', 'http://localhost:5002')
            click.echo(f"🔗 View it at: {base_url}/catalog")
        else:
            error_detail = result.get('error', 'Unknown Error')
            click.secho(f"❌ Registration failed: {error_detail}", fg="red")
            
    except Exception as e:
        click.secho(f"❌ Critical Registration Failure: {str(e)}", fg="red")


@cli.command("serve")
@click.option("--file", required=True, type=click.Path(exists=True), help="Path to the agent .py file")
@click.option("--port", default=8000, help="Port to listen on (default: 8000)")
@click.option("--host", default="0.0.0.0", help="Host to bind to (default: 0.0.0.0)")
def serve(file, port, host):
    """Run an MCP agent as a standalone HTTP server (Federated mode).
    
    This allows the agent to run on external infrastructure (e.g., AWS Lightsail)
    while still being accessible from the DE platform.
    
    Example:
        platform serve --file my_agent.py --port 8000
    """
    try:
        import importlib.util
        from fastmcp import FastMCP
        from platform_sdk.server import ExternalServer
    except ImportError as e:
        click.secho(
            f"❌ Missing dependencies for server mode.\n"
            f"   Install with: pip install platform-sdk[server]\n"
            f"   Error: {e}",
            fg="red"
        )
        return
    
    click.echo(f"🔍 Loading agent from {file}...")
    
    # Load the module dynamically
    spec = importlib.util.spec_from_file_location("agent_module", file)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    
    # Find the FastMCP instance
    mcp_instance = None
    for attr in dir(module):
        val = getattr(module, attr)
        if isinstance(val, FastMCP):
            mcp_instance = val
            break
    
    if not mcp_instance:
        click.secho("❌ No FastMCP instance found in the provided agent file.", fg="red")
        return
    
    agent_name = getattr(mcp_instance, 'name', os.path.basename(file))
    click.secho(f"✅ Found agent: {agent_name}", fg="green")
    
    # Create and run the server
    server = ExternalServer(mcp_instance, port=port, host=host)
    server.run()


@cli.command("bridge")
@click.option("--output", "-o", default="./de-bridge", help="Output directory for bridge assets")
@click.option("--format", type=click.Choice(["all", "js", "vue", "react"]), default="all", help="Which files to generate")
def bridge(output, format):
    """Generate UI bridge assets for custom agent UIs (Federated mode).
    
    Creates JavaScript helpers that allow custom UIs to communicate with
    the DE platform shell via postMessage.
    
    Example:
        platform bridge --output ./src/lib
    """
    from platform_sdk.ui_bridge import (
        get_ui_bridge_script,
        generate_vue_composable,
        generate_react_hook,
    )
    
    os.makedirs(output, exist_ok=True)
    
    files_created = []
    
    if format in ["all", "js"]:
        with open(os.path.join(output, "de-bridge.js"), "w") as f:
            f.write(get_ui_bridge_script())
        files_created.append("de-bridge.js")
    
    if format in ["all", "vue"]:
        with open(os.path.join(output, "useDEBridge.vue.js"), "w") as f:
            f.write(generate_vue_composable())
        files_created.append("useDEBridge.vue.js")
    
    if format in ["all", "react"]:
        with open(os.path.join(output, "useDEBridge.react.js"), "w") as f:
            f.write(generate_react_hook())
        files_created.append("useDEBridge.react.js")
    
    click.secho(f"✅ Bridge assets created in {output}/", fg="green", bold=True)
    for f in files_created:
        click.echo(f"   - {f}")
    
    click.echo("\n📖 Usage:")
    click.echo("   1. Include de-bridge.js in your HTML")
    click.echo("   2. Import useDEBridge composable/hook in your Vue/React app")
    click.echo("   3. Call bridge.run() or bridge.invokeTool() to communicate with DE")


@cli.command("info")
def info():
    """Show SDK version and configuration info."""
    from platform_sdk import __version__
    
    click.secho("Platform SDK", fg="cyan", bold=True)
    click.echo(f"  Version: {__version__}")
    click.echo("")
    click.echo("Environment:")
    click.echo(f"  DE_PLATFORM_URL: {os.getenv('DE_PLATFORM_URL', '(not set)')}")
    click.echo(f"  DE_AGENT_KEY: {'***' if os.getenv('DE_AGENT_KEY') else '(not set)'}")
    click.echo(f"  PLATFORM_BASE_URL: {os.getenv('PLATFORM_BASE_URL', '(not set)')}")
    click.echo("")
    click.echo("Installation:")
    click.echo("  pip install platform-sdk          # Core only")
    click.echo("  pip install platform-sdk[remote]  # + Remote context")
    click.echo("  pip install platform-sdk[server]  # + Server mode")
    click.echo("  pip install platform-sdk[full]    # All features")