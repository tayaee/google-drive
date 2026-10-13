import argparse
from datetime import datetime
import json
import os
import subprocess
import sys
import time
from typing import Any, Dict, Optional

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

from google_drive.auth import SCOPES, backup_expired_token, get_credentials
from google_drive.client import GoogleDriveClient, sanitize_filename
from google_drive.config import resolve_auth_paths
from google_drive.models import (
    ApiStatus,
    GoogleDriveStatus,
    MountInfo,
    MountStatus,
    MyDriveSummary,
)
from google_drive.mount import (
    clear_mount_state,
    get_active_mounts,
    get_mount_state_file,
    is_pid_alive,
    normalize_drive_letter,
    start_mount,
    stop_mount,
)


def format_iso8601_with_tz(dt_str: Optional[str]) -> str:
    """Format RFC3339 / ISO-8601 timestamp into ISO-8601 with local timezone offset."""
    if not dt_str:
        return "-------------------------"
    try:
        dt = datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
        return dt.astimezone().isoformat(timespec="seconds")
    except Exception:
        return dt_str


def format_ls_l_entry(item: Dict[str, Any]) -> str:
    """Format a single item in ls -l style with ISO-8601 tz timestamp."""
    is_dir = item.get("mimeType") == "application/vnd.google-apps.folder"
    mode_str = "drwxr-xr-x" if is_dir else "-rw-r--r--"

    size_raw = item.get("size")
    if is_dir:
        size_str = f"{'-':>12}"
    else:
        try:
            size_str = f"{int(size_raw):>12}"
        except (ValueError, TypeError):
            size_str = f"{'-':>12}"

    dt_str = format_iso8601_with_tz(item.get("modifiedTime"))
    name = item.get("display_name", item.get("name", "Untitled"))
    name_display = f"{name}/" if is_dir else name

    return f"{mode_str} 1 user group {size_str} {dt_str} {name_display}"


def get_drive_status(secrets_file: str, token_file: str) -> GoogleDriveStatus:
    """Collect API and mount status into a Pydantic GoogleDriveStatus model."""
    # 1. Google Drive API & My Drive summary
    try:
        client = GoogleDriveClient(secrets_file, token_file)
        summary_raw = client.get_my_drive_summary()
        api_info = ApiStatus(
            connected=True,
            status="Connected",
            error=None,
            my_drive=MyDriveSummary(
                folders=summary_raw.get("folders", 0),
                files=summary_raw.get("files", 0),
                total=summary_raw.get("total", 0),
            ),
        )
    except Exception as e:
        api_info = ApiStatus(
            connected=False,
            status=f"Error ({e})",
            error=str(e),
            my_drive=None,
        )

    # 2. Mount status
    active_mounts = get_active_mounts()
    mount_list = []
    for m in active_mounts:
        drive = m.get("drive_letter", "Unknown")
        port = m.get("port")
        pid = m.get("pid")
        url = m.get("webdav_url", f"http://127.0.0.1:{port}/" if port else "")
        mount_list.append(
            MountInfo(
                drive_letter=drive,
                drive_path=f"{drive}\\",
                webdav_url=url,
                pid=pid,
                port=port,
            )
        )

    mount_info = MountStatus(
        is_mounted=len(mount_list) > 0,
        mounts=mount_list,
    )

    return GoogleDriveStatus(api=api_info, mount=mount_info)


