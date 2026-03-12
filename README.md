# Platform SDK

Internal Agent Development Kit for the DE Platform.

## Overview

This SDK supports two deployment modes:

| Mode | Description | Use Case |
|------|-------------|----------|
| **In-Process** | Agents run inside the DE platform | Simple tools, quick development |
| **Federated** | Agents run on external infrastructure | Complex apps, custom UIs |

## Installation

```bash
# Core only (In-Process mode)
pip install platform-sdk

# With remote context support
pip install platform-sdk[remote]

# With server mode (for Federated deployments)
pip install platform-sdk[server]

# Full installation
pip install platform-sdk[full]
```

## Quick Start

### In-Process Mode (Default)

```python
from platform_sdk import context
from fastmcp import FastMCP

mcp = FastMCP("My Agent")

@mcp.tool()
def analyze(data: str) -> str:
    # Use governed LLM through the platform
    llm = context.get_llm(model="gpt-4")
    return llm.invoke(f"Analyze: {data}")
```

### Federated Mode (Remote)

```python
from platform_sdk import RemoteAgentContext, serve
from fastmcp import FastMCP

mcp = FastMCP("My Remote Agent")

# Connect to DE platform proxy
context = RemoteAgentContext(
    platform_url="https://de.example.com",
    agent_key="your-agent-key",  # From registration
)

@mcp.tool()
def analyze(data: str) -> str:
    llm = context.get_llm(model="gpt-4")
    return llm.invoke(f"Analyze: {data}")

# Run as standalone HTTP server
if __name__ == "__main__":
    serve(mcp, port=8000)
```

## CLI Commands

```bash
# Run an agent locally
platform run --file my_agent.py --input '{"data": "test"}'

# Register with the platform
platform register --file my_agent.py --name "My Agent"

# Run as standalone server (Federated mode)
platform serve --file my_agent.py --port 8000

# Generate UI bridge assets
platform bridge --output ./src/lib

# Show SDK info
platform info
```

## Custom UI Integration

When building custom UIs for Federated agents, use the UI bridge:

```html
<!-- Include in your HTML -->
<script src="de-bridge.js"></script>

<script>
  // Wait for connection to DE shell
  await window.deBridge.ready();
  
  // Run the agent
  const result = await window.deBridge.run({
    instructions: "Process this data"
  });
  
  // Invoke a specific tool
  const toolResult = await window.deBridge.invokeTool("analyze", {
    data: "hello"
  });
</script>
```

### Vue 3

```javascript
import { useDEBridge } from './useDEBridge.vue.js';

const { isReady, run, invokeTool, loading, error } = useDEBridge();

async function handleAnalyze() {
  const result = await run({ instructions: "Analyze data" });
}
```

### React

```javascript
import { useDEBridge } from './useDEBridge.react.js';

function MyComponent() {
  const { isReady, run, loading, error } = useDEBridge();
  
  const handleAnalyze = async () => {
    const result = await run({ instructions: "Analyze data" });
  };
}
```

## Environment Variables

| Variable | Description |
|----------|-------------|
| `DE_PLATFORM_URL` | Base URL of the DE platform |
| `DE_AGENT_KEY` | Agent API key (from registration) |
| `DE_AGENT_ID` | Agent ID in the platform registry |
| `PLATFORM_BASE_URL` | Alternative to `DE_PLATFORM_URL` |

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    DE Platform Shell                     │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────┐ │
│  │ Native UI   │  │   Iframe    │  │  LLM Proxy      │ │
│  │ (Internal)  │  │ (External)  │  │ /api/proxy/*    │ │
│  └─────────────┘  └──────┬──────┘  └────────┬────────┘ │
└──────────────────────────┼──────────────────┼──────────┘
                           │ postMessage      │ HTTP
                           ▼                  ▼
              ┌────────────────────────────────────────┐
              │         Federated Agent Server         │
              │  ┌──────────┐  ┌────────────────────┐ │
              │  │ Custom UI │  │ RemoteAgentContext │ │
              │  │ (Vue/React)│  │ → Proxy LLM calls │ │
              │  └──────────┘  └────────────────────┘ │
              │  ┌──────────────────────────────────┐ │
              │  │        FastMCP Tools             │ │
              │  └──────────────────────────────────┘ │
              └────────────────────────────────────────┘
```

## Development Setup

```powershell
# Create sandbox
mkdir agent_sandbox
cd agent_sandbox
python -m venv .venv
.\.venv\Scripts\Activate

# Install SDK in editable mode
pip install -e C:\path\to\platform-sdk[full]

# Set environment
$env:DE_PLATFORM_URL = "https://de.example.com"
$env:DE_AGENT_KEY = "your-key"

# Run your agent
platform serve --file my_agent.py --port 8000
```
