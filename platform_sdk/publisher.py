from .client import PlatformClient


def publish(module: str, class_name: str, name: str, model: str):

    client = PlatformClient()

    payload = {
        "name": name,
        "module": module,
        "class_name": class_name,
        "model": model,
    }

    return client.post(
        "/api/code-agents/register",
        json=payload,
    )
