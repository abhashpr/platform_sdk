import os
import requests
from typing import Any, List, Optional
from langchain_core.language_models.llms import LLM
from langchain_core.callbacks.manager import CallbackManagerForLLMRun

class RouterLLM(LLM):
    """
    A LangChain-compatible LLM that routes requests to the Platform ModelRouter.
    This allows developers to use LangGraph/LangChain while the Platform
    manages the API keys, costs, and model selection.
    """
    model: Optional[str] = None
    deployment: str = "default"
    temperature: float = 0.2
    
    # Hidden attributes to avoid LangChain serialization issues
    base_url: str = ""
    token: str = ""

    @property
    def _llm_type(self) -> str:
        return "platform_router"

    def _call(
        self,
        prompt: str,
        stop: Optional[List[str]] = None,
        run_manager: Optional[CallbackManagerForLLMRun] = None,
        **kwargs: Any,
    ) -> str:
        """Internal call logic: Routes to the Lightsail API."""
        
        # Priority: Env Var > Passed Config
        url = self.base_url or os.getenv("PLATFORM_BASE_URL")
        auth_token = self.token or os.getenv("PLATFORM_API_TOKEN")

        if not url or not auth_token:
            raise RuntimeError(
                "Missing Connectivity: Set PLATFORM_BASE_URL and PLATFORM_API_TOKEN."
            )

        # Prepare the payload for the ModelRouter
        payload = {
            "prompt": prompt,
            "model": self.model,
            "deployment": self.deployment,
            "temperature": self.temperature,
            "metadata": kwargs.get("metadata", {})
        }

        # Call the dedicated 'dev-invoke' endpoint on your Lightsail instance
        response = requests.post(
            f"{url.rstrip('/')}/api/router/dev-invoke",
            headers={"Authorization": f"Bearer {auth_token}"},
            json=payload,
            timeout=60,
        )

        if response.status_code != 200:
            error_msg = response.json().get("detail", "Unknown Router Error")
            raise RuntimeError(f"ModelRouter Error ({response.status_code}): {error_msg}")

        return response.json().get("output", "")

def get_llm(model: str = None, deployment: str = "default", **kwargs):
    """Factory function for developers to easily get a governed LLM."""
    return RouterLLM(model=model, deployment=deployment, **kwargs)