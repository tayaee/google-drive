from unittest.mock import MagicMock, patch
from google_drive.client import GoogleDriveClient
from google_drive.mount import clear_mount_state, get_active_mounts, save_mount_state


def test_get_my_drive_summary_mock():
    mock_service = MagicMock()
    mock_files = mock_service.files.return_value
    mock_list = mock_files.list.return_value
    mock_list.execute.return_value = {
        "files": [
            {"id": "1", "mimeType": "application/vnd.google-apps.folder"},
            {"id": "2", "mimeType": "application/vnd.google-apps.folder"},
            {"id": "3", "mimeType": "text/plain"},
        ],
        "nextPageToken": None,
    }

    client = GoogleDriveClient("dummy_secrets.json", "dummy_token.json")
    client._service = mock_service

    summary = client.get_my_drive_summary()
    assert summary["folders"] == 2
    assert summary["files"] == 1
    assert summary["total"] == 3


def test_get_active_mounts_empty():
    # If no mount state, returns empty list
    clear_mount_state("X:")
    active = get_active_mounts()
    # Check that X: is not in active
    assert not any(m.get("drive_letter") == "X:" for m in active)
