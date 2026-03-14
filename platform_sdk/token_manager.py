# platform_sdk/token_manager.py
"""
Token Manager for the Platform SDK.

Handles secure storage and automatic refresh of Cognito tokens.
Tokens are stored in ~/.de_platform/config (JSON format).

Token Hierarchy:
1. PLATFORM_AGENT_KEY (env) - Long-lived, for production agents
2. PLATFORM_API_TOKEN (env) - Manual token override
3. Stored tokens (~/.de_platform/config) - Auto-refreshed from refresh_token

Usage:
    from platform_sdk.token_manager import get_valid_token, get_auth_headers

    # Get a valid token (auto-refreshes if needed)
    token = get_valid_token()

    # Get ready-to-use headers for API calls
    headers = get_auth_headers()
"""

import base64
import json
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError
from urllib.parse import urlencode


# Config file location
CONFIG_DIR = Path.home() / ".de_platform"
CONFIG_FILE = CONFIG_DIR / "config"

# Buffer time before expiration to trigger refresh (5 minutes)
EXPIRY_BUFFER_SECONDS = 300


@dataclass
class TokenSet:
    """A set of Cognito tokens with metadata."""
    id_token: str
    refresh_token: str
    access_token: Optional[str] = None
    expires_at: Optional[int] = None  # Unix timestamp
    platform_url: Optional[str] = None
    user_pool_id: Optional[str] = None
    client_id: Optional[str] = None


