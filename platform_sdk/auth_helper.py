# platform_sdk/auth_helper.py
"""
Authentication helpers for the Platform SDK CLI.

Implements a local callback flow for CLI authentication:
1. Opens the platform login page in the user's browser
2. Starts a local HTTP server to receive the token callback
3. Saves tokens to ~/.de_platform/config for auto-refresh
4. Updates the .env file with the current ID token

This is similar to how the AWS CLI and GitHub CLI handle device authentication.
"""

import http.server
import json
import os
import secrets
import socketserver
import threading
import time
import urllib.parse
import webbrowser
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

from .env_utils import update_env_file
from .token_manager import save_tokens, get_token_status


@dataclass
class AuthResult:
    """Result of an authentication attempt."""
    success: bool
    token: Optional[str] = None
    refresh_token: Optional[str] = None
    error: Optional[str] = None
    expires_in: Optional[int] = None  # seconds until token expires


# Global to store the received tokens (used by callback handler)
_received_data: Optional[dict] = None
_auth_complete = threading.Event()


class CallbackHandler(http.server.BaseHTTPRequestHandler):
    """
    HTTP handler that receives the OAuth callback with tokens.
    
    Supports two modes:
    - GET /callback?token=... (legacy, ID token only)
    - POST /callback with JSON body (full token set with refresh)
    """
    
    def log_message(self, format, *args):
        """Log HTTP requests for debugging."""
        print(f"[Callback Server] {format % args}")
    
    def do_GET(self):
        global _received_data
        
        parsed = urllib.parse.urlparse(self.path)
        print(f"[Callback Server] GET {parsed.path} with query: {parsed.query[:100]}...")
        
        if parsed.path == "/callback":
            # Parse query parameters
            params = urllib.parse.parse_qs(parsed.query)
            print(f"[Callback Server] Params keys: {list(params.keys())}")
            
            if "token" in params:
                # Legacy mode: just the ID token
                _received_data = {
                    "id_token": params["token"][0],
                    "refresh_token": params.get("refresh_token", [None])[0],
                    "user_pool_id": params.get("user_pool_id", [None])[0],
                    "client_id": params.get("client_id", [None])[0],
                }
                print(f"[Callback Server] Received token (length={len(_received_data['id_token'])})")
                print(f"[Callback Server] Has refresh_token: {_received_data['refresh_token'] is not None}")
                
                # Send success page
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Connection", "close")
                self.end_headers()
                self.wfile.write(self._success_page().encode('utf-8'))
                self.wfile.flush()
                
                # Signal that auth is complete
                print("[Callback Server] Setting auth_complete event...")
                _auth_complete.set()
                print("[Callback Server] Event set!")
                
            elif "error" in params:
                error_msg = params.get("error_description", params["error"])[0]
                
                self.send_response(400)
                self.send_header("Content-Type", "text/html")
                self.end_headers()
                self.wfile.write(self._error_page(error_msg).encode())
                
                _auth_complete.set()
            else:
                self.send_response(400)
                self.send_header("Content-Type", "text/plain")
                self.end_headers()
                self.wfile.write(b"Missing token parameter")
        else:
            self.send_response(404)
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            self.wfile.write(b"Not found")
    
    def do_POST(self):
        """Handle POST requests for token submission (preferred method)."""
        global _received_data
        
        parsed = urllib.parse.urlparse(self.path)
        
        if parsed.path == "/callback":
            content_length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_length).decode()
            
            try:
                data = json.loads(body)
                
                # Accept either 'token' (legacy) or 'id_token' (new)
                id_token = data.get("id_token") or data.get("token")
                
                if id_token:
                    _received_data = {
                        "id_token": id_token,
                        "refresh_token": data.get("refresh_token"),
                        "access_token": data.get("access_token"),
                        "user_pool_id": data.get("user_pool_id"),
                        "client_id": data.get("client_id"),
                    }
                    
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Access-Control-Allow-Origin", "*")
                    self.end_headers()
                    self.wfile.write(json.dumps({"status": "ok"}).encode())
                    
                    _auth_complete.set()
                else:
                    self.send_response(400)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Access-Control-Allow-Origin", "*")
                    self.end_headers()
                    self.wfile.write(json.dumps({"error": "missing token"}).encode())
            except json.JSONDecodeError:
                self.send_response(400)
                self.send_header("Content-Type", "application/json")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(json.dumps({"error": "invalid json"}).encode())
        else:
            self.send_response(404)
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
    
    def do_OPTIONS(self):
        """Handle CORS preflight requests."""
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "POST, GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()
    
    def _success_page(self) -> str:
        return """
        <!DOCTYPE html>
        <html>
        <head>
            <title>Authentication Successful</title>
            <style>
                body {
                    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
                    display: flex;
                    justify-content: center;
                    align-items: center;
                    height: 100vh;
                    margin: 0;
                    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                }
                .card {
                    background: white;
                    padding: 3rem;
                    border-radius: 16px;
                    box-shadow: 0 10px 40px rgba(0,0,0,0.2);
                    text-align: center;
                    max-width: 400px;
                }
                .success-icon {
                    font-size: 4rem;
                    margin-bottom: 1rem;
                }
                h1 { color: #22c55e; margin: 0 0 1rem 0; }
                p { color: #666; margin: 0; }
                .hint {
                    margin-top: 1.5rem;
                    padding: 1rem;
                    background: #f3f4f6;
                    border-radius: 8px;
                    font-family: monospace;
                    font-size: 0.9rem;
                    color: #374151;
                }
                .feature {
                    margin-top: 1rem;
                    padding: 0.75rem;
                    background: #ecfdf5;
                    border-radius: 8px;
                    font-size: 0.85rem;
                    color: #065f46;
                }
            </style>
        </head>
        <body>
            <div class="card">
                <div class="success-icon">✅</div>
                <h1>Authentication Successful!</h1>
                <p>Your credentials have been saved securely.</p>
                <div class="feature">
                    🔄 <strong>Auto-refresh enabled</strong> — tokens will refresh automatically for 30 days
                </div>
                <div class="hint">You can close this window and return to your terminal.</div>
            </div>
        </body>
        </html>
        """
    
    def _error_page(self, error: str) -> str:
        return f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>Authentication Failed</title>
            <style>
                body {{
                    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
                    display: flex;
                    justify-content: center;
                    align-items: center;
                    height: 100vh;
                    margin: 0;
                    background: #fee2e2;
                }}
                .card {{
                    background: white;
                    padding: 3rem;
                    border-radius: 16px;
                    box-shadow: 0 10px 40px rgba(0,0,0,0.1);
                    text-align: center;
                    max-width: 400px;
                }}
                h1 {{ color: #dc2626; }}
                .error {{ color: #7f1d1d; background: #fecaca; padding: 1rem; border-radius: 8px; }}
            </style>
        </head>
        <body>
            <div class="card">
                <h1>❌ Authentication Failed</h1>
                <div class="error">{error}</div>
            </div>
        </body>
        </html>
        """


def authenticate_with_browser(
    platform_url: str,
    callback_port: int = 9876,
    timeout: int = 300,
    on_status: Optional[Callable[[str], None]] = None,
) -> AuthResult:
    """
    Perform browser-based authentication with the DE Platform.
    
    This starts a local HTTP server, opens the platform login page,
    and waits for the callback with the tokens (including refresh token).
    
    Args:
        platform_url: Base URL of the DE platform (e.g., "https://de.example.com")
        callback_port: Local port for the callback server (default: 9876)
        timeout: Maximum seconds to wait for authentication (default: 300)
        on_status: Optional callback for status updates
    
    Returns:
        AuthResult with success/failure, tokens, and metadata.
    
    Example:
        >>> result = authenticate_with_browser("https://de.example.com")
        >>> if result.success:
        ...     print(f"Got token: {result.token[:20]}...")
        ...     print(f"Refresh token: {'Yes' if result.refresh_token else 'No'}")
    """
    global _received_data, _auth_complete
    
    # Reset global state
    _received_data = None
    _auth_complete.clear()
    
    def status(msg: str):
        if on_status:
            on_status(msg)
    
    # Generate a unique state parameter for security
    state = secrets.token_urlsafe(16)
    
    # Build the callback URL
    callback_url = f"http://localhost:{callback_port}/callback"
    
    # Build the login URL with redirect parameters
    login_url = (
        f"{platform_url.rstrip('/')}/login"
        f"?redirect=cli_callback"
        f"&callback_url={urllib.parse.quote(callback_url)}"
        f"&state={state}"
    )
    
    # Start the local callback server
    try:
        socketserver.TCPServer.allow_reuse_address = True
        server = socketserver.TCPServer(("localhost", callback_port), CallbackHandler)
        server.timeout = 1  # Allow periodic checks
    except OSError as e:
        return AuthResult(
            success=False,
            error=f"Could not start callback server on port {callback_port}: {e}"
        )
    
    server_thread = threading.Thread(target=_run_server, args=(server, timeout))
    server_thread.daemon = True
    server_thread.start()
    
    status(f"Started local callback server on port {callback_port}")
    
    # Open the browser
    status(f"Opening browser to {platform_url}/login...")
    webbrowser.open(login_url)
    
    # Wait for the callback
    status("Waiting for authentication... (press Ctrl+C to cancel)")
    
    try:
        # Use a loop with short waits to allow Ctrl+C on Windows
        elapsed = 0
        while elapsed < timeout:
            if _auth_complete.wait(timeout=0.5):
                print(f"[Auth] Event detected after {elapsed:.1f}s")
                break
            elapsed += 0.5
            if elapsed % 10 == 0:
                print(f"[Auth] Still waiting... ({elapsed:.0f}s elapsed)")
        
        print(f"[Auth] Exited wait loop. Event set: {_auth_complete.is_set()}")
        print(f"[Auth] Received data: {_received_data is not None}")
        
        # Don't wait for shutdown - just close the socket
        print("[Auth] Closing server socket...")
        try:
            server.socket.close()
        except Exception as e:
            print(f"[Auth] Socket close error (ignored): {e}")
        print("[Auth] Server socket closed")
        
        if _received_data and _received_data.get("id_token"):
            print(f"[Auth] Returning success with token length: {len(_received_data['id_token'])}")
            return AuthResult(
                success=True,
                token=_received_data["id_token"],
                refresh_token=_received_data.get("refresh_token"),
                expires_in=3600,  # ID token lifetime
            )
        elif _auth_complete.is_set():
            return AuthResult(
                success=False,
                error="Authentication callback received but no token was provided"
            )
        else:
            return AuthResult(
                success=False,
                error=f"Authentication timed out after {timeout} seconds"
            )
    except KeyboardInterrupt:
        status("\n❌ Authentication cancelled by user")
        try:
            server.socket.close()
        except:
            pass
        return AuthResult(
            success=False,
            error="Authentication cancelled by user"
        )


def _run_server(server: socketserver.TCPServer, timeout: int):
    """Run the callback server until auth completes or timeout."""
    print("[Server Thread] Starting server loop")
    start_time = time.time()
    while not _auth_complete.is_set():
        try:
            server.handle_request()
        except Exception as e:
            print(f"[Server Thread] handle_request error: {e}")
            break
        if _auth_complete.is_set():
            print("[Server Thread] Event is set, exiting loop")
            break
        if time.time() - start_time > timeout:
            print("[Server Thread] Timeout reached")
            break
    print("[Server Thread] Server loop ended")


def get_fresh_token(
    platform_url: str,
    callback_port: int = 9876,
    timeout: int = 300,
) -> Optional[str]:
    """
    Convenience function to get a fresh token via browser authentication.
    
    This is a simplified wrapper around authenticate_with_browser().
    
    Args:
        platform_url: Base URL of the DE platform
        callback_port: Local port for callback (default: 9876)
        timeout: Max seconds to wait (default: 300)
    
    Returns:
        The token string if successful, None otherwise.
    """
    result = authenticate_with_browser(
        platform_url=platform_url,
        callback_port=callback_port,
        timeout=timeout,
    )
    return result.token if result.success else None


def authenticate_and_update_env(
    platform_url: str,
    env_key: str = "PLATFORM_API_TOKEN",
    env_path: Optional[Path] = None,
    callback_port: int = 9876,
    timeout: int = 300,
    on_status: Optional[Callable[[str], None]] = None,
    user_pool_id: Optional[str] = None,
    client_id: Optional[str] = None,
) -> AuthResult:
    """
    Complete authentication flow: browser auth + token storage + .env update.
    
    This is the main function used by `platform auth`.
    
    Tokens are saved in two places:
    1. ~/.de_platform/config - For auto-refresh (includes refresh_token)
    2. .env file - For backward compatibility (PLATFORM_API_TOKEN only)
    
    Args:
        platform_url: Base URL of the DE platform
        env_key: The environment variable name to update (default: PLATFORM_API_TOKEN)
        env_path: Path to .env file (default: current directory)
        callback_port: Local port for callback server
        timeout: Max seconds to wait for authentication
        on_status: Optional callback for status messages
        user_pool_id: Cognito User Pool ID (for token refresh)
        client_id: Cognito App Client ID (for token refresh)
    
    Returns:
        AuthResult indicating success/failure.
    """
    global _received_data
    
    def status(msg: str):
        if on_status:
            on_status(msg)
    
    # Step 1: Browser authentication
    result = authenticate_with_browser(
        platform_url=platform_url,
        callback_port=callback_port,
        timeout=timeout,
        on_status=on_status,
    )
    
    if not result.success:
        return result
    
    # Step 2: Save tokens to ~/.de_platform/config for auto-refresh
    status("Saving tokens for auto-refresh...")
    
    # Get Cognito config from callback data or parameters
    pool_id = None
    app_client_id = None
    
    if _received_data:
        pool_id = _received_data.get("user_pool_id") or user_pool_id
        app_client_id = _received_data.get("client_id") or client_id
    
    if result.refresh_token and pool_id and app_client_id:
        save_tokens(
            id_token=result.token,
            refresh_token=result.refresh_token,
            platform_url=platform_url,
            user_pool_id=pool_id,
            client_id=app_client_id,
        )
        status("✅ Tokens saved with auto-refresh enabled (30 days)")
    elif result.refresh_token:
        # Save without Cognito config - can't auto-refresh but still useful
        save_tokens(
            id_token=result.token,
            refresh_token=result.refresh_token,
            platform_url=platform_url,
        )
        status("⚠️  Tokens saved (auto-refresh needs Cognito config from frontend)")
    else:
        status("⚠️  No refresh token received - token will expire in 1 hour")
    
    # Step 3: Update .env file for backward compatibility
    status("Updating .env file...")
    
    try:
        success = update_env_file(
            key=env_key,
            value=result.token,
            env_path=env_path,
            create_if_missing=True,
        )
        
        if success:
            status(f"✅ {env_key} updated in .env")
            return result
        else:
            return AuthResult(
                success=False,
                error="Failed to update .env file"
            )
    except Exception as e:
        return AuthResult(
            success=False,
            error=f"Error updating .env: {str(e)}"
        )


# Manual token input fallback
def prompt_for_token() -> Optional[str]:
    """
    Prompt the user to manually paste a token.
    
    This is a fallback when browser authentication isn't available.
    
    Returns:
        The token string, or None if cancelled.
    """
    print("\n📋 Manual Token Entry")
    print("-" * 40)
    print("1. Open your browser and log in to the DE Platform")
    print("2. Open DevTools (F12) → Network tab")
    print("3. Find any /api/ request")
    print("4. Copy the Authorization header value (after 'Bearer ')")
    print("-" * 40)
    print()
    
    try:
        token = input("Paste your token (or press Enter to cancel): ").strip()
        if token:
            # Clean up common copy-paste issues
            if token.lower().startswith("bearer "):
                token = token[7:]
            return token
        return None
    except (KeyboardInterrupt, EOFError):
        return None


# Out-of-Band (OOB) authentication for enterprise/CloudFront environments
def authenticate_oob(
    platform_url: str,
    on_status: Optional[Callable[[str], None]] = None,
) -> AuthResult:
    """
    Out-of-Band authentication for enterprise environments.
    
    This flow is used when localhost callbacks are blocked by:
    - Corporate firewalls
    - CloudFront WAF policies
    - VPN/proxy restrictions
    
    Flow:
    1. Opens browser to platform login with mode=cli_oob
    2. User logs in and sees an auth code displayed
    3. User pastes the auth code into the CLI
    4. CLI exchanges the code for tokens via the platform API
    
    Args:
        platform_url: Base URL of the DE platform
        on_status: Optional callback for status messages
    
    Returns:
        AuthResult with success/failure and tokens
    """
    def status(msg: str):
        if on_status:
            on_status(msg)
    
    # Generate a unique state for this auth session
    state = secrets.token_urlsafe(16)
    
    # Build the OOB login URL
    login_url = f"{platform_url.rstrip('/')}/login?mode=cli_oob&state={state}"
    
    status("Opening browser for authentication...")
    status("(CloudFront-compatible OOB mode)")
    
    # Open the browser
    webbrowser.open(login_url)
    
    print()
    print("=" * 50)
    print("  📋  AUTHORIZATION CODE FLOW")
    print("=" * 50)
    print()
    print("  1. Sign in to the platform in your browser")
    print("  2. After login, you'll see an Authorization Code")
    print("  3. Copy and paste the code below")
    print()
    print("=" * 50)
    print()
    
    try:
        auth_code = input("  Enter authorization code: ").strip()
        
        if not auth_code:
            return AuthResult(success=False, error="No authorization code provided")
        
        # Exchange the code for tokens via the platform API
        status("Exchanging authorization code for tokens...")
        
        import httpx
        
        def try_exchange(url: str) -> tuple:
            """Try to exchange code at the given URL. Returns (response, error)."""
            try:
                exchange_url = f"{url.rstrip('/')}/api/auth/exchange-code"
                print(f"[OOB] Calling: POST {exchange_url}")
                
                response = httpx.post(
                    exchange_url,
                    json={
                        "code": auth_code,
                        "state": state,
                    },
                    headers={
                        "Content-Type": "application/json",
                        "User-Agent": "PlatformSDK-CLI/1.0",
                    },
                    timeout=30.0,
                )
                return response, None
            except httpx.RequestError as e:
                return None, str(e)
        
        # Try primary URL first
        response, network_error = try_exchange(platform_url)
        
        # Auto-detect CloudFront 403 and try direct URL fallback
        if response and response.status_code == 403:
            direct_url = os.getenv("PLATFORM_DIRECT_URL")
            if direct_url:
                print(f"[OOB] CloudFront blocked (403). Trying direct backend: {direct_url}")
                status("CloudFront blocked. Trying direct backend...")
                response, network_error = try_exchange(direct_url)
            else:
                print("[OOB] CloudFront blocked (403). Set PLATFORM_DIRECT_URL to bypass.")
                print("[OOB] Example: PLATFORM_DIRECT_URL=http://3.108.136.233")
        
        if network_error:
            return AuthResult(success=False, error=f"Network error: {network_error}")
        
        print(f"[OOB] Response status: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            # Prefer access_token for API calls (longer-lived), fallback to id_token
            return AuthResult(
                success=True,
                token=data.get("access_token") or data.get("id_token"),
                refresh_token=data.get("refresh_token"),
                expires_in=data.get("expires_in", 3600),
            )
        else:
            # Handle non-JSON error responses gracefully
            try:
                error_data = response.json()
                error_msg = error_data.get("detail") or error_data.get("error") or f"HTTP {response.status_code}"
            except Exception:
                # Response isn't JSON - show the raw text
                error_msg = f"HTTP {response.status_code}: {response.text[:200]}"
            return AuthResult(success=False, error=f"Code exchange failed: {error_msg}")
        
    except (KeyboardInterrupt, EOFError):
        return AuthResult(success=False, error="Authentication cancelled by user")


def authenticate_and_update_env_oob(
    platform_url: str,
    env_key: str = "PLATFORM_API_TOKEN",
    env_path: Optional[Path] = None,
    on_status: Optional[Callable[[str], None]] = None,
) -> AuthResult:
    """
    Complete OOB authentication flow: browser + code exchange + storage.
    
    This is used by `platform auth --oob` for enterprise/CloudFront environments.
    """
    def status(msg: str):
        if on_status:
            on_status(msg)
    
    # Step 1: OOB authentication
    result = authenticate_oob(
        platform_url=platform_url,
        on_status=on_status,
    )
    
    if not result.success:
        return result
    
    # Step 2: Save tokens
    status("Saving authentication tokens...")
    
    if result.refresh_token:
        save_tokens(
            id_token=result.token,
            refresh_token=result.refresh_token,
            platform_url=platform_url,
        )
        status("✅ Tokens saved with auto-refresh enabled")
    
    # Step 3: Update .env
    try:
        success = update_env_file(
            key=env_key,
            value=result.token,
            env_path=env_path,
            create_if_missing=True,
        )
        
        if success:
            status(f"✅ {env_key} updated in .env")
            return result
        else:
            return AuthResult(success=False, error="Failed to update .env file")
    except Exception as e:
        return AuthResult(success=False, error=f"Error updating .env: {e}")
