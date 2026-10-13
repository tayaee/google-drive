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


def test_sanitize_and_restore_filename():
    from google_drive.client import sanitize_filename, restore_filename

    raw = '2022/12/2: "Test"? <Draft> | Path\\File *'
    sanitized = sanitize_filename(raw)
    assert "/" not in sanitized
    assert "\\" not in sanitized
    assert ":" not in sanitized
    assert "*" not in sanitized
    assert "?" not in sanitized
    assert '"' not in sanitized
    assert "<" not in sanitized
    assert ">" not in sanitized
    assert "|" not in sanitized

    # Check fullwidth look-alikes
    assert "2022／12／2： ＂Test＂？ ＜Draft＞ ｜ Path＼File ＊" == sanitized

    # Check lossless restoration
    restored = restore_filename(sanitized)
    assert restored == raw


def test_make_unique_names_sanitizes_forbidden_chars():
    raw_items = [
        {"id": "1", "name": "2022/12/2   우리들병원 비용(9월) 신청", "mimeType": "application/vnd.google-apps.folder"},
        {"id": "2", "name": "Budget: 2026?*", "mimeType": "application/vnd.google-apps.spreadsheet"},
    ]
    unique = make_unique_names(raw_items)
    assert unique[0]["display_name"] == "2022／12／2   우리들병원 비용(9월) 신청"
    assert unique[1]["display_name"] == "Budget： 2026？＊.xlsx"


def test_shared_with_me_member_list_with_slashed_names():
    mock_client = MagicMock()
    raw_items = [
        {"id": "1", "name": "[교육청]학부모 Zoom활용 연수", "mimeType": "application/vnd.google-apps.folder"},
        {"id": "2", "name": "5 함지박 이야기마당", "mimeType": "application/vnd.google-apps.folder"},
        {"id": "3", "name": "2022/12/2   우리들병원 비용(9월) 신청", "mimeType": "application/vnd.google-apps.folder"},
        {"id": "4", "name": "Report: Final (v1.0).pdf", "mimeType": "application/pdf"},
    ]
    mock_client.list_shared_with_me.return_value = make_unique_names(raw_items)

    provider = GoogleDriveDAVProvider(drive_client=mock_client, root_mode="virtual")
    shared_res = provider.get_resource_inst("/Shared with me", {})
    assert shared_res is not None

    # This should succeed without AssertionError
    member_list = shared_res.get_member_list()
    assert len(member_list) == 4
    names = [m.get_display_name() for m in member_list]
    assert "2022／12／2   우리들병원 비용(9월) 신청" in names
    assert "Report： Final (v1.0).pdf" in names


def test_shared_with_me_subpath_resolution_and_traversal():
    mock_client = MagicMock()
    folder_item = {
        "id": "folder-123",
        "name": "2022/12/2   우리들병원 비용(9월) 신청",
        "mimeType": "application/vnd.google-apps.folder",
    }
    file_item = {
        "id": "file-456",
        "name": "Receipt: Nov.pdf",
        "mimeType": "application/pdf",
        "size": 1024,
    }
    mock_client.list_shared_with_me.return_value = make_unique_names([folder_item])
    mock_client.list_folder.return_value = make_unique_names([file_item])

    provider = GoogleDriveDAVProvider(drive_client=mock_client, root_mode="virtual")

    # Resolve folder
    folder_res = provider.get_resource_inst("/Shared with me/2022／12／2   우리들병원 비용(9월) 신청", {})
    assert folder_res is not None
    assert folder_res.folder_id == "folder-123"

    # Resolve file inside folder
    file_res = provider.get_resource_inst(
        "/Shared with me/2022／12／2   우리들병원 비용(9월) 신청/Receipt： Nov.pdf", {}
    )
    assert file_res is not None
    assert file_res.file_id == "file-456"

