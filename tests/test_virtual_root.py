from unittest.mock import MagicMock
from google_drive.client import make_unique_names
from google_drive.dav_provider import GoogleDriveDAVProvider, VirtualRootResource


def test_make_unique_names_deduplication():
    raw_items = [
        {"id": "1", "name": "document.txt", "mimeType": "text/plain"},
        {"id": "2", "name": "document.txt", "mimeType": "text/plain"},
        {"id": "3", "name": "photo.png", "mimeType": "image/png"},
    ]
    unique = make_unique_names(raw_items)
    display_names = [item["display_name"] for item in unique]
    assert display_names == ["document.txt", "document (2).txt", "photo.png"]


def test_make_unique_names_google_docs_extension():
    raw_items = [
        {"id": "1", "name": "Meeting Notes", "mimeType": "application/vnd.google-apps.document"},
        {"id": "2", "name": "Budget", "mimeType": "application/vnd.google-apps.spreadsheet"},
    ]
    unique = make_unique_names(raw_items)
    display_names = [item["display_name"] for item in unique]
    assert display_names == ["Meeting Notes.docx", "Budget.xlsx"]


def test_virtual_root_resource_members():
    mock_client = MagicMock()
    provider = GoogleDriveDAVProvider(drive_client=mock_client, root_mode="virtual")
    vroot = VirtualRootResource(path="/", environ={}, provider=provider)

    assert vroot.get_member_names() == ["My Drive", "Shared with me"]


def test_get_resource_inst_virtual_root():
    mock_client = MagicMock()
    provider = GoogleDriveDAVProvider(drive_client=mock_client, root_mode="virtual")

    # Root resource
    root_res = provider.get_resource_inst("/", {})
    assert root_res is not None
    assert isinstance(root_res, VirtualRootResource)

    # Sub-branches
    my_drive = provider.get_resource_inst("/My Drive", {})
    assert my_drive is not None
    assert my_drive.display_name == "My Drive"

    shared = provider.get_resource_inst("/Shared with me", {})
    assert shared is not None
    assert shared.display_name == "Shared with me"
