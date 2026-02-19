import os

FORBIDDEN_PATTERNS = [
    "OpenAI(",
    "ChatOpenAI(",
    "AzureOpenAI(",
    "google.generativeai",
]

def validate_agent_code(agent_dir: str):

    for root, _, files in os.walk(agent_dir):
        for file in files:
            if file.endswith(".py"):
                with open(os.path.join(root, file), "r") as f:
                    content = f.read()
                    for pattern in FORBIDDEN_PATTERNS:
                        if pattern in content:
                            raise RuntimeError(
                                f"Forbidden provider usage detected: {pattern}"
                            )
