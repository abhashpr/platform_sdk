"""Agent Publisher Module.

Generates YAML configuration snippets for registering agents with the platform.
Agents are defined in configs/agents.yaml and loaded at runtime.

For Foundry/Azure deployments, model names reference environment variables
that contain the actual deployment names, API keys, and endpoints.
"""

from typing import Optional


def generate_agent_config(
    module: str,
    class_name: str,
    name: str,
    model: str = "default",
    description: str = "",
    temperature: float = 0.2,
    max_tokens: int = 2000,
    source: str = "code",
) -> str:
    """Generate YAML configuration snippet for an agent.
    
    Args:
        module: Python module path (e.g., 'code_agents.my_agent')
        class_name: Agent class name (e.g., 'MyAgent')
        name: Human-readable agent name
        model: Model name or alias. Use 'default' for env-based resolution,
               or reference env vars like '${DE_MODEL_MY_AGENT:-gemini-2.5-flash}'
        description: Agent description
        temperature: Default temperature
        max_tokens: Default max tokens
        source: Agent source type ('code', 'foundry', 'yaml')
    
    Returns:
        YAML configuration snippet to add to configs/agents.yaml
    """
    # Generate agent ID from class name (snake_case)
    agent_id = _to_snake_case(class_name)
    env_var_name = f"DE_MODEL_{agent_id.upper()}"
    
    # If model is 'default', use env var with fallback
    if model == "default":
        model_value = f"${{DE_DEFAULT_MODEL:-gemini-2.5-flash}}"
    elif not model.startswith("${"):
        # Wrap in env var for easy override
        model_value = f"${{{env_var_name}:-{model}}}"
    else:
        model_value = model
    
    if source == "code":
        config = f"""  {agent_id}:
    name: {name}
    source: code
    module: {module}
    class_name: {class_name}
    description: {description}
    model: {model_value}
    temperature: {temperature}
    max_tokens: {max_tokens}"""
    elif source == "foundry":
        config = f"""  {agent_id}:
    name: {name}
    source: foundry
    description: {description}
    model: {model_value}
    system_prompt: |
      # Add your system prompt here
    temperature: {temperature}
    max_tokens: {max_tokens}"""
    else:
        config = f"""  {agent_id}:
    name: {name}
    source: {source}
    model: {model_value}"""
    
    return config


def _to_snake_case(name: str) -> str:
    """Convert CamelCase to snake_case."""
    import re
    s1 = re.sub('(.)([A-Z][a-z]+)', r'\1_\2', name)
    return re.sub('([a-z0-9])([A-Z])', r'\1_\2', s1).lower()


def publish(
    module: str,
    class_name: str,
    name: str,
    model: str,
    description: str = "",
    temperature: float = 0.2,
    max_tokens: int = 2000,
) -> dict:
    """Generate agent configuration for manual registration.
    
    NOTE: Agents are now configured via configs/agents.yaml, not via API.
    This function generates the YAML snippet to add to the config file.
    
    Args:
        module: Python module path
        class_name: Agent class name
        name: Human-readable name
        model: Model name or 'default'
        description: Agent description
        temperature: Default temperature
        max_tokens: Default max tokens
    
    Returns:
        Dict with 'config' (YAML snippet) and 'instructions'
    """
    config = generate_agent_config(
        module=module,
        class_name=class_name,
        name=name,
        model=model,
        description=description,
        temperature=temperature,
        max_tokens=max_tokens,
        source="code",
    )
    
    agent_id = _to_snake_case(class_name)
    env_var = f"DE_MODEL_{agent_id.upper()}"
    
    return {
        "config": config,
        "agent_id": agent_id,
        "env_var": env_var,
        "instructions": f"""
=== Agent Registration ===

Add the following to configs/agents.yaml under 'agents:':

{config}

To override the model at runtime, set:
  {env_var}=your-model-or-deployment

For Azure/Foundry deployments, also ensure these are set:
  AZURE_OPENAI_ENDPOINT=https://your-resource.openai.azure.com
  AZURE_OPENAI_API_KEY=your-api-key
  AZURE_OPENAI_DEPLOYMENT=your-deployment-name

Then restart the backend to load the new agent.
""",
    }
