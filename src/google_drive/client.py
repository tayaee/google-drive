import io
import os
import time
from typing import Any, Dict, List, Optional, Tuple

from googleapiclient.discovery import Resource, build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaIoBaseDownload

from google_drive.auth import backup_expired_token, get_credentials

FOLDER_MIME_TYPE = "application/vnd.google-apps.folder"

# Automatic export mappings for Google Docs / Sheets / Slides
GOOGLE_DOCS_EXPORT_MAP: Dict[str, Tuple[str, str]] = {
    "application/vnd.google-apps.document": (
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        ".docx",
    ),
    "application/vnd.google-apps.spreadsheet": (
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        ".xlsx",
    ),
    "application/vnd.google-apps.presentation": (
        "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        ".pptx",
    ),
    "application/vnd.google-apps.drawing": ("application/pdf", ".pdf"),
}

# Windows forbidden characters mapped to Unicode fullwidth look-alikes
WINDOWS_FORBIDDEN_CHAR_MAP: Dict[str, str] = {
    "/": "／",   # U+FF0F Fullwidth Solidus
    "\\": "＼",  # U+FF3C Fullwidth Reverse Solidus
    ":": "：",   # U+FF1A Fullwidth Colon
    "*": "＊",   # U+FF0A Fullwidth Asterisk
    "?": "？",   # U+FF1F Fullwidth Question Mark
    '"': "＂",   # U+FF02 Fullwidth Quotation Mark
    "<": "＜",   # U+FF1C Fullwidth Less-Than Sign
    ">": "＞",   # U+FF1E Fullwidth Greater-Than Sign
    "|": "｜",   # U+FF5C Fullwidth Vertical Line
}

REVERSE_WINDOWS_CHAR_MAP: Dict[str, str] = {
    v: k for k, v in WINDOWS_FORBIDDEN_CHAR_MAP.items()
}


def sanitize_filename(name: str) -> str:
    """Sanitize filename by mapping Windows-forbidden characters to fullwidth look-alikes."""
    if not name:
        return "Untitled"
    for forbidden, replacement in WINDOWS_FORBIDDEN_CHAR_MAP.items():
        if forbidden in name:
            name = name.replace(forbidden, replacement)
    return name


def restore_filename(name: str) -> str:
    """Restore sanitized filename back to its original characters."""
    if not name:
        return name
    for replacement, original in REVERSE_WINDOWS_CHAR_MAP.items():
        if replacement in name:
            name = name.replace(replacement, original)
    return name


