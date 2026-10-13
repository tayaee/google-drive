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


def test_get_drive_status_pydantic_model():
    from google_drive.cli import get_drive_status
    from google_drive.models import GoogleDriveStatus

    with patch("google_drive.cli.GoogleDriveClient") as mock_client_cls, \
         patch("google_drive.cli.get_active_mounts") as mock_active:
        mock_instance = mock_client_cls.return_value
        mock_instance.get_my_drive_summary.return_value = {
            "folders": 5,
            "files": 12,
            "total": 17,
        }
        mock_active.return_value = [
            {
                "drive_letter": "G:",
                "port": 18875,
                "pid": 12345,
                "webdav_url": "http://127.0.0.1:18875/",
            }
        ]

        status = get_drive_status("secrets.json", "token.json")
        assert isinstance(status, GoogleDriveStatus)
        assert status.api.connected is True
        assert status.api.status == "Connected"
        assert status.api.my_drive is not None
        assert status.api.my_drive.folders == 5
        assert status.api.my_drive.files == 12
        assert status.api.my_drive.total == 17
        assert status.mount.is_mounted is True
        assert len(status.mount.mounts) == 1
        assert status.mount.mounts[0].drive_letter == "G:"
        assert status.mount.mounts[0].port == 18875
        assert status.mount.mounts[0].pid == 12345


def test_cmd_status_json_output(capsys):
    import argparse
    import json
    from google_drive.cli import cmd_status

    with patch("google_drive.cli.GoogleDriveClient") as mock_client_cls, \
         patch("google_drive.cli.get_active_mounts") as mock_active:
        mock_instance = mock_client_cls.return_value
        mock_instance.get_my_drive_summary.return_value = {
            "folders": 3,
            "files": 7,
            "total": 10,
        }
        mock_active.return_value = []

        args = argparse.Namespace(
            secrets_file=None,
            token_file=None,
            json=True,
        )
        cmd_status(args)

        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert data["api"]["connected"] is True
        assert data["api"]["my_drive"]["folders"] == 3
        assert data["mount"]["is_mounted"] is False
        assert data["mount"]["mounts"] == []

