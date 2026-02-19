# agent.py

from abc import ABC, abstractmethod

class BaseAgent(ABC):

    @abstractmethod
    def build(self, context):
        """Construct chains, tools, memory, etc."""
        pass

    @abstractmethod
    def run(self, input_data, context):
        """Execute the agent."""
        pass