def make_unique_names(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Deduplicate names, sanitize Windows forbidden characters, and append extensions for Google Docs."""
    name_counts: Dict[str, int] = {}
    result = []

    for item in items:
        item_copy = dict(item)
        raw_name = item_copy.get("name", "Untitled")
        mime = item_copy.get("mimeType", "")

        # 1. Sanitize Windows forbidden characters (e.g. '/' -> '／')
        sanitized_name = sanitize_filename(raw_name)

        # 2. Append extension for Google Docs if not present
        if mime in GOOGLE_DOCS_EXPORT_MAP:
            _, ext = GOOGLE_DOCS_EXPORT_MAP[mime]
            if not sanitized_name.lower().endswith(ext):
                sanitized_name = f"{sanitized_name}{ext}"

        # 3. Deduplicate
        lower_name = sanitized_name.lower()
        if lower_name in name_counts:
            name_counts[lower_name] += 1
            count = name_counts[lower_name]
            stem, ext = os.path.splitext(sanitized_name)
            unique_name = f"{stem} ({count}){ext}"
        else:
            name_counts[lower_name] = 1
            unique_name = sanitized_name

        item_copy["display_name"] = unique_name
        result.append(item_copy)

    return result


class GoogleDriveClient:
    """Wrapper around Google Drive API v3."""

    def __init__(self, secrets_file: str, token_file: str):
        self.secrets_file = secrets_file
        self.token_file = token_file
        self._service: Optional[Resource] = None
        self._folder_cache: Dict[str, Tuple[float, List[Dict[str, Any]]]] = {}
        self._cache_ttl = 30.0  # seconds

    def get_service(self) -> Resource:
        if self._service is None:
            creds = get_credentials(self.secrets_file, self.token_file)
            self._service = build("drive", "v3", credentials=creds)
        return self._service

    def refresh_service_after_expiry(self) -> Resource:
        """Called when an API call fails due to invalid/expired token."""
        print("[!] API authorization error. Backing up token and re-authenticating...")
        backup_expired_token(self.token_file)
        self._service = None
        return self.get_service()

    def resolve_path(self, remote_path: Optional[str]) -> str:
        """Resolve a slash-separated remote path to a Google Drive folder ID.

        Returns 'root' if empty or '/'.
        """
        if not remote_path or remote_path.strip() in ("", "/"):
            return "root"

        segments = [s for s in remote_path.strip().replace("\\", "/").split("/") if s]
        current_id = "root"

        service = self.get_service()
        for seg in segments:
            query = (
                f"'{current_id}' in parents and "
                f"name = '{seg}' and "
                f"mimeType = '{FOLDER_MIME_TYPE}' and "
                f"trashed = false"
            )
            try:
                res = (
                    service.files()
                    .list(
                        q=query,
                        fields="files(id, name)",
                        pageSize=10,
                        supportsAllDrives=True,
                        includeItemsFromAllDrives=True,
                    )
                    .execute()
                )
            except HttpError as e:
                if e.resp.status in (401, 403):
                    service = self.refresh_service_after_expiry()
                    res = (
                        service.files()
                        .list(
                            q=query,
                            fields="files(id, name)",
                            pageSize=10,
                            supportsAllDrives=True,
                            includeItemsFromAllDrives=True,
                        )
                        .execute()
                    )
                else:
                    raise

            files = res.get("files", [])
            if not files:
                raise FileNotFoundError(
                    f"Remote folder '{seg}' not found in parent '{current_id}' (path: {remote_path})"
                )
            current_id = files[0]["id"]

        return current_id

    def get_my_drive_summary(self) -> Dict[str, int]:
        """Fetch count of folders and files directly under My Drive (root) using minimal fields."""
        service = self.get_service()
        query = "'root' in parents and trashed = false"
        fields = "nextPageToken, files(id, mimeType)"

        folders_count = 0
        files_count = 0
        page_token = None

        while True:
            try:
                resp = (
                    service.files()
                    .list(
                        q=query,
                        fields=fields,
                        pageToken=page_token,
                        pageSize=1000,
                        supportsAllDrives=True,
                        includeItemsFromAllDrives=True,
                    )
                    .execute()
                )
            except HttpError as e:
                if e.resp.status in (401, 403):
                    service = self.refresh_service_after_expiry()
                    resp = (
                        service.files()
                        .list(
                            q=query,
                            fields=fields,
                            pageToken=page_token,
                            pageSize=1000,
                            supportsAllDrives=True,
                            includeItemsFromAllDrives=True,
                        )
                        .execute()
                    )
                else:
                    raise

            for item in resp.get("files", []):
                if item.get("mimeType") == FOLDER_MIME_TYPE:
                    folders_count += 1
                else:
                    files_count += 1

            page_token = resp.get("nextPageToken")
            if not page_token:
                break

        return {
            "folders": folders_count,
            "files": files_count,
            "total": folders_count + files_count,
        }

    def list_folder(self, parent_id: str, force_refresh: bool = False) -> List[Dict[str, Any]]:
        """List files and folders inside a given parent folder ID."""
        now = time.time()
        if not force_refresh and parent_id in self._folder_cache:
            cache_time, items = self._folder_cache[parent_id]
            if now - cache_time < self._cache_ttl:
                return items

        service = self.get_service()
        query = f"'{parent_id}' in parents and trashed = false"
        fields = "nextPageToken, files(id, name, mimeType, size, modifiedTime, md5Checksum)"

        items: List[Dict[str, Any]] = []
        page_token = None

        while True:
            try:
                resp = (
                    service.files()
                    .list(
                        q=query,
                        fields=fields,
                        pageToken=page_token,
                        pageSize=100,
                        supportsAllDrives=True,
                        includeItemsFromAllDrives=True,
                        orderBy="folder,name_natural",
                    )
                    .execute()
                )
            except HttpError as e:
                if e.resp.status in (401, 403):
                    service = self.refresh_service_after_expiry()
                    resp = (
                        service.files()
                        .list(
                            q=query,
                            fields=fields,
                            pageToken=page_token,
                            pageSize=100,
                            supportsAllDrives=True,
                            includeItemsFromAllDrives=True,
                            orderBy="folder,name_natural",
                        )
                        .execute()
                    )
                else:
                    raise

            items.extend(resp.get("files", []))
            page_token = resp.get("nextPageToken")
            if not page_token:
                break

        unique_items = make_unique_names(items)
        self._folder_cache[parent_id] = (now, unique_items)
        return unique_items

    def list_shared_with_me(self, force_refresh: bool = False) -> List[Dict[str, Any]]:
        """List files and folders shared with the user."""
        now = time.time()
        cache_key = "__shared_with_me__"
        if not force_refresh and cache_key in self._folder_cache:
            cache_time, items = self._folder_cache[cache_key]
            if now - cache_time < self._cache_ttl:
                return items

        service = self.get_service()
        query = "sharedWithMe = true and trashed = false"
        fields = "nextPageToken, files(id, name, mimeType, size, modifiedTime, md5Checksum)"

        items: List[Dict[str, Any]] = []
        page_token = None

        while True:
            try:
                resp = (
                    service.files()
                    .list(
                        q=query,
                        fields=fields,
                        pageToken=page_token,
                        pageSize=100,
                        supportsAllDrives=True,
                        includeItemsFromAllDrives=True,
                        orderBy="folder,name_natural",
                    )
                    .execute()
                )
            except HttpError as e:
                if e.resp.status in (401, 403):
                    service = self.refresh_service_after_expiry()
                    resp = (
                        service.files()
                        .list(
                            q=query,
                            fields=fields,
                            pageToken=page_token,
                            pageSize=100,
                            supportsAllDrives=True,
                            includeItemsFromAllDrives=True,
                            orderBy="folder,name_natural",
                        )
                        .execute()
                    )
                else:
                    raise

            items.extend(resp.get("files", []))
            page_token = resp.get("nextPageToken")
            if not page_token:
                break

        unique_items = make_unique_names(items)
        self._folder_cache[cache_key] = (now, unique_items)
        return unique_items

    def get_file_metadata(self, file_id: str) -> Dict[str, Any]:
        """Fetch metadata for a single file or folder."""
        service = self.get_service()
        fields = "id, name, mimeType, size, modifiedTime, md5Checksum, parents"
        try:
            return (
                service.files()
                .get(fileId=file_id, fields=fields, supportsAllDrives=True)
                .execute()
            )
        except HttpError as e:
            if e.resp.status in (401, 403):
                service = self.refresh_service_after_expiry()
                return (
                    service.files()
                    .get(fileId=file_id, fields=fields, supportsAllDrives=True)
                    .execute()
                )
            raise

    def download_file(self, file_id: str, mime_type: str = "") -> io.BytesIO:
        """Download binary content of a file or export Google Doc."""
        service = self.get_service()
        stream = io.BytesIO()

        # Handle Google Docs export
        if mime_type in GOOGLE_DOCS_EXPORT_MAP:
            export_mime, _ = GOOGLE_DOCS_EXPORT_MAP[mime_type]
            try:
                request = service.files().export_media(fileId=file_id, mimeType=export_mime)
                downloader = MediaIoBaseDownload(stream, request)
                done = False
                while not done:
                    _, done = downloader.next_chunk()
                stream.seek(0)
                return stream
            except HttpError as e:
                if e.resp.status in (401, 403):
                    service = self.refresh_service_after_expiry()
                    request = service.files().export_media(fileId=file_id, mimeType=export_mime)
                    downloader = MediaIoBaseDownload(stream, request)
                    done = False
                    while not done:
                        _, done = downloader.next_chunk()
                    stream.seek(0)
                    return stream
                raise

        # Standard file download
        try:
            request = service.files().get_media(fileId=file_id, supportsAllDrives=True)
            downloader = MediaIoBaseDownload(stream, request)
            done = False
            while not done:
                _, done = downloader.next_chunk()
            stream.seek(0)
            return stream
        except HttpError as e:
            if e.resp.status in (401, 403):
                service = self.refresh_service_after_expiry()
                request = service.files().get_media(fileId=file_id, supportsAllDrives=True)
                downloader = MediaIoBaseDownload(stream, request)
                done = False
                while not done:
                    _, done = downloader.next_chunk()
                stream.seek(0)
                return stream
            raise
