from datetime import datetime
import io
import logging
import time
from typing import Any, Dict, List, Optional

from wsgidav import util
from wsgidav.dav_provider import DAVCollection, DAVNonCollection, DAVProvider

from google_drive.client import (
    FOLDER_MIME_TYPE,
    GOOGLE_DOCS_EXPORT_MAP,
    GoogleDriveClient,
    sanitize_filename,
)

logger = logging.getLogger("google_drive.dav")


def parse_rfc3339_to_epoch(date_str: Optional[str]) -> float:
    if not date_str:
        return time.time()
    try:
        dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
        return dt.timestamp()
    except Exception:
        return time.time()


class GoogleDriveDAVProvider(DAVProvider):
    """WsgiDAV Provider that mounts Google Drive with Virtual Root support."""

    def __init__(
        self,
        drive_client: GoogleDriveClient,
        root_mode: str = "virtual",  # "virtual", "shared_with_me", or "folder"
        target_folder_id: str = "root",
        display_name: str = "Google Drive",
    ):
        super().__init__()
        self.drive_client = drive_client
        self.root_mode = root_mode
        self.target_folder_id = target_folder_id
        self.display_name = display_name

    def get_resource_inst(self, path: str, environ: dict) -> Optional[Any]:
        """Resolve DAV URI path to appropriate resource."""
        path = "/" + path.strip("/") if path else "/"

        # Case 1: Specific root mode: shared_with_me
        if self.root_mode == "shared_with_me":
            if path == "/":
                return SharedWithMeResource(
                    path=path,
                    environ=environ,
                    provider=self,
                    display_name=self.display_name,
                )
            # Subpaths under shared_with_me root
            return self._resolve_shared_with_me_subpath(path[1:], path, environ)

        # Case 2: Specific folder root mode
        if self.root_mode == "folder":
            if path == "/":
                return GDriveFolderResource(
                    path=path,
                    environ=environ,
                    provider=self,
                    folder_id=self.target_folder_id,
                    display_name=self.display_name,
                    modified_time=time.time(),
                )
            return self._walk_folder_segments(self.target_folder_id, path.split("/")[1:], path, environ)

        # Case 3: Virtual Root mode (Default)
        # Root /
        if path == "/":
            return VirtualRootResource(path=path, environ=environ, provider=self)

        segments = [s for s in path.split("/") if s]
        top_branch = segments[0]
        remaining = segments[1:]

        # Branch A: /My Drive
        if top_branch.lower() == "my drive":
            if not remaining:
                return GDriveFolderResource(
                    path=path,
                    environ=environ,
                    provider=self,
                    folder_id="root",
                    display_name="My Drive",
                    modified_time=time.time(),
                )
            return self._walk_folder_segments("root", remaining, path, environ)

        # Branch B: /Shared with me
        if top_branch.lower() == "shared with me":
            if not remaining:
                return SharedWithMeResource(
                    path=path,
                    environ=environ,
                    provider=self,
                    display_name="Shared with me",
                )
            return self._resolve_shared_with_me_subpath("/".join(remaining), path, environ)

        return None

    def _resolve_shared_with_me_subpath(self, rel_path: str, full_path: str, environ: dict) -> Optional[Any]:
        """Resolve a path inside 'Shared with me'."""
        segments = [s for s in rel_path.split("/") if s]
        if not segments:
            return None

        # Level 1: Find item in shared_with_me list
        top_name = segments[0]
        try:
            shared_items = self.drive_client.list_shared_with_me()
        except Exception as e:
            logger.warning(f"Failed to list shared_with_me: {e}")
            return None

        matched_item = None
        for item in shared_items:
            disp = item.get("display_name", "")
            raw = item.get("name", "")
            if disp == top_name or raw == top_name or sanitize_filename(raw) == top_name:
                matched_item = item
                break

        if not matched_item:
            return None

        if len(segments) == 1:
            if matched_item.get("mimeType") == FOLDER_MIME_TYPE:
                return GDriveFolderResource(
                    path=full_path,
                    environ=environ,
                    provider=self,
                    folder_id=matched_item["id"],
                    display_name=matched_item.get("display_name", matched_item["name"]),
                    modified_time=parse_rfc3339_to_epoch(matched_item.get("modifiedTime")),
                )
            else:
                return GDriveFileResource(
                    path=full_path,
                    environ=environ,
                    provider=self,
                    item=matched_item,
                )

        # Deeper levels inside a shared folder
        if matched_item.get("mimeType") != FOLDER_MIME_TYPE:
            return None

        return self._walk_folder_segments(matched_item["id"], segments[1:], full_path, environ)

    def _walk_folder_segments(
        self,
        start_folder_id: str,
        segments: List[str],
        full_path: str,
        environ: dict,
    ) -> Optional[Any]:
        """Walk nested folder segments from a given start folder ID."""
        current_folder_id = start_folder_id
        matched_item: Optional[Dict[str, Any]] = None

        for idx, seg in enumerate(segments):
            try:
                items = self.drive_client.list_folder(current_folder_id)
            except Exception as e:
                logger.warning(f"Failed to list folder {current_folder_id}: {e}")
                return None

            found = None
            for item in items:
                disp = item.get("display_name", "")
                raw = item.get("name", "")
                if disp == seg or raw == seg or sanitize_filename(raw) == seg:
                    found = item
                    break

            if not found:
                return None

            is_last = (idx == len(segments) - 1)
            is_folder = found.get("mimeType") == FOLDER_MIME_TYPE

            if is_last:
                matched_item = found
                break
            else:
                if not is_folder:
                    return None
                current_folder_id = found["id"]

        if not matched_item:
            return None

        if matched_item.get("mimeType") == FOLDER_MIME_TYPE:
            return GDriveFolderResource(
                path=full_path,
                environ=environ,
                provider=self,
                folder_id=matched_item["id"],
                display_name=matched_item.get("display_name", matched_item["name"]),
                modified_time=parse_rfc3339_to_epoch(matched_item.get("modifiedTime")),
            )
        else:
            return GDriveFileResource(
                path=full_path,
                environ=environ,
                provider=self,
                item=matched_item,
            )


