# import os

# FORBIDDEN_PATTERNS = [
#     "OpenAI(",
#     "ChatOpenAI(",
#     "AzureOpenAI(",
#     "google.generativeai",
# ]

# def validate_agent_code(agent_dir: str):

#     for root, _, files in os.walk(agent_dir):
#         for file in files:
#             if file.endswith(".py"):
#                 with open(os.path.join(root, file), "r") as f:
#                     content = f.read()
#                     for pattern in FORBIDDEN_PATTERNS:
#                         if pattern in content:
#                             raise RuntimeError(
#                                 f"Forbidden provider usage detected: {pattern}"
#                             )


import ast
import os
from typing import List

class AgentValidator:
    # Patterns that suggest the developer is bypassing the ModelRouter
    FORBIDDEN_IMPORTS = [
        "openai", 
        "anthropic", 
        "google.generativeai", 
        "boto3", # Blocking direct Bedrock access
        "azure.ai.contentsafety"
    ]

    # Patterns that suggest hardcoded keys
    FORBIDDEN_STRINGS = [
        "sk-",          # OpenAI
        "xai-",         # xAI
        "AIza",         # Google Cloud
        "ghp_",         # GitHub
    ]

    def __init__(self, file_path: str):
        self.file_path = file_path
        with open(file_path, "r") as f:
            self.content = f.read()
            self.tree = ast.parse(self.content)

    def validate(self):
        """Runs all checks. Raises RuntimeError if any fail."""
        self._check_imports()
        self._check_hardcoded_keys()
        self._check_context_usage()
        return True

    def _check_imports(self):
        """Ensures they aren't importing raw provider SDKs."""
        for node in ast.walk(self.tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name in self.FORBIDDEN_IMPORTS:
                        raise RuntimeError(f"❌ Forbidden import '{alias.name}' detected. Use 'platform_sdk.context' instead.")
            elif isinstance(node, ast.ImportFrom):
                if node.module and any(p in node.module for p in self.FORBIDDEN_IMPORTS):
                    raise RuntimeError(f"❌ Forbidden import from '{node.module}'. Use the provided ModelRouter.")

    def _check_hardcoded_keys(self):
        """Scans for strings that look like API keys."""
        for pattern in self.FORBIDDEN_STRINGS:
            if pattern in self.content:
                raise RuntimeError(f"❌ Security Risk: Potential hardcoded API key or secret detected ({pattern}).")

    def _check_context_usage(self):
        """
        Advanced Check: Encourages the use of the Platform LLM.
        We look for 'get_llm' to ensure they are at least aware of it.
        """
        if "get_llm" not in self.content and ("LangGraph" in self.content or "langchain" in self.content):
            print("⚠️ Warning: We detected LangChain/LangGraph usage without 'get_llm'. "
                  "Ensure you are not hardcoding provider credentials.")

# Usage in your SDK
def validate_mcp_agent(file_path: str):
    validator = AgentValidator(file_path)
    return validator.validate()