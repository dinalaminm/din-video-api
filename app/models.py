from pydantic import BaseModel, HttpUrl
from typing import Optional, List, Any
from enum import Enum


class VideoQuality(str, Enum):
    BEST = "best"
    WORST = "worst"
    P360 = "360p"
    P720 = "720p"
    P1080 = "1080p"


class VideoDownloadRequest(BaseModel):
    url: HttpUrl
    quality: Optional[VideoQuality] = VideoQuality.BEST

    class Config:
        schema_extra = {
            "example": {
                "url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
                "quality": "720p"
            }
        }


class VideoInfo(BaseModel):
    title: str
    duration: Optional[float] = None
    thumbnail: Optional[str] = None
    uploader: Optional[str] = None
    view_count: Optional[int] = None
    upload_date: Optional[str] = None


class VideoFormat(BaseModel):
    quality: str
    format_id: str
    ext: str
    filesize: Optional[int] = None
    url: str


class VideoDownloadResponse(BaseModel):
    status: str
    message: Optional[str] = None
    video_info: Optional[VideoInfo] = None
    download_url: Optional[str] = None
    available_formats: Optional[List[VideoFormat]] = None
    platform: Optional[str] = None


class ErrorResponse(BaseModel):
    status: str = "error"
    message: str
    error_code: Optional[str] = None