class VirtualRootResource(DAVCollection):
    """Virtual container hosting 'My Drive' and 'Shared with me'."""

    def __init__(self, path: str, environ: dict, provider: GoogleDriveDAVProvider):
        environ = dict(environ)
        environ["wsgidav.provider"] = provider
        super().__init__(path, environ)
        self.provider = provider
        self.display_name = "Google Drive"
        self.modified_time = time.time()

    def get_display_name(self) -> str:
        return self.display_name

    def get_last_modified(self) -> float:
        return self.modified_time

    def get_creation_date(self) -> float:
        return self.modified_time

    def get_member_names(self) -> List[str]:
        return ["My Drive", "Shared with me"]

    def get_member(self, name: str) -> Optional[Any]:
        child_path = util.join_uri(self.path, name)
        return self.provider.get_resource_inst(child_path, self.environ)


class SharedWithMeResource(DAVCollection):
    """Represents the 'Shared with me' virtual folder."""

    def __init__(self, path: str, environ: dict, provider: GoogleDriveDAVProvider, display_name: str = "Shared with me"):
        environ = dict(environ)
        environ["wsgidav.provider"] = provider
        super().__init__(path, environ)
        self.provider = provider
        self.display_name = display_name
        self.modified_time = time.time()

    def get_display_name(self) -> str:
        return self.display_name

    def get_last_modified(self) -> float:
        return self.modified_time

    def get_creation_date(self) -> float:
        return self.modified_time

    def get_member_names(self) -> List[str]:
        try:
            items = self.provider.drive_client.list_shared_with_me()
            return [item.get("display_name", item["name"]) for item in items]
        except Exception as e:
            logger.warning(f"Failed to list Shared with me members: {e}")
            return []

    def get_member(self, name: str) -> Optional[Any]:
        child_path = util.join_uri(self.path, name)
        return self.provider.get_resource_inst(child_path, self.environ)

    def get_member_list(self) -> List[Any]:
        """Directly construct member resources to guarantee no missing members and maximize performance."""
        try:
            items = self.provider.drive_client.list_shared_with_me()
        except Exception as e:
            logger.warning(f"Failed to list Shared with me member list: {e}")
            return []

        members = []
        for item in items:
            name = item.get("display_name", item["name"])
            child_path = util.join_uri(self.path, name)
            if item.get("mimeType") == FOLDER_MIME_TYPE:
                res = GDriveFolderResource(
                    path=child_path,
                    environ=self.environ,
                    provider=self.provider,
                    folder_id=item["id"],
                    display_name=name,
                    modified_time=parse_rfc3339_to_epoch(item.get("modifiedTime")),
                )
            else:
                res = GDriveFileResource(
                    path=child_path,
                    environ=self.environ,
                    provider=self.provider,
                    item=item,
                )
            members.append(res)
        return members


