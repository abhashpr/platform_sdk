import ast
import re
import json
from .client import PlatformClient

def extract_ui_hints_from_ast(file_path: str) -> dict:
    """
    Walks the AST of the agent file to find UI_HINTs in docstrings.
    """
    with open(file_path, "r", encoding="utf-8") as f:
        tree = ast.parse(f.read())

    found_hints = {}

    # 1. Check Module-level docstring
    module_doc = ast.get_docstring(tree)
    if module_doc:
        hint = _parse_hint_from_doc(module_doc)
        if hint:
            found_hints.update(hint)

    # 2. Check Function-level docstrings (Tools)
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            doc = ast.get_docstring(node)
            if doc:
                hint = _parse_hint_from_doc(doc)
                if hint:
                    # We can key hints by tool name if needed
                    found_hints.update(hint)

    return found_hints

def _parse_hint_from_doc(docstring: str) -> dict:
    """Helper to find and parse 'UI_HINT: {JSON}' within a docstring."""
    # Look for the UI_HINT marker
    match = re.search(r'UI_HINT:\s*({.*})', docstring, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            return {}
    return None


async def register_mcp_agent(file_path: str, name: str, category: str):
    """
    Registrar using AST for metadata extraction.
    """
    client = PlatformClient()
    
    with open(file_path, "r", encoding="utf-8") as f:
        content = f.read()

    # Extract UI Metadata using the robust AST walker
    ui_metadata = extract_ui_hints_from_ast(file_path)

    payload = {
        "name": name,
        "category": category,
        "source": "mcp_server",
        "file_content": content,
        "ui_metadata": ui_metadata,
        "config": {
            "command": "python",
            "args": [file_path]
        }
    }

    return client.post("/api/catalog/register", json=payload)