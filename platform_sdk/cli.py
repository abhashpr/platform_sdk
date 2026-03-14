import click
import json
import os
import asyncio
from platform_sdk.runtime import run_local
from platform_sdk.publisher import register_mcp_agent  # Updated for MCP
from platform_sdk.client import PlatformClient
from platform_sdk.env_utils import update_env_file
from platform_sdk.auth_helper import (
    authenticate_and_update_env,
    prompt_for_token,
    AuthResult,
)
from platform_sdk.token_manager import (
    get_token_status,
    get_valid_token,
    clear_tokens,
    load_tokens,
)
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


@cli.command("auth")
@click.option(
    "--url",
    default=None,
    envvar="PLATFORM_BASE_URL",
    help="Platform URL (or set PLATFORM_BASE_URL env var)",
)
@click.option(
    "--manual",
    is_flag=True,
    help="Manually paste a token instead of browser auth",
)
@click.option(
    "--port",
    default=9876,
    help="Local port for auth callback (default: 9876)",
)
def auth(url, manual, port):
    """
    Authenticate with the DE Platform and update .env.

    Opens your browser to log in, then automatically saves the token
    to your local .env file. Tokens auto-refresh for 30 days.

    \b
    Examples:
        platform auth
        platform auth --url https://de.example.com
        platform auth --manual  # Paste token instead of browser flow
    """
    if not url:
        # Try to get from environment or prompt
        url = os.getenv("PLATFORM_BASE_URL") or os.getenv("PLATFORM_URL")
        if not url:
            click.secho("❌ No platform URL specified.", fg="red")
            click.echo("   Use --url or set PLATFORM_BASE_URL environment variable.")
            raise SystemExit(1)

    click.secho(f"🔐 Authenticating with {url}", fg="cyan", bold=True)
    click.echo()

    if manual:
        # Manual token entry
        token = prompt_for_token()
        if token:
            update_env_file("PLATFORM_API_TOKEN", token)
            click.secho("\n✅ Token saved to .env!", fg="green", bold=True)
            click.echo("   You can now run your agent: python your_agent.py")
            click.echo()
            click.secho("   ⚠️  Manual tokens expire in 1 hour.", fg="yellow")
            click.echo("   For auto-refresh, use: platform auth (without --manual)")
        else:
            click.secho("\n❌ No token provided.", fg="red")
            raise SystemExit(1)
    else:
        # Browser-based authentication
        def on_status(msg: str):
            click.echo(f"   {msg}")

        result = authenticate_and_update_env(
            platform_url=url,
            callback_port=port,
            on_status=on_status,
        )

        if result.success:
            click.echo()
            click.secho("✅ Authentication successful!", fg="green", bold=True)
            if result.refresh_token:
                click.echo("   🔄 Auto-refresh enabled (tokens refresh for 30 days)")
            else:
                click.echo("   ⚠️  No refresh token - expires in 1 hour")
            click.echo()
            click.echo("   You can now run your agent:")
            click.secho("   python your_agent.py", fg="cyan")
        else:
            click.echo()
            click.secho(f"❌ Authentication failed: {result.error}", fg="red")
            raise SystemExit(1)


@cli.command("status")
def status():
    """
    Show current authentication status.

    Displays information about your current authentication method,
    token expiration, and whether auto-refresh is enabled.

    \b
    Examples:
        platform status
    """
    import datetime
    
    click.secho("🔐 Authentication Status", fg="cyan", bold=True)
    click.echo()
    
    token_status = get_token_status()
    method = token_status.get("auth_method")
    
    if method == "agent_key":
        click.secho("   Method: Platform Agent Key", fg="green")
        click.echo("   Expires: Never (until revoked)")
        click.echo()
        click.secho("   ✓ Production-ready authentication", fg="green")
        
    elif method == "env_token":
        click.secho("   Method: Environment Variable (PLATFORM_API_TOKEN)", fg="yellow")
        expires_in = token_status.get("expires_in_seconds", 0)
        if expires_in > 0:
            hours = expires_in // 3600
            minutes = (expires_in % 3600) // 60
            click.echo(f"   Expires in: {hours}h {minutes}m")
        else:
            click.secho("   Status: EXPIRED", fg="red")
        click.echo()
        if token_status.get("needs_refresh"):
            click.secho("   ⚠️  Token needs refresh. Run: platform auth", fg="yellow")
        else:
            click.echo("   Run 'platform auth' before expiration for auto-refresh")
            
    elif method == "stored_token":
        click.secho("   Method: Stored Token (auto-refresh enabled)", fg="green")
        expires_in = token_status.get("expires_in_seconds", 0)
        
        if expires_in > 0:
            hours = expires_in // 3600
            minutes = (expires_in % 3600) // 60
            click.echo(f"   ID Token expires in: {hours}h {minutes}m")
        else:
            click.echo("   ID Token: Expired (will refresh on next use)")
        
        if token_status.get("can_auto_refresh"):
            click.secho("   🔄 Auto-refresh: Enabled (30 days)", fg="green")
        else:
            click.secho("   ⚠️  Auto-refresh: Disabled (missing Cognito config)", fg="yellow")
        
        if token_status.get("platform_url"):
            click.echo(f"   Platform: {token_status['platform_url']}")
            
    else:
        click.secho("   Status: Not authenticated", fg="red")
        click.echo()
        click.echo("   Run: platform auth --url https://your-platform.com")


