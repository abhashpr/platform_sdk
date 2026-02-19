import uuid

class ExecutionContext:
    
    def __init__(self, run_id = None, user_id = None, agent_id = None, source = "sdk"):
        self.run_id = run_id or str(uuid.uuid4())
        self.user_id = user_id
        self.agent_id = agent_id
        self.source = source
        
    def to_dict(self):
        return {
            "run_id": self.run_id,
            "user_id": self.user_id,
            "agent_id": self.agent_id,
            "source": self.source
        }