def cmd_status(args: argparse.Namespace) -> None:
    secrets_file, token_file = resolve_auth_paths(args.secrets_file, args.token_file)

    if getattr(args, "json", False):
        import contextlib
        # Redirect progress prints to stderr so stdout is strictly clean JSON
        with contextlib.redirect_stdout(sys.stderr):
            status_obj = get_drive_status(secrets_file, token_file)
        print(status_obj.model_dump_json(indent=2))
        return

    print("=" * 60)
    print(" Google Drive Status")
    print("=" * 60)

    # 1. Google Drive API & My Drive summary (lightweight call)
    print("[*] Checking Google Drive API connection...")
    try:
        client = GoogleDriveClient(secrets_file, token_file)
        summary = client.get_my_drive_summary()
        folders = summary["folders"]
        files = summary["files"]
        total = summary["total"]
        print(f"[+] API Status   : Connected")
        print(f"[+] My Drive     : {folders} folders, {files} files (Total: {total} items)")
    except Exception as e:
        print(f"[!] API Status   : Error ({e})")
        print("    Please check credentials or run 'google-drive auth'.")

    print("-" * 60)

    # 2. Mount status
    active_mounts = get_active_mounts()
    if active_mounts:
        for m in active_mounts:
            drive = m.get("drive_letter", "Unknown")
            pid = m.get("pid", "-")
            port = m.get("port", "-")
            url = m.get("webdav_url", f"http://127.0.0.1:{port}/")
            print(f"[+] Mount Status : MOUNTED on {drive}")
            print(f"    - Drive Path : {drive}\\")
            print(f"    - WebDAV URL : {url}")
            print(f"    - Process PID: {pid}")
    else:
        print("[-] Mount Status : NOT MOUNTED")
        print("    To mount Google Drive, run:")
        print("      google-drive mount")
        print("    or specify a drive letter:")
        print("      google-drive mount G:")

    print("=" * 60)


def cmd_mount(args: argparse.Namespace) -> None:
    secrets_file, token_file = resolve_auth_paths(args.secrets_file, args.token_file)
    drive_letter = normalize_drive_letter(args.drive_letter)

    # In Windows, if not run in foreground, spawn in a new console window
    if os.name == "nt" and not getattr(args, "foreground", False):
        # 1. Pre-check if already running to report errors in the current console
        state_file = get_mount_state_file(drive_letter)
        already_running = False
        existing_pid = None
        if state_file.exists():
            try:
                data = json.loads(state_file.read_text(encoding="utf-8"))
                pid = data.get("pid")
                if pid and is_pid_alive(pid):
                    already_running = True
                    existing_pid = pid
                else:
                    clear_mount_state(drive_letter)
            except Exception:
                clear_mount_state(drive_letter)

        if not already_running and os.path.exists(f"{drive_letter}\\"):
            already_running = True

        if already_running:
            if args.force:
                print("[*] Force option specified (-f/--force).")
                print(f"[*] Unmounting existing drive {drive_letter}...")
                stop_mount(drive_letter)
                time.sleep(1)
            else:
                pid_info = f" (PID: {existing_pid})" if existing_pid else ""
                print(f"[!] Error: Google Drive is already mounted or running on {drive_letter}{pid_info}.")
                print("    Aborting mount.")
                print(f"    - To unmount: google-drive umount {drive_letter}")
                print(f"    - To force remount: google-drive mount -f {drive_letter}")
                sys.exit(1)

        # 2. Launch in a new console window
        cmd = [sys.executable, "-m", "google_drive.cli", "mount", "--foreground", drive_letter]
        if args.port:
            cmd.extend(["-p", str(args.port)])
        if args.force:
            cmd.append("-f")
        if args.secrets_file:
            cmd.extend(["-s", args.secrets_file])
        if args.token_file:
            cmd.extend(["-t", args.token_file])

        print(f"[*] Launching Google Drive mount in a new window for {drive_letter}...")
        proc = subprocess.Popen(cmd, creationflags=subprocess.CREATE_NEW_CONSOLE)
        print(f"[+] Started mount process in new window (PID: {proc.pid}).")
        print(f"    - Target Drive: {drive_letter}\\")
        print(f"    - To check status: google-drive status")
        print(f"    - To unmount:      google-drive umount {drive_letter}")
        return

    # Running in foreground (inside the new window or non-Windows)
    start_mount(
        drive_letter=drive_letter,
        port=args.port,
        force=args.force,
        secrets_file=secrets_file,
        token_file=token_file,
    )


def cmd_umount(args: argparse.Namespace) -> None:
    stop_mount(drive_letter=args.drive_letter)