class GDriveFolderResource(DAVCollection):
    """Represents a standard Google Drive directory/folder."""

    def __init__(
        self,
        path: str,
        environ: dict,
        provider: GoogleDriveDAVProvider,
        folder_id: str,
        display_name: str,
        modified_time: float,
    ):
        environ = dict(environ)
        environ["wsgidav.provider"] = provider
        super().__init__(path, environ)
        self.provider = provider
        self.folder_id = folder_id
        self.display_name = display_name
        self.modified_time = modified_time

    def get_display_name(self) -> str:
        return self.display_name

    def get_last_modified(self) -> float:
        return self.modified_time

    def get_creation_date(self) -> float:
        return self.modified_time

    def get_member_names(self) -> List[str]:
        try:
            items = self.provider.drive_client.list_folder(self.folder_id)
            return [item.get("display_name", item["name"]) for item in items]
        except Exception as e:
            logger.warning(f"get_member_names error: {e}")
            return []

    def get_member(self, name: str) -> Optional[Any]:
        child_path = util.join_uri(self.path, name)
        return self.provider.get_resource_inst(child_path, self.environ)

    def get_member_list(self) -> List[Any]:
        """Directly construct member resources to guarantee no missing members and maximize performance."""
        try:
            items = self.provider.drive_client.list_folder(self.folder_id)
        except Exception as e:
            logger.warning(f"get_member_list error: {e}")
            return []

        members = []
        for item in items:
            name = item.get("display_name", item["name"])
            child_path = util.join_uri(self.path, name)
            if item.get("mimeType") == FOLDER_MIME_TYPE:
                res = GDriveFolderResource(
                    path=child_path,
                    environ=self.environ,
                    provider=self.provider,
                    folder_id=item["id"],
                    display_name=name,
                    modified_time=parse_rfc3339_to_epoch(item.get("modifiedTime")),
                )
            else:
                res = GDriveFileResource(
                    path=child_path,
                    environ=self.environ,
                    provider=self.provider,
                    item=item,
                )
            members.append(res)
        return members


class GDriveFileResource(DAVNonCollection):
    """Represents a Google Drive file."""

    def __init__(
        self,
        path: str,
        environ: dict,
        provider: GoogleDriveDAVProvider,
        item: Dict[str, Any],
    ):
        environ = dict(environ)
        environ["wsgidav.provider"] = provider
        super().__init__(path, environ)
        self.provider = provider
        self.item = item
        self.file_id = item["id"]
        self.mime_type = item.get("mimeType", "application/octet-stream")
        self.display_name = item.get("display_name", item.get("name", ""))
        self.modified_time = parse_rfc3339_to_epoch(item.get("modifiedTime"))
        self.etag = item.get("md5Checksum") or f'"{self.file_id}-{int(self.modified_time)}"'

        # Size estimation for Google Docs vs binary files
        if self.mime_type in GOOGLE_DOCS_EXPORT_MAP:
            # Google Docs don't have static size in drive; default estimation or 0
            self.size = int(item.get("size") or 0)
        else:
            self.size = int(item.get("size", 0))

    def get_display_name(self) -> str:
        return self.display_name

    def get_content_length(self) -> int:
        return self.size

    def get_content_type(self) -> str:
        return self.mime_type

    def get_last_modified(self) -> float:
        return self.modified_time

    def get_creation_date(self) -> float:
        return self.modified_time

    def get_etag(self) -> str:
        return self.etag

    def support_etag(self) -> bool:
        return True

    def get_content(self) -> io.BytesIO:
        """Download and return stream for WebDAV GET / xcopy requests."""
        return self.provider.drive_client.download_file(self.file_id, self.mime_type)
