import click
from platform_sdk.runtime import run_local
from platform_sdk.publisher import publish
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
@click.option("--name", required=True)
@click.option("--module", required=True)
@click.option("--class-name", required=True)
@click.option("--model", required=True)
def publish_agent(name, module, class_name, model):
    """Register code agent with platform."""
    from platform_sdk.publisher import publish

    response = publish(module, class_name, name, model)
    print("Registered:", response)

 
