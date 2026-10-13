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
