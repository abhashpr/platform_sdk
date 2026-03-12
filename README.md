Follow these steps in order to create a agent using this SDK.

1. Create a clean venv
2. Install the SDK locally
3. Point it to your platform (remote dev mode)
4. Build a **real LangChain agent**
5. Run it locally (calls router)
6. Then publish

I’ll give you exact commands.

---

# 1. Create sandbox + venv (Windows PowerShell)

Open PowerShell:

```powershell
mkdir agent_sandbox
cd agent_sandbox

python -m venv .venv
.\.venv\Scripts\Activate
```

Upgrade pip:

```powershell
pip install --upgrade pip
```

---

# 2. Install the SDK (local install for now)

Assuming your SDK repo is somewhere like:

```
C:\dev\platform-sdk\
```

Install in editable mode:

```powershell
pip install -e C:\dev\platform-sdk
```

Verify:

```powershell
platform --help
```

You should see CLI commands.

---

# 3. Configure Remote Dev Mode

You must point SDK to your running platform backend.

Set env vars:

```powershell
$env:PLATFORM_BASE_URL="http://localhost:5002"
$env:PLATFORM_API_TOKEN="dev-user-token"
```

(Use whatever auth token your platform expects.)

Test router connectivity:

```powershell
python -c "import os; print(os.getenv('PLATFORM_BASE_URL'))"
```

---

# 4. Create agent project

Inside sandbox:

```powershell
mkdir research_agent
cd research_agent
```

Create:

```
agent.py
requirements.txt
```

---

# 5. Example complex LangChain agent

This uses:

* router_llm
* tools
* multi-step reasoning

### `agent.py`

```python
from platform_sdk import BaseAgent, router_llm, ExecutionContext
from langchain.agents import initialize_agent, Tool
from langchain.agents.agent_types import AgentType


# ---- TOOL EXAMPLE ----
def calculator_tool(x: str):
    try:
        return str(eval(x))
    except Exception as e:
        return f"error: {e}"


class Agent(BaseAgent):

    def build(self, context):

        llm = router_llm(
            model="gemini-pro",
            context=context
        )

        tools = [
            Tool(
                name="Calculator",
                func=calculator_tool,
                description="Use for math calculations"
            )
        ]

        agent = initialize_agent(
            tools,
            llm,
            agent=AgentType.ZERO_SHOT_REACT_DESCRIPTION,
            verbose=True
        )

        return agent

    def run(self, input_data, context):
        agent = self.build(context)
        return agent.run(input_data)
```

---

# 6. requirements.txt

```txt
langchain
requests
```

Install deps:

```powershell
pip install -r requirements.txt
```

---

# 7. Run locally (remote LLM)

From inside `research_agent`:

```powershell
platform run --file agent.py --input "What is 45 * 12 and explain transformers?"
```

Expected flow:

```
Agent builds
router_llm → POST /api/router/dev-invoke
ModelRouter → Gemini
response returned
```

If everything is wired correctly, you’ll see output.

---

# 🔍 If it fails, check these first

## A. Dev router endpoint exists

Your backend must have:

```
POST /api/router/dev-invoke
```

If not implemented yet → this will fail.

---

## B. Auth token accepted

Check backend logs:

```
Authorization header received?
```

---

## C. Gemini registered in model registry

Router must know model name:

```
gemini-pro
```

Run:

```
GET /api/models
```

---

# 8. Publish to platform (Config-Based Registration)

Agents are now registered via `configs/agents.yaml` instead of API calls.
The SDK generates the YAML snippet for you to add manually.

### For Code Agents

```powershell
platform publish-agent `
    --name "Research Agent" `
    --module code_agents.research_agent `
    --class-name ResearchAgent `
    --model gemini-2.5-flash `
    --description "Performs research tasks"
```

Output:
```
=== Agent Registration ===

Add the following to configs/agents.yaml under 'agents:':

  research_agent:
    name: Research Agent
    source: code
    module: code_agents.research_agent
    class_name: ResearchAgent
    description: Performs research tasks
    model: ${DE_MODEL_RESEARCH_AGENT:-gemini-2.5-flash}
    temperature: 0.2
    max_tokens: 2000

To override the model at runtime, set:
  DE_MODEL_RESEARCH_AGENT=your-model-or-deployment
```

### For Azure/Foundry Deployments

```powershell
platform generate-foundry-config `
    --name "Foundry SQL Agent" `
    --agent-id foundry_sql_agent `
    --description "SQL generation using Azure OpenAI"
```

Output includes required environment variables for Azure setup.

### Manual Steps

1. Copy the generated YAML to `backend/configs/agents.yaml`
2. Set required environment variables (see below)
3. Restart the backend

### Environment Variables for Deployments

```powershell
# Provider selection
$env:LLM_PROVIDER="azure_openai"  # or "azure_foundry" or "google_gemini"

# Azure OpenAI
$env:AZURE_OPENAI_ENDPOINT="https://your-resource.openai.azure.com"
$env:AZURE_OPENAI_API_KEY="your-api-key"
$env:AZURE_OPENAI_DEPLOYMENT="your-deployment-name"

# Azure AI Foundry
$env:AZURE_FOUNDRY_ENDPOINT="https://your-foundry-endpoint"
$env:AZURE_FOUNDRY_API_KEY="your-api-key"
$env:AZURE_FOUNDRY_DEPLOYMENT="your-deployment-name"

# Google Gemini
$env:GOOGLE_GEMINI_API_KEY="your-api-key"

# Per-agent model overrides
$env:DE_MODEL_RESEARCH_AGENT="gpt-4-turbo"
$env:DE_DEFAULT_MODEL="gemini-2.5-flash"
```

### Why Config-Based?

- **No DB dependencies** for agent definitions
- **Easy deployment switching** via env vars
- **Version control friendly** - config in git
- **Runtime model override** without code changes

---

# What you are validating here

This test proves:

* SDK works
* router works in dev mode
* LangChain works through router
* no credential leakage
* publish flow works

This is the moment your platform becomes real.

---

Note about console entrypoint

If you install this package locally (`pip install -e .`), the `platform` console
script is provided by the `platform_sdk.cli:cli` entry point. The CLI implementation
lives in `platform_sdk/cli.py` (not a top-level `cli.py`). If you see
`ModuleNotFoundError: No module named 'platform_sdk.cli'` ensure the package is
installed into the active virtualenv and that `platform_sdk` is importable from
that environment.

---

# 🛠 Before you run

Tell me:

### Do you already have:

1. `/api/router/dev-invoke` endpoint?
2. `/api/code-agents` endpoint?
3. Gemini working through ModelRouter?

Answer yes/no for each.

If any are missing, I’ll give you the minimal backend patch before you run the test.
