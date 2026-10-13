from datetime import datetime, timezone
from google_drive.cli import format_iso8601_with_tz, format_ls_l_entry


def test_format_iso8601_with_tz():
    utc_str = "2025-08-12T10:20:30.000Z"
    formatted = format_iso8601_with_tz(utc_str)

    # Must be valid ISO 8601
    dt = datetime.fromisoformat(formatted)
    assert dt.tzinfo is not None, "Timestamp must include timezone info"
    # Check that + or - tz offset is in the formatted string
    assert "+" in formatted or "-" in formatted


def test_format_ls_l_entry_directory():
    item = {
        "id": "folder123",
        "name": "Projects",
        "display_name": "Projects",
        "mimeType": "application/vnd.google-apps.folder",
        "modifiedTime": "2025-08-12T10:20:30.000Z",
    }
    line = format_ls_l_entry(item)
    assert line.startswith("drwxr-xr-x")
    assert "user group" in line
    assert "Projects/" in line
    assert " - " in line


def test_format_ls_l_entry_file():
    item = {
        "id": "file123",
        "name": "report.pdf",
        "display_name": "report.pdf",
        "mimeType": "application/pdf",
        "size": "1048576",
        "modifiedTime": "2025-08-12T10:20:30.000Z",
    }
    line = format_ls_l_entry(item)
    assert line.startswith("-rw-r--r--")
    assert "user group" in line
    assert "1048576" in line
    assert "report.pdf" in line
    assert not line.endswith("/")


def test_cmd_dir_shared_with_me_subpath(capsys):
    import argparse
    from unittest.mock import patch
    from google_drive.cli import cmd_dir

    with patch("google_drive.cli.GoogleDriveClient") as mock_client_cls:
        client = mock_client_cls.return_value
        client.list_shared_with_me.return_value = [
            {"id": "shared-f1", "name": "Team Docs", "display_name": "Team Docs", "mimeType": "application/vnd.google-apps.folder"}
        ]
        client.list_folder.return_value = [
            {"id": "doc1", "name": "guide.docx", "display_name": "guide.docx", "mimeType": "application/vnd.openxmlformats-officedocument.wordprocessingml.document", "size": 2048, "modifiedTime": "2026-01-01T00:00:00Z"}
        ]

        args = argparse.Namespace(
            remote_path="Shared with me/Team Docs",
            limit=50,
            secrets_file=None,
            token_file=None,
        )
        cmd_dir(args)

        out = capsys.readouterr().out
        assert "guide.docx" in out
        client.list_folder.assert_called_with("shared-f1")


def test_cmd_dir_my_drive_prefix(capsys):
    import argparse
    from unittest.mock import patch
    from google_drive.cli import cmd_dir

    with patch("google_drive.cli.GoogleDriveClient") as mock_client_cls:
        client = mock_client_cls.return_value
        client.resolve_path.return_value = "folder-sub"
        client.list_folder.return_value = [
            {"id": "file1", "name": "notes.txt", "display_name": "notes.txt", "mimeType": "text/plain", "size": 100, "modifiedTime": "2026-01-01T00:00:00Z"}
        ]

        args = argparse.Namespace(
            remote_path="My Drive/Work",
            limit=50,
            secrets_file=None,
            token_file=None,
        )
        cmd_dir(args)

        out = capsys.readouterr().out
        assert "notes.txt" in out
        client.resolve_path.assert_called_with("Work")

