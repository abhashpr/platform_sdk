# platform_sdk/env_utils.py
"""
Environment file utilities for the Platform SDK.

Provides functions to read, update, and manage .env files while
preserving comments and formatting.
"""

import os
import re
from pathlib import Path
from typing import Optional, Union


def update_env_file(
    key: str,
    value: str,
    env_path: Optional[Union[str, Path]] = None,
    create_if_missing: bool = True,
) -> bool:
    """
    Update or add a key-value pair in a .env file.

    This function preserves existing comments and formatting in the file.

    Args:
        key: The environment variable name (e.g., "PLATFORM_API_TOKEN")
        value: The value to set (will be properly escaped if needed)
        env_path: Path to the .env file. Defaults to ".env" in current directory.
        create_if_missing: If True, create the .env file if it doesn't exist.

    Returns:
        True if the operation succeeded, False otherwise.

    Behavior:
        1. If the file exists and contains the key → replaces the value
        2. If the file exists but doesn't contain the key → appends at end
        3. If the file doesn't exist and create_if_missing=True → creates it
        4. If the file doesn't exist and create_if_missing=False → returns False

    Example:
        >>> update_env_file("PLATFORM_API_TOKEN", "eyJraWQi...")
        True

        >>> update_env_file("MY_KEY", "my_value", env_path="/path/to/.env")
        True
    """
    if env_path is None:
        env_path = Path.cwd() / ".env"
    else:
        env_path = Path(env_path)

    # Escape value if it contains special characters
    escaped_value = _escape_value(value)

    # Build the new line
    new_line = f"{key}={escaped_value}"

    # Case 1: File doesn't exist
    if not env_path.exists():
        if create_if_missing:
            env_path.write_text(f"{new_line}\n", encoding="utf-8")
            return True
        return False

    # Case 2: File exists - read and process
    content = env_path.read_text(encoding="utf-8")
    lines = content.splitlines(keepends=True)

    # Pattern to match the key (handles KEY=value, KEY = value, KEY="value", etc.)
    # Also matches commented-out versions like # KEY=value
    key_pattern = re.compile(
        rf"^(\s*#?\s*)?{re.escape(key)}\s*=.*$",
        re.MULTILINE
    )

    # Check if key exists (including commented out)
    if key_pattern.search(content):
        # Replace the first uncommented occurrence, or the first commented one
        found_uncommented = False
        new_lines = []

        for line in lines:
            stripped = line.strip()

            # Check if this line is an uncommented assignment for our key
            if not found_uncommented and not stripped.startswith("#"):
                if re.match(rf"^{re.escape(key)}\s*=", stripped):
                    # Replace this line
                    # Preserve the original line ending
                    line_ending = _get_line_ending(line)
                    new_lines.append(f"{new_line}{line_ending}")
                    found_uncommented = True
                    continue

            new_lines.append(line)

        # If we only found commented versions, append as new
        if not found_uncommented:
            # Ensure file ends with newline before appending
            if new_lines and not new_lines[-1].endswith("\n"):
                new_lines[-1] += "\n"
            new_lines.append(f"{new_line}\n")

        env_path.write_text("".join(new_lines), encoding="utf-8")
        return True

    # Case 3: Key doesn't exist - append to end
    # Ensure file ends with newline before appending
    if content and not content.endswith("\n"):
        content += "\n"

    content += f"{new_line}\n"
    env_path.write_text(content, encoding="utf-8")
    return True


def _escape_value(value: str) -> str:
    """
    Escape a value for safe inclusion in a .env file.

    If the value contains spaces, quotes, or special characters,
    it will be wrapped in double quotes with proper escaping.

    Args:
        value: The raw value to escape

    Returns:
        The escaped value, possibly wrapped in quotes
    """
    # If value is simple (alphanumeric, underscore, dash, dot, forward slash)
    # and doesn't start/end with whitespace, return as-is
    if re.match(r"^[\w\-./]+$", value) and value == value.strip():
        return value

    # Otherwise, wrap in double quotes and escape internal quotes/backslashes
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def _get_line_ending(line: str) -> str:
    """
    Detect the line ending of a string.

    Args:
        line: A line of text that may end with \\n, \\r\\n, or nothing

    Returns:
        The detected line ending, or \\n as default
    """
    if line.endswith("\r\n"):
        return "\r\n"
    elif line.endswith("\n"):
        return "\n"
    elif line.endswith("\r"):
        return "\r"
    return "\n"


def get_env_value(
    key: str,
    env_path: Optional[Union[str, Path]] = None,
) -> Optional[str]:
    """
    Read a specific key from a .env file.

    Args:
        key: The environment variable name to read
        env_path: Path to the .env file. Defaults to ".env" in current directory.

    Returns:
        The value if found, None otherwise.

    Note:
        This is a simple reader that doesn't handle all edge cases.
        For production use, consider using python-dotenv's dotenv_values.
    """
    if env_path is None:
        env_path = Path.cwd() / ".env"
    else:
        env_path = Path(env_path)

    if not env_path.exists():
        return None

    content = env_path.read_text(encoding="utf-8")

    # Pattern to match KEY=value (not commented)
    pattern = re.compile(rf'^{re.escape(key)}\s*=\s*(.*)$', re.MULTILINE)
    match = pattern.search(content)

    if not match:
        return None

    value = match.group(1).strip()

    # Remove surrounding quotes if present
    if len(value) >= 2:
        if (value.startswith('"') and value.endswith('"')) or \
           (value.startswith("'") and value.endswith("'")):
            value = value[1:-1]

    return value


def env_file_exists(env_path: Optional[Union[str, Path]] = None) -> bool:
    """
    Check if a .env file exists.

    Args:
        env_path: Path to check. Defaults to ".env" in current directory.

    Returns:
        True if the file exists, False otherwise.
    """
    if env_path is None:
        env_path = Path.cwd() / ".env"
    else:
        env_path = Path(env_path)

    return env_path.exists()