@cli.command("logout")
def logout():
    """
    Clear stored authentication tokens.

    Removes tokens from ~/.de_platform/config. Does not affect
    .env files or environment variables.

    \b
    Examples:
        platform logout
    """
    click.secho("🔐 Logging out...", fg="cyan")
    
    tokens = load_tokens()
    if tokens:
        if clear_tokens():
            click.secho("   ✓ Cleared stored tokens from ~/.de_platform/config", fg="green")
        else:
            click.secho("   ✗ Failed to clear tokens", fg="red")
    else:
        click.echo("   No stored tokens found")
    
    # Check for env vars
    if os.getenv("PLATFORM_AGENT_KEY"):
        click.echo()
        click.secho("   Note: PLATFORM_AGENT_KEY is set in environment", fg="yellow")
        click.echo("   Remove it from your shell or .env to fully logout")
    
    if os.getenv("PLATFORM_API_TOKEN"):
        click.echo()
        click.secho("   Note: PLATFORM_API_TOKEN is set in environment", fg="yellow")
        click.echo("   Remove it from your shell or .env to fully logout")
    
    click.echo()
    click.secho("✅ Logged out", fg="green")


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


@cli.command("publish")
@click.option("--name", required=True, help="Display name for the agent in the platform")
@click.option("--version", default="0.0.1", help="Semver version string (default: 0.0.1)")
@click.option("--entry", default="agent.py", help="Entry-point file to include (default: agent.py)")
@click.option("--description", default="", help="Short description shown in the My Agents catalog")
@click.option(
    "--include",
    multiple=True,
    help="Extra glob patterns to include (e.g. --include 'lib/*.py'). "
         "agent.py is always included. venv/, __pycache__/, and *.pyc are excluded.",
)
def publish(name, version, entry, description, include):
    """Package and publish a local agent to the DE platform.

    Zips the agent file (and any extra --include patterns) and POSTs the
    bundle to POST /api/agents/upload on the platform.  On success the
    platform assigns an agent_id and returns it so you can open the agent
    in the 'My Agents' catalog.

    Required environment variables:
        PLATFORM_BASE_URL   — e.g. https://your-lightsail-domain.com
        PLATFORM_API_TOKEN  — Cognito id_token (copy from browser DevTools)

    Example:
        platform publish --name "LogArchitect" --entry log_architect_remote.py
    """
    import glob
    import io as _io
    import zipfile as _zipfile

    entry_path = os.path.abspath(entry)
    if not os.path.exists(entry_path):
        click.secho(f"❌ Entry file not found: {entry_path}", fg="red")
        raise SystemExit(1)

    # ── Gather files ──────────────────────────────────────────────────────────
    files_to_pack: list[tuple[str, str]] = []  # (abs_path, archive_name)

    def _add(abs_path: str, arc_name: str):
        # Security: reject absolute arc names and path traversal
        if arc_name.startswith("/") or ".." in arc_name:
            return
        files_to_pack.append((abs_path, arc_name))

    _add(entry_path, os.path.basename(entry_path))

    base_dir = os.path.dirname(entry_path)
    skip_dirs = {".venv", "venv", "__pycache__", ".git", "node_modules", ".mypy_cache"}

    for pattern in include:
        for matched in glob.glob(os.path.join(base_dir, pattern), recursive=True):
            if not os.path.isfile(matched):
                continue
            rel = os.path.relpath(matched, base_dir)
            # Skip venv/cache
            parts = rel.replace("\\", "/").split("/")
            if any(p in skip_dirs for p in parts):
                continue
            if rel.endswith(".pyc"):
                continue
            _add(os.path.abspath(matched), rel.replace("\\", "/"))

    click.echo(f"📦 Packing {len(files_to_pack)} file(s)...")
    for _, arc in files_to_pack:
        click.echo(f"   + {arc}")

    # ── Build zip in memory ───────────────────────────────────────────────────
    buf = _io.BytesIO()
    with _zipfile.ZipFile(buf, "w", _zipfile.ZIP_DEFLATED) as zf:
        for abs_path, arc_name in files_to_pack:
            zf.write(abs_path, arc_name)
    buf.seek(0)

    # ── POST to platform ──────────────────────────────────────────────────────
    try:
        client = PlatformClient()
    except RuntimeError as e:
        click.secho(f"❌ {e}", fg="red")
        raise SystemExit(1)

    click.echo(f"🚀 Publishing '{name}' v{version} to {client.base_url} ...")

    try:
        result = client.post_multipart(
            "/api/agents/upload",
            fields={
                "name": name,
                "version": version,
                "description": description,
            },
            file_field="file",
            file_name=f"{name.replace(' ', '_')}.zip",
            file_bytes=buf.read(),
            content_type="application/zip",
        )
    except Exception as exc:
        click.secho(f"❌ Upload failed: {exc}", fg="red")
        raise SystemExit(1)

    agent_id = result.get("id", "unknown")
    base_url = client.base_url.rstrip("/")

    click.secho(f"\n✅ Published '{name}' v{version}!", fg="green", bold=True)
    click.echo(f"   Agent ID : {agent_id}")
    click.echo(f"   Status   : {result.get('status', '?')}")
    click.echo(f"   Agent Key: {result.get('agent_key', '?')}")
    click.echo(f"\n🔗 Open in My Agents: {base_url}/my-agents")
    click.echo(
        f"\nTo deploy:  curl -X POST {base_url}/api/agents/managed/{agent_id}/deploy"
        f" -H 'Authorization: Bearer $PLATFORM_API_TOKEN'"
    )