def cmd_dir(args: argparse.Namespace) -> None:
    secrets_file, token_file = resolve_auth_paths(args.secrets_file, args.token_file)
    client = GoogleDriveClient(secrets_file, token_file)

    remote_path = (args.remote_path or "").strip().strip("/").replace("\\", "/")
    lower_path = remote_path.lower()

    # Normalize 'My Drive' prefix
    if lower_path in ("my drive", "my_drive"):
        remote_path = ""
        lower_path = ""
    elif lower_path.startswith("my drive/"):
        remote_path = remote_path[9:].strip("/")
        lower_path = remote_path.lower()
    elif lower_path.startswith("my_drive/"):
        remote_path = remote_path[9:].strip("/")
        lower_path = remote_path.lower()

    if lower_path in ("shared with me", "shared_with_me"):
        items = client.list_shared_with_me()
        display_title = "Shared with me"
    elif lower_path.startswith("shared with me/") or lower_path.startswith("shared_with_me/"):
        subpath = remote_path.split("/", 1)[1].strip("/")
        segments = [s for s in subpath.split("/") if s]
        try:
            shared_items = client.list_shared_with_me()
            top_seg = segments[0]
            matched = None
            for it in shared_items:
                disp = it.get("display_name", "")
                raw = it.get("name", "")
                if disp == top_seg or raw == top_seg or sanitize_filename(raw) == top_seg:
                    matched = it
                    break
            if not matched:
                raise FileNotFoundError(f"Shared folder '{top_seg}' not found")

            curr_id = matched["id"]
            for seg in segments[1:]:
                sub_items = client.list_folder(curr_id)
                found = None
                for it in sub_items:
                    disp = it.get("display_name", "")
                    raw = it.get("name", "")
                    if disp == seg or raw == seg or sanitize_filename(raw) == seg:
                        found = it
                        break
                if not found:
                    raise FileNotFoundError(f"Subfolder '{seg}' not found in '{curr_id}'")
                curr_id = found["id"]

            items = client.list_folder(curr_id)
            display_title = remote_path
        except Exception as e:
            print(f"[!] Path error: {e}")
            sys.exit(1)
    else:
        try:
            folder_id = client.resolve_path(remote_path)
        except Exception as e:
            print(f"[!] Path error: {e}")
            sys.exit(1)

        display_title = remote_path or "My Drive"
        items = client.list_folder(folder_id)

    if not items:
        print(f"total 0 ({display_title})")
        return

    limit = args.limit or 100
    display_items = items[:limit]

    print(f"total {len(items)} (showing up to {limit} in {display_title}):")
    for item in display_items:
        print(format_ls_l_entry(item))


