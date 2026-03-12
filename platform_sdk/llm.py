# llm.py

import os
import requests
# from langchain.llms.base import LLM
from langchain_core.language_models.llms import LLM

class RouterLLM(LLM):

    def __init__(self, model=None, deployment=None, context=None):
        self.model = model
        self.context = context
        self.deployment = deployment
        
        if not self.model and not self.deployment:
            raise ValueError("Provide either model or deployment for RouterLLM.")

    @property
    def _llm_type(self):
        return "platform_router"

    def _call(self, prompt, stop=None):

        base_url = os.getenv("PLATFORM_BASE_URL")
        token = os.getenv("PLATFORM_API_TOKEN")

        if not base_url or not token:
            raise RuntimeError(
                "Remote Dev Mode required. "
                "Set PLATFORM_BASE_URL and PLATFORM_API_TOKEN."
            )
            
        payload = {
            "prompt": prompt,
            "context": self.context.to_dict() if self.context else {}
        }

        if self.model:
            payload["model"] = self.model
            
        if self.deployment:
            payload["deployment"] = self.deployment # Note: deployment is optional and may be used by certain providers like Azure
        
        response = requests.post(
            f"{base_url}/api/router/dev-invoke",
            headers={"Authorization": f"Bearer {token}"},
            json=payload,
            timeout=60,
        )

        response.raise_for_status()
        return response.json()["output"]

def router_llm(model: str = None, 
               deployment: str = None, 
               context = None):
    return RouterLLM(model=model, deployment=deployment, context=context)