import click
from platform_sdk.runtime import run_local
from platform_sdk.publisher import publish, generate_agent_config
from platform_sdk.validator import validate_agent_code

@click.group()
def cli():
    pass

@cli.command()
@click.option("--input", required=True)
@click.option("--file", required=True)
def run(input, file):
    """Run agent locally (remote LLM)."""
    output = run_local(file, input)
    print("Agent Output:")
    print(output)

@cli.command("publish-agent")
@click.option("--name", required=True, help="Human-readable agent name")
@click.option("--module", required=True, help="Python module path (e.g., code_agents.my_agent)")
@click.option("--class-name", required=True, help="Agent class name")
@click.option("--model", default="default", help="Model name or 'default' for env-based resolution")
@click.option("--description", default="", help="Agent description")
@click.option("--temperature", default=0.2, type=float, help="Default temperature")
@click.option("--max-tokens", default=2000, type=int, help="Default max tokens")
def publish_agent(name, module, class_name, model, description, temperature, max_tokens):
    """Generate agent config for manual registration.
    
    Agents are now registered via configs/agents.yaml instead of the API.
    This command generates the YAML snippet to add to the config file.
    
    Example:
        platform-sdk publish-agent \\
            --name "My Research Agent" \\
            --module code_agents.research \\
            --class-name ResearchAgent \\
            --model gemini-2.5-flash
    """
    result = publish(
        module=module,
        class_name=class_name,
        name=name,
        model=model,
        description=description,
        temperature=temperature,
        max_tokens=max_tokens,
    )
    print(result["instructions"])


@cli.command("generate-foundry-config")
@click.option("--name", required=True, help="Human-readable agent name")
@click.option("--agent-id", required=True, help="Unique agent ID (snake_case)")
@click.option("--description", default="", help="Agent description")
@click.option("--temperature", default=0.2, type=float, help="Default temperature")
@click.option("--max-tokens", default=2000, type=int, help="Default max tokens")
def generate_foundry_config(name, agent_id, description, temperature, max_tokens):
    """Generate config for Azure/Foundry deployment.
    
    For Foundry deployments, the model is resolved from environment variables
    at runtime. This allows switching deployments without code changes.
    
    Example:
        platform-sdk generate-foundry-config \\
            --name "Foundry SQL Agent" \\
            --agent-id foundry_sql_agent
    """
    env_var = f"DE_MODEL_{agent_id.upper()}"
    
    config = f"""  {agent_id}:
    name: {name}
    source: foundry
    description: {description}
    model: ${{{env_var}:-${{AZURE_OPENAI_DEPLOYMENT}}}}
    system_prompt: |
      # Add your system prompt here
    temperature: {temperature}
    max_tokens: {max_tokens}"""
    
    print(f"""
=== Foundry Agent Configuration ===

Add the following to configs/agents.yaml under 'agents:':

{config}

Required environment variables for Azure OpenAI:
  AZURE_OPENAI_ENDPOINT=https://your-resource.openai.azure.com
  AZURE_OPENAI_API_KEY=your-api-key
  AZURE_OPENAI_DEPLOYMENT=your-deployment-name

Optional per-agent model override:
  {env_var}=specific-deployment-name

Required environment variables for Azure AI Foundry:
  AZURE_FOUNDRY_ENDPOINT=https://your-foundry-endpoint
  AZURE_FOUNDRY_API_KEY=your-api-key
  AZURE_FOUNDRY_DEPLOYMENT=your-deployment-name

Set LLM_PROVIDER to switch providers:
  LLM_PROVIDER=azure_openai      # Azure OpenAI Service
  LLM_PROVIDER=azure_foundry     # Azure AI Foundry
  LLM_PROVIDER=google_gemini     # Google Gemini (supports model override)

Then restart the backend to load the new agent.
""")

 
