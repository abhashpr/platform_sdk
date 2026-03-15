import os
import requests

# Import token manager for auto-refresh support
try:
    from .token_manager import get_valid_token
    _HAS_TOKEN_MANAGER = True
except ImportError:
    _HAS_TOKEN_MANAGER = False


class PlatformClient:
    
    def __init__(self):
        self.base_url = os.getenv("PLATFORM_BASE_URL")
        self.principal_b64 = os.getenv("PLATFORM_API_PRINCIPAL")
        self.principal_name = os.getenv("PLATFORM_API_PRINCIPAL_NAME")
        
        # Token resolution order:
        # 1. get_valid_token() - reads from ~/.de_platform/config with auto-refresh
        # 2. PLATFORM_API_TOKEN env var (fallback)
        self.token = None
        if _HAS_TOKEN_MANAGER:
            try:
                self.token = get_valid_token()
            except Exception:
                pass
        
        if not self.token:
            self.token = os.getenv("PLATFORM_API_TOKEN")
        
        if not self.base_url or not self.token:
            raise RuntimeError(
                "Set PLATFORM_BASE_URL and PLATFORM_API_TOKEN, or run 'platform auth'."
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

    def post_multipart(
        self,
        path: str,
        fields: dict,
        file_field: str,
        file_name: str,
        file_bytes: bytes,
        content_type: str = "application/octet-stream",
    ):
        """POST multipart/form-data (used by `platform publish`)."""
        headers = {"Authorization": f"Bearer {self.token}"}
        if self.principal_b64 and self.principal_name:
            headers["X-MS-CLIENT-PRINCIPAL"] = self.principal_b64
            headers["X-MS-CLIENT-PRINCIPAL-NAME"] = self.principal_name
        else:
            try:
                import base64, json as _json

                role = os.getenv("DEFAULT_APP_ROLE", "user")
                principal = {"claims": [{"typ": "roles", "val": role}]}
                encoded = base64.b64encode(_json.dumps(principal).encode()).decode()
                headers["X-MS-CLIENT-PRINCIPAL"] = encoded
                headers["X-MS-CLIENT-PRINCIPAL-NAME"] = (
                    os.getenv("PLATFORM_API_PRINCIPAL_NAME") or self.token
                )
            except Exception:
                pass

        files_payload = {k: (None, v) for k, v in fields.items()}
        files_payload[file_field] = (file_name, file_bytes, content_type)

        response = requests.post(
            f"{self.base_url}{path}",
            headers=headers,
            files=files_payload,
        )
        response.raise_for_status()
        return response.json()
        