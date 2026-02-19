import os
import requests

class PlatformClient:
    
    def __init__(self):
        self.base_url = os.getenv("PLATFORM_BASE_URL")
        self.token = os.getenv("PLATFORM_API_TOKEN")
        self.principal_b64 = os.getenv("PLATFORM_API_PRINCIPAL")
        self.principal_name = os.getenv("PLATFORM_API_PRINCIPAL_NAME")

        if not self.base_url or not self.token:
            raise RuntimeError(
                "Set PLATFORM_BASE_URL and PLATFORM_API_TOKEN."
            )

    def post(self, path, json=None, files=None):
        headers = {"Authorization": f"Bearer {self.token}"}

        # If the platform expects Azure-like principal headers, allow providing
        # them via env vars or emulate them in dev mode using the token as name.
        if self.principal_b64 and self.principal_name:
            headers["X-MS-CLIENT-PRINCIPAL"] = self.principal_b64
            headers["X-MS-CLIENT-PRINCIPAL-NAME"] = self.principal_name
        else:
            # Dev convenience: emulate principal header if not explicitly set.
            # Use token value as name and DEFAULT_APP_ROLE as role.
            try:
                import base64, os, json as _json

                role = os.getenv("DEFAULT_APP_ROLE", "user")
                principal = {"claims": [{"typ": "roles", "val": role}]}
                encoded = base64.b64encode(_json.dumps(principal).encode("utf-8")).decode(
                    "utf-8"
                )
                headers["X-MS-CLIENT-PRINCIPAL"] = encoded
                headers["X-MS-CLIENT-PRINCIPAL-NAME"] = os.getenv("PLATFORM_API_PRINCIPAL_NAME") or self.token
            except Exception:
                pass

        response = requests.post(
            f"{self.base_url}{path}",
            headers=headers,
            json=json,
            files=files,
        )
        response.raise_for_status()
        return response.json()
        