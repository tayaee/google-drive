# Google Drive WebDAV Mount

Mount Google Drive ("My Drive" and "Shared with me") as a local Windows drive (`G:`).

## 1. Prerequisites (Credentials)

Download your OAuth client credentials (`client_secrets.json`) from Google Cloud Console and place it at:
- `%USERPROFILE%\.config\google-drive\client_secrets.json`

## 2. Usage

| Task | Command | Description |
| :--- | :--- | :--- |
| **Install** | `install.bat` | Install tool via `uv tool` |
| **Status Check** | `status.bat` | Check API connection and mount status |
| **Mount** | `mount.bat` | Mount to `G:` drive |
| **Unmount** | `umount.bat` | Unmount `G:` drive |

---

### Note: Remove Windows WebDAV Transfer Limit
To increase the default file size transfer limit (~50MB) to 4GB and enable HTTP WebDAV mounts, run the following script once as Administrator:
- `scripts\fix-FileSizelimitInBytes-and-restart-WebClient.bat`