@cli.command("discover")
@click.option("--url", required=True, help="URL of the running MCP agent (e.g. http://localhost:8001)")
@click.option("--name", default=None, help="Override the display name (uses agent's own name if omitted)")
def discover(url, name):
    """Connect a running remote MCP agent to the DE platform.

    The platform will ping the agent's GET /health and GET /schema endpoints,
    read its tool manifest, and register it in the My Agents catalog — all in
    one step. No manual curl needed.

    Required environment variables:
        PLATFORM_BASE_URL   — e.g. https://your-lightsail-domain.com
        PLATFORM_API_TOKEN  — Cognito id_token

    Example:
        platform discover --url http://ubuntu-ws-ip:8001
        platform discover --url http://10.0.0.42:8001 --name "LogArchitect"
    """
    try:
        client = PlatformClient()
    except RuntimeError as e:
        click.secho(f"❌ {e}", fg="red")
        raise SystemExit(1)

    click.echo(f"🔍 Discovering agent at {url} ...")

    payload = {"url": url}
    if name:
        payload["name"] = name

    try:
        result = client.post("/api/agents/discover", json=payload)
    except Exception as exc:
        click.secho(f"❌ Discovery failed: {exc}", fg="red")
        raise SystemExit(1)

    click.secho(f"\n✅ Agent connected: '{result.get('name')}'", fg="green", bold=True)
    click.echo(f"   Agent ID  : {result.get('id')}")
    click.echo(f"   Tools     : {', '.join(result.get('tools', []))}")
    click.echo(f"   Agent Key : {result.get('agent_key', '?')}")
    click.echo(f"\n🔗 Open in My Agents: {client.base_url.rstrip('/')}/my-agents")
    click.echo(
        "\nSave the agent_key — it's only shown once.\n"
        "Use it as X-DE-AGENT-KEY to access governed LLM calls from inside the agent."
    )