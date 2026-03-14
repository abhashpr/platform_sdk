"""Remote Agent Context for Federated Mode.

This module provides a RemoteAgentContext that routes LLM calls and logging
through the DE platform's proxy endpoints instead of using local services.

Usage:
    from platform_sdk import RemoteAgentContext
    
    # Initialize with your agent key (received during registration)
    context = RemoteAgentContext(
        platform_url="https://your-de-platform.com",
        agent_key="your-agent-key",
    )
    
    # Get a governed LLM (routes through DE's ModelRouter)
    llm = context.get_llm(model="gpt-4")
    
    # Make LLM calls - all usage is logged by the platform
    response = llm.invoke("Hello, world!")
"""

import os
import uuid
from typing import Any, Dict, List, Optional

try:
    import httpx
except ImportError:
    httpx = None

from langchain_core.language_models.llms import LLM
from langchain_core.callbacks.manager import CallbackManagerForLLMRun
from pydantic import ConfigDict, PrivateAttr


class RemoteRouterLLM(LLM):
    """LangChain-compatible LLM that routes through the DE platform proxy.
    
    This LLM makes calls to /api/router/dev-invoke on the DE platform.
    Uses deployment names ("default", "smart", "fast") instead of model names.
    """
    deployment: str = "default"  # Use deployment tiers, not model names
    temperature: float = 0.2
    max_tokens: int = 2000
    
    # Platform connection (set via _configure) - use PrivateAttr for Pydantic v2
    _platform_url: str = PrivateAttr(default="")
    _agent_key: str = PrivateAttr(default="")
    _agent_id: str = PrivateAttr(default="")
    _run_id: Optional[str] = PrivateAttr(default=None)
    
    model_config = ConfigDict(extra="allow")

    @property
    def _llm_type(self) -> str:
        return "remote_platform_router"
    
    def _configure(
        self,
        platform_url: str,
        agent_key: str,
        agent_id: str = "",
        run_id: Optional[str] = None,
    ):
        """Configure the LLM with platform connection details."""
        self._platform_url = platform_url.rstrip("/")
        self._agent_key = agent_key
        self._agent_id = agent_id
        self._run_id = run_id

    def _call(
        self,
        prompt: str,
        stop: Optional[List[str]] = None,
        run_manager: Optional[CallbackManagerForLLMRun] = None,
        **kwargs: Any,
    ) -> str:
        """Make an LLM call through the DE platform proxy."""
        if httpx is None:
            raise ImportError("httpx is required for remote mode. Install with: pip install httpx")
        
        if not self._platform_url or not self._agent_key:
            raise RuntimeError(
                "RemoteRouterLLM not configured. Use RemoteAgentContext.get_llm() instead."
            )
        
        # Use the dev-invoke endpoint (same as platform_sdk.llm.RouterLLM)
        payload = {
            "prompt": prompt,
            "model": None,  # Let the backend resolve from deployment
            "deployment": self.deployment,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "metadata": {
                "run_id": self._run_id or str(uuid.uuid4()),
                "agent_id": self._agent_id,
            }
        }
        
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self._agent_key}",
        }
        
        url = f"{self._platform_url}/api/router/dev-invoke"
        
        with httpx.Client(timeout=120.0) as client:
            response = client.post(url, json=payload, headers=headers)
            
            if response.status_code == 401:
                raise RuntimeError("Invalid agent key. Check your agent registration.")
            elif response.status_code == 400:
                error_detail = response.json().get("detail", "Bad request")
                raise RuntimeError(f"Proxy error: {error_detail}")
            elif response.status_code != 200:
                raise RuntimeError(f"Proxy error ({response.status_code}): {response.text}")
            
            data = response.json()
            # dev-invoke returns {"output": "...", "model": "...", "usage": {...}}
            return data.get("output", "")


class RemoteAgentContext:
    """Context for agents running in Federated/Remote mode.
    
    This context routes all LLM calls through the DE platform's proxy endpoints,
    allowing the platform to:
    - Log all usage
    - Enforce model allow-lists
    - Track costs per agent
    
    Example:
        context = RemoteAgentContext(
            platform_url="https://de.example.com",
            agent_key="sk-xxxxx",
        )
        
        llm = context.get_llm(model="gpt-4")
        result = llm.invoke("Summarize this document")
    """
    
    def __init__(
        self,
        platform_url: Optional[str] = None,
        agent_key: Optional[str] = None,
        agent_id: Optional[str] = None,
    ):
        """Initialize the remote context.
        
        Args:
            platform_url: Base URL of the DE platform (e.g., https://de.example.com)
            agent_key: The X-DE-AGENT-KEY received during agent registration
            agent_id: The agent's ID in the platform registry
        """
        self.platform_url = (
            platform_url 
            or os.getenv("DE_PLATFORM_URL") 
            or os.getenv("PLATFORM_BASE_URL")
        )
        self.agent_key = (
            agent_key 
            or os.getenv("DE_AGENT_KEY") 
            or os.getenv("X_DE_AGENT_KEY")
        )
        self.agent_id = agent_id or os.getenv("DE_AGENT_ID", "")
        self._current_run_id: Optional[str] = None
        
        if not self.platform_url:
            raise ValueError(
                "platform_url is required. Set DE_PLATFORM_URL env var or pass it directly."
            )
        if not self.agent_key:
            raise ValueError(
                "agent_key is required. Set DE_AGENT_KEY env var or pass it directly."
            )
    
    def start_run(self, run_id: Optional[str] = None) -> str:
        """Start a new run (for tracing/logging purposes)."""
        self._current_run_id = run_id or str(uuid.uuid4())
        return self._current_run_id
    
    def get_llm(
        self,
        deployment: str = "default",
        temperature: float = 0.2,
        max_tokens: int = 2000,
        **kwargs,
    ) -> RemoteRouterLLM:
        """Get a governed LLM that routes through the DE platform proxy.
        
        Args:
            deployment: Deployment tier ("default", "smart", "fast")
            temperature: Sampling temperature
            max_tokens: Maximum tokens to generate
            
        Returns:
            A LangChain-compatible LLM instance
        """
        llm = RemoteRouterLLM(
            deployment=deployment,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        llm._configure(
            platform_url=self.platform_url,
            agent_key=self.agent_key,
            agent_id=self.agent_id,
            run_id=self._current_run_id,
        )
        return llm
    
    def list_models(self) -> List[str]:
        """List available models from the platform."""
        if httpx is None:
            raise ImportError("httpx is required for remote mode.")
        
        url = f"{self.platform_url.rstrip('/')}/api/proxy/models"
        headers = {"X-DE-AGENT-KEY": self.agent_key}
        
        with httpx.Client(timeout=30.0) as client:
            response = client.get(url, headers=headers)
            if response.status_code != 200:
                raise RuntimeError(f"Failed to list models: {response.text}")
            return response.json().get("models", [])
    
    def log_event(self, event_type: str, data: Dict[str, Any]) -> None:
        """Log a custom event to the platform (for debugging/auditing)."""
        # Future: implement /api/proxy/log endpoint
        pass


def get_remote_context(
    platform_url: Optional[str] = None,
    agent_key: Optional[str] = None,
) -> RemoteAgentContext:
    """Factory function to create a RemoteAgentContext.
    
    This is the recommended way to initialize context in federated mode.
    """
    return RemoteAgentContext(platform_url=platform_url, agent_key=agent_key)
