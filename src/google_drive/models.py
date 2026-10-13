"""Pydantic models for Google Drive status and CLI data structures."""

from typing import List, Optional
from pydantic import BaseModel, Field


class MyDriveSummary(BaseModel):
    """Summary of items in Google Drive (My Drive)."""

    folders: int = Field(0, description="Total folder count in My Drive")
    files: int = Field(0, description="Total file count in My Drive")
    total: int = Field(0, description="Total items (folders + files) in My Drive")


class ApiStatus(BaseModel):
    """Google Drive API connection and authentication status."""

    connected: bool = Field(..., description="Whether the Google Drive API is connected")
    status: str = Field(..., description="API connection status message (e.g. 'Connected', 'Error')")
    error: Optional[str] = Field(None, description="Error message if API connection failed")
    my_drive: Optional[MyDriveSummary] = Field(None, description="My Drive items count summary")


class MountInfo(BaseModel):
    """Details of an active Google Drive mount."""

    drive_letter: str = Field(..., description="Mapped Windows drive letter (e.g. 'G:')")
    drive_path: str = Field(..., description="Drive path (e.g. 'G:\\')")
    webdav_url: str = Field(..., description="WebDAV server URL")
    pid: Optional[int] = Field(None, description="Background process PID")
    port: Optional[int] = Field(None, description="WebDAV server port")


class MountStatus(BaseModel):
    """Status of Google Drive local mounts."""

    is_mounted: bool = Field(..., description="Whether at least one Google Drive mount is active")
    mounts: List[MountInfo] = Field(default_factory=list, description="List of active mounts")


class GoogleDriveStatus(BaseModel):
    """Overall status response for Google Drive."""

    api: ApiStatus = Field(..., description="Google Drive API connection and storage status")
    mount: MountStatus = Field(..., description="Local mount status")
