# llm.py

import os
import requests
# from langchain.llms.base import LLM
from langchain_core.language_models.llms import LLM

class RouterLLM(LLM):

    def __init__(self, model, context=None):
        self.model = model
        self.context = context

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

        response = requests.post(
            f"{base_url}/api/router/dev-invoke",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "model": self.model,
                "prompt": prompt,
                "context": vars(self.context) if self.context else {}
            },
            timeout=60,
        )

        response.raise_for_status()
        return response.json()["output"]

def router_llm(model: str, context = None):
    return RouterLLM(model=model, context=context)