def _ensure_config_dir():
    """Create the config directory if it doesn't exist."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    # Set restrictive permissions on Unix
    if os.name != "nt":
        CONFIG_DIR.chmod(0o700)


def _decode_jwt_payload(token: str) -> dict:
    """
    Decode the payload of a JWT without verification.
    
    We only use this for reading expiration time, not for security.
    """
    try:
        # JWT format: header.payload.signature
        parts = token.split(".")
        if len(parts) != 3:
            return {}
        
        # Decode payload (base64url)
        payload_b64 = parts[1]
        # Add padding if needed
        padding = 4 - len(payload_b64) % 4
        if padding != 4:
            payload_b64 += "=" * padding
        
        payload_bytes = base64.urlsafe_b64decode(payload_b64)
        return json.loads(payload_bytes)
    except Exception:
        return {}


def _get_token_expiry(token: str) -> Optional[int]:
    """Extract the expiration timestamp from a JWT."""
    payload = _decode_jwt_payload(token)
    return payload.get("exp")


def _is_token_expired(token: str, buffer_seconds: int = EXPIRY_BUFFER_SECONDS) -> bool:
    """
    Check if a token is expired or will expire soon.
    
    Args:
        token: The JWT token to check
        buffer_seconds: Refresh this many seconds before actual expiry
    
    Returns:
        True if token is expired or will expire within buffer_seconds
    """
    exp = _get_token_expiry(token)
    if exp is None:
        # Can't determine expiry, assume expired to be safe
        return True
    
    return time.time() >= (exp - buffer_seconds)


def save_tokens(
    id_token: str,
    refresh_token: str,
    platform_url: str,
    access_token: Optional[str] = None,
    user_pool_id: Optional[str] = None,
    client_id: Optional[str] = None,
) -> bool:
    """
    Save tokens to the config file.
    
    Args:
        id_token: Cognito ID token (used for API auth)
        refresh_token: Cognito refresh token (used to get new ID tokens)
        platform_url: Base URL of the platform
        access_token: Optional access token
        user_pool_id: Cognito User Pool ID (needed for refresh)
        client_id: Cognito App Client ID (needed for refresh)
    
    Returns:
        True if saved successfully
    """
    _ensure_config_dir()
    
    expires_at = _get_token_expiry(id_token)
    
    config = {
        "id_token": id_token,
        "refresh_token": refresh_token,
        "access_token": access_token,
        "expires_at": expires_at,
        "platform_url": platform_url,
        "user_pool_id": user_pool_id,
        "client_id": client_id,
        "saved_at": int(time.time()),
    }
    
    try:
        CONFIG_FILE.write_text(json.dumps(config, indent=2), encoding="utf-8")
        # Set restrictive permissions on Unix
        if os.name != "nt":
            CONFIG_FILE.chmod(0o600)
        return True
    except Exception:
        return False


def load_tokens() -> Optional[TokenSet]:
    """
    Load tokens from the config file.
    
    Returns:
        TokenSet if found, None otherwise
    """
    if not CONFIG_FILE.exists():
        return None
    
    try:
        config = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
        return TokenSet(
            id_token=config.get("id_token", ""),
            refresh_token=config.get("refresh_token", ""),
            access_token=config.get("access_token"),
            expires_at=config.get("expires_at"),
            platform_url=config.get("platform_url"),
            user_pool_id=config.get("user_pool_id"),
            client_id=config.get("client_id"),
        )
    except Exception:
        return None


def clear_tokens() -> bool:
    """
    Remove stored tokens (logout).
    
    Returns:
        True if cleared successfully
    """
    try:
        if CONFIG_FILE.exists():
            CONFIG_FILE.unlink()
        return True
    except Exception:
        return False


def refresh_id_token(
    refresh_token: str,
    user_pool_id: str,
    client_id: str,
) -> Optional[dict]:
    """
    Use a refresh token to get a new ID token from Cognito.
    
    Args:
        refresh_token: The Cognito refresh token
        user_pool_id: Cognito User Pool ID (e.g., "ap-south-1_XXXXXXXXX")
        client_id: Cognito App Client ID
    
    Returns:
        Dict with new tokens if successful, None otherwise
    """
    # Extract region from user pool ID
    try:
        region = user_pool_id.split("_")[0]
    except Exception:
        return None
    
    cognito_url = f"https://cognito-idp.{region}.amazonaws.com/"
    
    # Cognito InitiateAuth request
    payload = json.dumps({
        "AuthFlow": "REFRESH_TOKEN_AUTH",
        "ClientId": client_id,
        "AuthParameters": {
            "REFRESH_TOKEN": refresh_token,
        },
    }).encode("utf-8")
    
    headers = {
        "Content-Type": "application/x-amz-json-1.1",
        "X-Amz-Target": "AWSCognitoIdentityProviderService.InitiateAuth",
    }
    
    try:
        req = Request(cognito_url, data=payload, headers=headers, method="POST")
        with urlopen(req, timeout=30) as response:
            result = json.loads(response.read().decode("utf-8"))
            
            auth_result = result.get("AuthenticationResult", {})
            return {
                "id_token": auth_result.get("IdToken"),
                "access_token": auth_result.get("AccessToken"),
                # Note: Cognito doesn't return a new refresh token on refresh
                "expires_in": auth_result.get("ExpiresIn", 3600),
            }
    except (URLError, HTTPError) as e:
        print(f"[TokenManager] Refresh failed: {e}")
        return None
    except Exception as e:
        print(f"[TokenManager] Unexpected error during refresh: {e}")
        return None


def get_valid_token(
    platform_url: Optional[str] = None,
    user_pool_id: Optional[str] = None,
    client_id: Optional[str] = None,
    on_refresh: Optional[callable] = None,
) -> Optional[str]:
    """
    Get a valid ID token, refreshing if necessary.
    
    This is the main entry point for agents to get authentication.
    
    Priority:
    1. PLATFORM_AGENT_KEY env var (returns None, use get_auth_headers instead)
    2. PLATFORM_API_TOKEN env var (used as-is, no refresh)
    3. Stored tokens with auto-refresh
    
    Args:
        platform_url: Platform URL (falls back to stored or env)
        user_pool_id: Cognito User Pool ID (falls back to stored or env)
        client_id: Cognito App Client ID (falls back to stored or env)
        on_refresh: Optional callback when token is refreshed
    
    Returns:
        A valid ID token, or None if not available
    """
    # Priority 1: Agent key (handled separately via get_auth_headers)
    if os.getenv("PLATFORM_AGENT_KEY"):
        return None  # Caller should use get_auth_headers()
    
    # Priority 2: Manual token override
    manual_token = os.getenv("PLATFORM_API_TOKEN")
    if manual_token:
        # Check if it's expired
        if not _is_token_expired(manual_token):
            return manual_token
        # Manual token is expired, fall through to try stored tokens
    
    # Priority 3: Stored tokens with auto-refresh
    tokens = load_tokens()
    if not tokens or not tokens.id_token:
        return manual_token if manual_token else None
    
    # Check if stored token is still valid
    if not _is_token_expired(tokens.id_token):
        return tokens.id_token
    
    # Token expired, try to refresh
    pool_id = user_pool_id or tokens.user_pool_id or os.getenv("COGNITO_USER_POOL_ID")
    app_client_id = client_id or tokens.client_id or os.getenv("COGNITO_APP_CLIENT_ID")
    url = platform_url or tokens.platform_url or os.getenv("PLATFORM_URL")
    
    if not tokens.refresh_token or not pool_id or not app_client_id:
        # Can't refresh without these
        return None
    
    print("[TokenManager] ID token expired, refreshing...")
    new_tokens = refresh_id_token(tokens.refresh_token, pool_id, app_client_id)
    
    if new_tokens and new_tokens.get("id_token"):
        # Save the new tokens
        save_tokens(
            id_token=new_tokens["id_token"],
            refresh_token=tokens.refresh_token,  # Keep the same refresh token
            platform_url=url,
            access_token=new_tokens.get("access_token"),
            user_pool_id=pool_id,
            client_id=app_client_id,
        )
        print("[TokenManager] Token refreshed successfully")
        
        if on_refresh:
            on_refresh(new_tokens["id_token"])
        
        return new_tokens["id_token"]
    
    # Refresh failed
    print("[TokenManager] Token refresh failed, please run 'platform auth' again")
    return None


def get_auth_headers(
    platform_url: Optional[str] = None,
    user_pool_id: Optional[str] = None,
    client_id: Optional[str] = None,
) -> dict:
    """
    Get authentication headers for platform API calls.
    
    This handles all auth methods:
    - Platform Agent Key (X-DE-AGENT-KEY header)
    - Cognito ID Token (Authorization: Bearer header)
    
    Args:
        platform_url: Platform URL (for token refresh)
        user_pool_id: Cognito User Pool ID (for token refresh)
        client_id: Cognito App Client ID (for token refresh)
    
    Returns:
        Dict of headers ready for use in HTTP requests
    
    Example:
        headers = get_auth_headers()
        response = httpx.post(url, headers=headers, json=payload)
    """
    headers = {"Content-Type": "application/json"}
    
    # Priority 1: Platform Agent Key
    agent_key = os.getenv("PLATFORM_AGENT_KEY")
    if agent_key:
        headers["X-DE-AGENT-KEY"] = agent_key
        return headers
    
    # Priority 2 & 3: ID Token (manual or auto-refreshed)
    token = get_valid_token(
        platform_url=platform_url,
        user_pool_id=user_pool_id,
        client_id=client_id,
    )
    
    if token:
        headers["Authorization"] = f"Bearer {token}"
    
    return headers


def get_token_status() -> dict:
    """
    Get the current token status for display.
    
    Returns:
        Dict with status information
    """
    result = {
        "auth_method": None,
        "expires_at": None,
        "expires_in_seconds": None,
        "needs_refresh": False,
        "platform_url": None,
    }
    
    # Check agent key first
    if os.getenv("PLATFORM_AGENT_KEY"):
        result["auth_method"] = "agent_key"
        result["expires_at"] = "never"
        return result
    
    # Check manual token
    manual_token = os.getenv("PLATFORM_API_TOKEN")
    if manual_token:
        exp = _get_token_expiry(manual_token)
        result["auth_method"] = "env_token"
        if exp:
            result["expires_at"] = exp
            result["expires_in_seconds"] = max(0, exp - int(time.time()))
            result["needs_refresh"] = result["expires_in_seconds"] < EXPIRY_BUFFER_SECONDS
        return result
    
    # Check stored tokens
    tokens = load_tokens()
    if tokens and tokens.id_token:
        exp = _get_token_expiry(tokens.id_token)
        result["auth_method"] = "stored_token"
        result["platform_url"] = tokens.platform_url
        if exp:
            result["expires_at"] = exp
            result["expires_in_seconds"] = max(0, exp - int(time.time()))
            result["needs_refresh"] = result["expires_in_seconds"] < EXPIRY_BUFFER_SECONDS
        
        # Check if refresh token is available
        result["can_auto_refresh"] = bool(
            tokens.refresh_token and tokens.user_pool_id and tokens.client_id
        )
        return result
    
    result["auth_method"] = None
    return result
