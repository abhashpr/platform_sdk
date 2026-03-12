# import uuid

# class ExecutionContext:
    
#     def __init__(self, run_id = None, user_id = None, agent_id = None, source = "sdk"):
#         self.run_id = run_id or str(uuid.uuid4())
#         self.user_id = user_id
#         self.agent_id = agent_id
#         self.source = source
        
#     def to_dict(self):
#         return {
#             "run_id": self.run_id,
#             "user_id": self.user_id,
#             "agent_id": self.agent_id,
#             "source": self.source
#         }


# platform_sdk/context.py
from .llm import get_llm

class AgentContext:
    @staticmethod
    def get_llm(deployment="default", model=None):
        """
        The official way for DE agents to access AI.
        Usage: llm = context.get_llm(deployment='smart')
        """
        return get_llm(model=model, deployment=deployment)

# Global alias for convenience
context = AgentContext()