import os
import shutil
import time
from typing import Optional

from google.auth.exceptions import RefreshError
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = ["https://www.googleapis.com/auth/drive"]


def backup_expired_token(token_file: str) -> Optional[str]:
    """Rename expired or invalid token file to token.json.<epoch>."""
    if not os.path.exists(token_file):
        return None

    epoch = int(time.time())
    backup_file = f"{token_file}.{epoch}"
    try:
        shutil.move(token_file, backup_file)
        print(
            f"[!] Token expired or invalid. Renamed to {os.path.basename(backup_file)} "
            f"and re-authenticating..."
        )
        return backup_file
    except Exception as e:
        print(f"[!] Warning: Failed to rename expired token file {token_file}: {e}")
        return None


def get_credentials(
    secrets_file: str,
    token_file: str,
    force_reauth: bool = False,
) -> Credentials:
    """Retrieve valid credentials.

    If the token is expired or revoked, rename the token file to
    token.json.<epoch> and launch authentication flow again.
    """
    creds: Optional[Credentials] = None

    if not force_reauth and os.path.exists(token_file):
        try:
            creds = Credentials.from_authorized_user_file(token_file, SCOPES)
        except Exception as e:
            print(f"[!] Corrupted token file ({e}).")
            backup_expired_token(token_file)
            creds = None

    # Check validity and refresh if expired
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                print("[*] Refreshing access token...")
                creds.refresh(Request())
            except (RefreshError, Exception) as e:
                print(f"[!] Token refresh failed ({e}).")
                backup_expired_token(token_file)
                creds = None
        elif creds and not creds.valid:
            backup_expired_token(token_file)
            creds = None

    # Need fresh authentication flow
    if not creds or not creds.valid:
        if not os.path.exists(secrets_file):
            raise FileNotFoundError(
                f"Client secrets file not found at: {secrets_file}\n"
                "Please download OAuth client credentials from Google Cloud Console and save as client_secrets.json "
                "in %USERPROFILE%\\.config\\google-drive\\ (Windows) or ~/.config/google-drive/ (Linux/macOS)."
            )

        print("[*] Starting local server for Google OAuth authentication...")
        flow = InstalledAppFlow.from_client_secrets_file(secrets_file, SCOPES)
        creds = flow.run_local_server(port=0)

        # Save new token
        token_dir = os.path.dirname(os.path.abspath(token_file))
        if token_dir:
            os.makedirs(token_dir, exist_ok=True)

        with open(token_file, "w", encoding="utf-8") as f:
            f.write(creds.to_json())
        print(f"[+] Authentication successful. Saved new token to {token_file}")

    return creds
