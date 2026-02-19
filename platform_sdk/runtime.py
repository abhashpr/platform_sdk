import importlib.util
import sys
from .context import ExecutionContext

def run_local(agent_file: str, input_data: str):

    spec = importlib.util.spec_from_file_location("agent_module", agent_file)
    module = importlib.util.module_from_spec(spec)
    sys.modules["agent_module"] = module
    spec.loader.exec_module(module)

    agent_class = getattr(module, "Agent")
    agent = agent_class()

    context = ExecutionContext(user_id="local_dev")

    return agent.run(input_data, context)
