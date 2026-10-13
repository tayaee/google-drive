# Google Drive CLI & WebDAV Mount

A lightweight CLI tool to mount Google Drive ("My Drive" and "Shared with me") as a local Windows drive or WebDAV server.

## Quickstart

### 1. Credentials
Download your OAuth 2.0 client credentials (`client_secrets.json`) from [Google Cloud Console](https://console.cloud.google.com/) and save it to:
- `%USERPROFILE%\.config\google-drive\client_secrets.json`

*(Generated tokens will also be saved to `token.json` in the same directory.)*

### 2. Install
```cmd
.\install.bat

# Or via uv directly
uv tool install --force .
```

### 3. Mount
```bash
# Mount to G: drive (default)
google-drive mount

# Or specify a drive letter
google-drive mount Z:
```

---

## Usage

| Command | Description |
| :--- | :--- |
| `google-drive mount [DRIVE]` | Mount drive (default: `G:`, use `-f` to force remount, `--port` or `-p` for custom port) |
| `google-drive status [-j]` | Check API connection and mount status (supports `--json`) |
| `google-drive umount [DRIVE]` | Unmount drive |
| `google-drive dir [PATH]` | List files in `ls -l` format (`list` is an alias) |
| `google-drive auth [-f]` | Verify or force OAuth authentication |

### Examples

```bash
# Mount with a custom port
google-drive mount G: --port 18875

# Check status in JSON format
google-drive status --json

# Unmount
google-drive umount G:

# List root or shared folder
google-drive dir
google-drive dir "Shared with me"
google-drive dir "Projects" -n 50
```

---

## Windows WebDAV Setup & 4GB Limit Fix

Windows WebClient blocks unencrypted HTTP WebDAV by default and limits file transfers to ~50 MB.
Run `fix-FileSizelimitInBytes-and-restart-WebClient.bat` as Administrator to enable HTTP drive mounting (`BasicAuthLevel=2`) and raise the file limit to 4GB.
