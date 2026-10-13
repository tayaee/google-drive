import os
from pathlib import Path
from typing import Optional, Tuple

CLIENT_SECRETS_FILENAME = "client_secrets.json"
TOKEN_FILENAME = "token.json"


def get_config_dir_path() -> Path:
    """Return the configuration directory path.

    - Windows: %USERPROFILE%\\.config\\google-drive
    - Linux/macOS/POSIX: ~/.config/google-drive (or $XDG_CONFIG_HOME/google-drive)
    """
    if os.name == "nt" and "USERPROFILE" in os.environ:
        base = Path(os.environ["USERPROFILE"]) / ".config"
    elif os.environ.get("XDG_CONFIG_HOME"):
        base = Path(os.environ["XDG_CONFIG_HOME"])
    else:
        base = Path.home() / ".config"
    return base / "google-drive"


def get_default_config_dir() -> Path:
    """Ensure and return the default configuration directory."""
    config_dir = get_config_dir_path()
    config_dir.mkdir(parents=True, exist_ok=True)
    return config_dir


DEFAULT_CONFIG_DIR = get_config_dir_path()


def resolve_auth_paths(
    secrets_path: Optional[str] = None,
    token_path: Optional[str] = None,
) -> Tuple[str, str]:
    """Resolve paths for client_secrets.json and token.json.

    Priority:
    1. Explicitly provided paths
    2. User configuration directory (%USERPROFILE%\\.config\\google-drive\\ or ~/.config/google-drive/)
    3. Current working directory
    4. Default fallback to user configuration directory
    """
    config_dir = get_config_dir_path()

    # 1. Resolve secrets path
    if secrets_path:
        resolved_secrets = secrets_path
    elif (config_dir / CLIENT_SECRETS_FILENAME).exists():
        resolved_secrets = str(config_dir / CLIENT_SECRETS_FILENAME)
    elif os.path.exists(CLIENT_SECRETS_FILENAME):
        resolved_secrets = os.path.abspath(CLIENT_SECRETS_FILENAME)
    else:
        resolved_secrets = str(config_dir / CLIENT_SECRETS_FILENAME)

    # 2. Resolve token path
    if token_path:
        resolved_token = token_path
    elif (config_dir / TOKEN_FILENAME).exists():
        resolved_token = str(config_dir / TOKEN_FILENAME)
    elif os.path.exists(TOKEN_FILENAME):
        resolved_token = os.path.abspath(TOKEN_FILENAME)
    else:
        if resolved_secrets == os.path.abspath(CLIENT_SECRETS_FILENAME) and os.path.exists(CLIENT_SECRETS_FILENAME):
            resolved_token = os.path.abspath(TOKEN_FILENAME)
        else:
            resolved_token = str(config_dir / TOKEN_FILENAME)

    return resolved_secrets, resolved_token