def cmd_auth(args: argparse.Namespace) -> None:
    secrets_file, token_file = resolve_auth_paths(args.secrets_file, args.token_file)

    if not args.force and os.path.exists(token_file):
        print("[*] Verifying existing authentication via Drive list API...")
        try:
            creds = Credentials.from_authorized_user_file(token_file, SCOPES)
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            if creds and creds.valid:
                # Run lightweight list call to verify actual access
                service = build("drive", "v3", credentials=creds)
                service.files().list(pageSize=1, fields="files(id)").execute()
                print("[+] Already authenticated and token is valid.")
                print(f"    Verified with Google Drive list API using {token_file}.")
                print("    Aborting auth flow. (Use 'google-drive auth -f' to force re-authenticate)")
                return
        except Exception as e:
            print(f"[!] Existing token is invalid or expired: {e}")
            backup_expired_token(token_file)

    print(f"[*] Starting authentication using {secrets_file}...")
    creds = get_credentials(secrets_file, token_file, force_reauth=args.force)
    if creds and creds.valid:
        print(f"[+] Authentication successful! Token saved at {token_file}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="google-drive",
        description="Google Drive WebDAV Mount and CLI Utility",
    )
    subparsers = parser.add_subparsers(dest="subcommand", help="Available subcommands")

    # mount
    mount_parser = subparsers.add_parser("mount", help="Mount Google Drive (My Drive + Shared with me)")
    mount_parser.add_argument(
        "drive_letter",
        nargs="?",
        default="G:",
        help="Windows drive letter to mount (default: G:)",
    )
    mount_parser.add_argument(
        "-p", "--port",
        type=int,
        default=None,
        help="WebDAV server port (default: auto-detect starting from 18875)",
    )
    mount_parser.add_argument(
        "-f", "--force",
        action="store_true",
        help="Force remount: unmount existing drive if already running.",
    )
    mount_parser.add_argument(
        "-F", "--foreground",
        action="store_true",
        help="Run mount in the foreground of the current console (do not open a new window).",
    )
    mount_parser.add_argument(
        "-s", "--secrets-file",
        type=str,
        default=None,
        help="Path to client_secrets.json (default: %%USERPROFILE%%\\.config\\google-drive\\ or ~/.config/google-drive/)",
    )
    mount_parser.add_argument(
        "-t", "--token-file",
        type=str,
        default=None,
        help="Path to token.json (default: %%USERPROFILE%%\\.config\\google-drive\\ or ~/.config/google-drive/)",
    )

    # umount
    umount_parser = subparsers.add_parser("umount", help="Unmount Google Drive")
    umount_parser.add_argument(
        "drive_letter",
        nargs="?",
        default="G:",
        help="Windows drive letter to unmount (default: G:)",
    )

    # dir
    dir_parser = subparsers.add_parser("dir", help="List files in Google Drive (ls -l format with ISO-8601 tz)")
    dir_parser.add_argument(
        "remote_path",
        nargs="?",
        default=None,
        help="Remote Google Drive folder path to list (default: root, or 'Shared with me')",
    )
    dir_parser.add_argument(
        "-n", "--limit",
        type=int,
        default=100,
        help="Max number of files to display (default: 100)",
    )
    dir_parser.add_argument(
        "-s", "--secrets-file",
        type=str,
        default=None,
        help="Path to client_secrets.json (default: %%USERPROFILE%%\\.config\\google-drive\\ or ~/.config/google-drive/)",
    )
    dir_parser.add_argument(
        "-t", "--token-file",
        type=str,
        default=None,
        help="Path to token.json (default: %%USERPROFILE%%\\.config\\google-drive\\ or ~/.config/google-drive/)",
    )

    # list (alias for dir)
    list_parser = subparsers.add_parser("list", help="Alias for 'dir'")
    list_parser.add_argument(
        "remote_path",
        nargs="?",
        default=None,
        help="Remote Google Drive folder path to list (default: root, or 'Shared with me')",
    )
    list_parser.add_argument(
        "-n", "--limit",
        type=int,
        default=100,
        help="Max number of files to display (default: 100)",
    )
    list_parser.add_argument(
        "-s", "--secrets-file",
        type=str,
        default=None,
        help="Path to client_secrets.json (default: %%USERPROFILE%%\\.config\\google-drive\\ or ~/.config/google-drive/)",
    )
    list_parser.add_argument(
        "-t", "--token-file",
        type=str,
        default=None,
        help="Path to token.json (default: %%USERPROFILE%%\\.config\\google-drive\\ or ~/.config/google-drive/)",
    )

    # auth
    auth_parser = subparsers.add_parser("auth", help="Authenticate and generate token.json")
    auth_parser.add_argument(
        "-f", "--force",
        action="store_true",
        help="Force re-authentication even if current token exists",
    )
    auth_parser.add_argument(
        "-s", "--secrets-file",
        type=str,
        default=None,
        help="Path to client_secrets.json (default: %%USERPROFILE%%\\.config\\google-drive\\ or ~/.config/google-drive/)",
    )
    auth_parser.add_argument(
        "-t", "--token-file",
        type=str,
        default=None,
        help="Path to token.json (default: %%USERPROFILE%%\\.config\\google-drive\\ or ~/.config/google-drive/)",
    )

    # status
    status_parser = subparsers.add_parser("status", help="Show Google Drive and mount status")
    status_parser.add_argument(
        "-s", "--secrets-file",
        type=str,
        default=None,
        help="Path to client_secrets.json (default: %%USERPROFILE%%\\.config\\google-drive\\ or ~/.config/google-drive/)",
    )
    status_parser.add_argument(
        "-t", "--token-file",
        type=str,
        default=None,
        help="Path to token.json (default: %%USERPROFILE%%\\.config\\google-drive\\ or ~/.config/google-drive/)",
    )
    status_parser.add_argument(
        "-j", "--json",
        action="store_true",
        help="Output status in JSON format",
    )

    return parser


def main() -> None:
    parser = build_parser()
    if len(sys.argv) == 1:
        parser.print_help()
        sys.exit(0)

    args = parser.parse_args()
    if args.subcommand == "status":
        cmd_status(args)
    elif args.subcommand == "mount":
        cmd_mount(args)
    elif args.subcommand == "umount":
        cmd_umount(args)
    elif args.subcommand in ("dir", "list"):
        cmd_dir(args)
    elif args.subcommand == "auth":
        cmd_auth(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
