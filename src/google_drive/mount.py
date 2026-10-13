import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import threading
import time
from typing import Optional

from cheroot import wsgi
from wsgidav.wsgidav_app import WsgiDAVApp

from google_drive.client import GoogleDriveClient
from google_drive.config import get_default_config_dir, resolve_auth_paths
from google_drive.dav_provider import GoogleDriveDAVProvider


def normalize_drive_letter(drive_letter: Optional[str]) -> str:
    """Normalize drive letter input (e.g. 'G', 'G:', 'g', 'G:\\' -> 'G:')."""
    if not drive_letter:
        return "G:"
    cleaned = drive_letter.strip().rstrip(":\\/").upper()
    if len(cleaned) != 1 or not cleaned.isalpha():
        raise ValueError(
            f"Invalid drive letter: '{drive_letter}'. Must be a single letter (e.g. G or G:)."
        )
    return f"{cleaned}:"


def is_port_available(port: int, host: str = "127.0.0.1") -> bool:
    """Check if a TCP port is available for binding."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.bind((host, port))
            return True
        except OSError:
            return False


def find_available_port(start_port: int = 18875, host: str = "127.0.0.1", max_tries: int = 1000) -> int:
    """Find the first available TCP port starting from start_port upwards."""
    for port in range(start_port, start_port + max_tries):
        if is_port_available(port, host):
            return port
    raise RuntimeError(f"No available port found in range {start_port} to {start_port + max_tries}")


def get_mount_state_file(drive_letter: str) -> Path:
    clean = drive_letter.rstrip(":").upper()
    state_dir = get_default_config_dir()
    return state_dir / f"mount_{clean}.json"


def save_mount_state(drive_letter: str, port: int, pid: int, url: str) -> None:
    state_file = get_mount_state_file(drive_letter)
    data = {
        "drive_letter": drive_letter,
        "port": port,
        "pid": pid,
        "webdav_url": url,
    }
    state_file.write_text(json.dumps(data, indent=2), encoding="utf-8")


def clear_mount_state(drive_letter: str) -> None:
    state_file = get_mount_state_file(drive_letter)
    if state_file.exists():
        try:
            state_file.unlink()
        except Exception:
            pass


def get_active_mounts() -> list[dict]:
    """Retrieve all currently active Google Drive mounts."""
    state_dir = get_default_config_dir()
    if not state_dir.exists():
        return []

    active = []
    for state_file in state_dir.glob("mount_*.json"):
        try:
            data = json.loads(state_file.read_text(encoding="utf-8"))
            pid = data.get("pid")
            drive = data.get("drive_letter")
            if pid and is_pid_alive(pid):
                active.append(data)
            elif drive and os.name == "nt" and os.path.exists(f"{drive}\\"):
                active.append(data)
            else:
                try:
                    state_file.unlink()
                except Exception:
                    pass
        except Exception:
            pass
    return active


def check_windows_webclient_settings() -> None:
    """Check WebClient registry settings on Windows and provide advice if needed."""
    if os.name != "nt":
        return
    try:
        import winreg

        with winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE,
            r"SYSTEM\CurrentControlSet\Services\WebClient\Parameters",
        ) as key:
            try:
                basic_auth, _ = winreg.QueryValueEx(key, "BasicAuthLevel")
            except OSError:
                basic_auth = 1

            if basic_auth != 2:
                print(
                    "[!] Notice: Windows WebClient registry setting 'BasicAuthLevel' is not 2.\n"
                    "    Windows blocks HTTP WebDAV drive mapping unless BasicAuthLevel=2.\n"
                    "    Please run 'fix-FileSizelimitInBytes-and-restart-WebClient.bat' as Administrator."
                )
    except Exception:
        pass


def mount_windows_drive(drive_letter: str, url: str) -> bool:
    """Mount URL as a Windows network drive using 'net use'."""
    cmd = ["net", "use", drive_letter, url, "/persistent:no"]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        if proc.returncode == 0:
            print(f"[+] Successfully mapped drive {drive_letter}")
            return True

        notice = proc.stderr.strip() or proc.stdout.strip()
        print(f"[!] 'net use' notice: {notice}")

        # Try fallback UNC syntax if http URL failed (e.g., \\127.0.0.1@18875\DavWWWRoot)
        if "http://" in url:
            try:
                port_part = url.split("://")[-1].split("/")[0].split(":")[-1]
                if port_part.isdigit():
                    fallback_unc = f"\\\\127.0.0.1@{port_part}\\DavWWWRoot"
                    fallback_cmd = ["net", "use", drive_letter, fallback_unc, "/persistent:no"]
                    proc_fb = subprocess.run(fallback_cmd, capture_output=True, text=True, timeout=10)
                    if proc_fb.returncode == 0:
                        print(f"[+] Successfully mapped drive {drive_letter} via UNC syntax ({fallback_unc})")
                        return True
            except Exception:
                pass

        if any(err_code in notice for err_code in ("59", "67", "1244")):
            print(
                "    Tip: Windows requires BasicAuthLevel=2 to map HTTP WebDAV drives.\n"
                "    Run 'fix-FileSizelimitInBytes-and-restart-WebClient.bat' as Administrator to fix."
            )
        return False
    except Exception as e:
        print(f"[!] Could not map drive {drive_letter}: {e}")
        return False


def unmount_windows_drive(drive_letter: str) -> bool:
    """Unmount Windows network drive."""
    cmd = ["net", "use", drive_letter, "/delete", "/y"]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
        return proc.returncode == 0
    except Exception:
        return False


def stop_mount(drive_letter: Optional[str] = "G:") -> None:
    """Unmount Google Drive and kill background server process if active."""
    drive_letter = normalize_drive_letter(drive_letter)
    print(f"[*] Unmounting drive {drive_letter}...")

    # Check state file
    state_file = get_mount_state_file(drive_letter)
    killed_proc = False
    if state_file.exists():
        try:
            data = json.loads(state_file.read_text(encoding="utf-8"))
            pid = data.get("pid")
            if pid and pid != os.getpid():
                # Terminate server process
                if os.name == "nt":
                    subprocess.run(["taskkill", "/PID", str(pid), "/F"], capture_output=True)
                else:
                    os.kill(pid, 15)
                killed_proc = True
        except Exception:
            pass
        clear_mount_state(drive_letter)

    # Disconnect Windows network drive
    unmount_windows_drive(drive_letter)

    print(f"[+] Successfully unmounted {drive_letter}")
    if killed_proc:
        print("[-] Stopped associated background WebDAV server process.")


def is_pid_alive(pid: int) -> bool:
    """Check whether a process with given PID is still running."""
    if pid <= 0:
        return False
    if os.name == "nt":
        try:
            res = subprocess.run(
                ["tasklist", "/FI", f"PID eq {pid}", "/NH"],
                capture_output=True,
                text=True,
                timeout=3,
            )
            return str(pid) in res.stdout
        except Exception:
            return False
    else:
        try:
            os.kill(pid, 0)
            return True
        except OSError:
            return False


def start_mount(
    drive_letter: Optional[str] = "G:",
    port: Optional[int] = None,
    no_drive: bool = False,
    force: bool = False,
    secrets_file: Optional[str] = None,
    token_file: Optional[str] = None,
) -> None:
    """Start WebDAV server and mount Virtual Root (My Drive + Shared with me)."""
    drive_letter = normalize_drive_letter(drive_letter)
    if not secrets_file or not token_file:
        resolved_s, resolved_t = resolve_auth_paths(secrets_file, token_file)
        secrets_file = secrets_file or resolved_s
        token_file = token_file or resolved_t

    # 1. Check if already running or mounted
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
                # Clean up stale state
                clear_mount_state(drive_letter)
        except Exception:
            clear_mount_state(drive_letter)

    if not already_running and os.name == "nt" and not no_drive:
        if os.path.exists(f"{drive_letter}\\"):
            already_running = True

    if already_running:
        if force:
            print(f"[*] Force option (-f/--force) specified.")
            print(f"[*] Unmounting existing drive {drive_letter} and terminating previous server...")
            stop_mount(drive_letter)
            time.sleep(1)
        else:
            pid_info = f" (PID: {existing_pid})" if existing_pid else ""
            print(f"[!] Error: Google Drive is already mounted or running on {drive_letter}{pid_info}.")
            print("    Aborting mount.")
            print(f"    - To unmount: google-drive umount {drive_letter}")
            print(f"    - To force remount: google-drive mount -f {drive_letter}")
            sys.exit(1)

    if port is None:
        port = find_available_port(18875)
        print(f"[*] Auto-detected available port: {port} (searching from 18875)")
    else:
        print(f"[*] Using specified port: {port}")

    if os.name == "nt":
        try:
            import ctypes
            ctypes.windll.kernel32.SetConsoleTitleW(f"Google Drive Mount ({drive_letter})")
        except Exception:
            pass

    print("=" * 60)
    print(" Google Drive WebDAV Mount Utility (Virtual Root)")
    print("=" * 60)
    print(f"[*] Target Drive : {drive_letter}")
    print(f"[*] Secrets file : {secrets_file}")
    print(f"[*] Token file   : {token_file}")

    client = GoogleDriveClient(secrets_file, token_file)

    # Trigger initial auth check
    print("[*] Connecting to Google Drive...")
    try:
        client.get_service()
    except Exception as e:
        print(f"[!] Authentication failed: {e}")
        sys.exit(1)

    # Setup WsgiDAV Provider (Always Virtual Root)
    provider = GoogleDriveDAVProvider(drive_client=client, root_mode="virtual")

    config = {
        "host": "127.0.0.1",
        "port": port,
        "mount_path": "",
        "provider_mapping": {"/": provider},
        "simple_dc": {"user_mapping": {"*": True}},
        "verbose": 1,
        "logging": {"enable": False},
    }

    app = WsgiDAVApp(config)
    server = wsgi.Server(("127.0.0.1", port), app)

    server_thread = threading.Thread(target=server.start, daemon=True)
    server_thread.start()

    time.sleep(1)

    webdav_url = f"http://127.0.0.1:{port}/"
    mounted_success = False

    # Mount Windows drive
    if os.name == "nt" and not no_drive:
        check_windows_webclient_settings()
        if mount_windows_drive(drive_letter, webdav_url):
            mounted_success = True
            save_mount_state(drive_letter, port, os.getpid(), webdav_url)

    print("\n" + "=" * 60)
    print(" Google Drive Mount Active")
    print(f" WebDAV URL  : {webdav_url}")
    if mounted_success:
        print(f" Local Drive : {drive_letter}\\")
        print(f"               ├── {drive_letter}\\My Drive\\")
        print(f"               └── {drive_letter}\\Shared with me\\")
    else:
        print(" (Drive letter not mapped; connect via WebDAV client or File Explorer)")
    print("=" * 60)
    print(f"To unmount from another terminal: google-drive umount {drive_letter}")
    print("Press Ctrl+C to stop and unmount...\n")

    def cleanup():
        print("\n[*] Shutting down...")
        if mounted_success:
            unmount_windows_drive(drive_letter)
            clear_mount_state(drive_letter)
        try:
            server.stop()
        except Exception:
            pass

    try:
        while server_thread.is_alive():
            time.sleep(0.5)
    except KeyboardInterrupt:
        pass
    finally:
        cleanup()
