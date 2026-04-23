from fastapi import FastAPI, HTTPException, Depends, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
import logging
import sys
from contextlib import asynccontextmanager
import aiohttp
from urllib.parse import urlparse

from app.config import settings
from app.models import (
    VideoDownloadRequest,
    VideoDownloadResponse,
    ErrorResponse,
    VideoQuality
)
from app.services.video_service import video_service
from app.utils.rate_limiter import check_rate_limit
from app.utils.validators import URLValidator

logging.basicConfig(
    level=logging.INFO if not settings.DEBUG else logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("🚀 Social Video Downloader API starting up...")
    logger.info(f"Debug mode: {settings.DEBUG}")
    yield
    logger.info("📱 Social Video Downloader API shutting down...")


app = FastAPI(
    title="Social Video Downloader API",
    version="2.0.0",
    description="Download videos from Facebook, YouTube, TikTok, Instagram, Twitter, Reddit, Vimeo, and more.",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

app.mount("/static", StaticFiles(directory="static"), name="static")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"Unhandled exception: {str(exc)}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"status": "error", "message": "Internal server error", "error_code": "INTERNAL_ERROR"}
    )


@app.get("/")
async def root():
    from fastapi.responses import FileResponse
    return FileResponse("static/index.html")


@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "version": "2.0.0",
        "service": "Social Video Downloader API",
        "supported_platforms": list(URLValidator.SUPPORTED_PLATFORMS.keys())
    }


@app.post("/download", response_model=VideoDownloadResponse)
async def download_video(
    request: VideoDownloadRequest,
    _: None = Depends(check_rate_limit)
):
    """
    Download video from any supported social media platform.
    - **url**: Video URL (Facebook, YouTube, TikTok, Instagram, Twitter, etc.)
    - **quality**: Preferred video quality (optional, default: best)
    """
    try:
        logger.info(f"Processing download request: {request.url}")
        result = await video_service.get_video_info(str(request.url), request.quality)

        return VideoDownloadResponse(
            status="success",
            video_info=result['video_info'],
            download_url=result['download_url'],
            available_formats=result['available_formats'],
            platform=result.get('platform', 'unknown')
        )
    except ValueError as e:
        logger.warning(f"Invalid request: {str(e)}")
        raise HTTPException(status_code=400, detail={"status": "error", "message": str(e), "error_code": "INVALID_REQUEST"})
    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail={"status": "error", "message": "Failed to process video", "error_code": "PROCESSING_ERROR"})


@app.get("/stream/{video_id}")
async def stream_video(video_id: str, url: str):
    """Stream video file directly through the server"""
    try:
        parsed_url = urlparse(url)
        if not parsed_url.scheme or not parsed_url.netloc:
            raise HTTPException(status_code=400, detail="Invalid URL")

        async def generate():
            timeout = aiohttp.ClientTimeout(total=600)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(url, headers={'User-Agent': 'Mozilla/5.0'}) as response:
                    if response.status != 200:
                        raise HTTPException(status_code=response.status, detail="Failed to fetch video")
                    async for chunk in response.content.iter_chunked(8192):
                        yield chunk

        return StreamingResponse(
            generate(),
            media_type="video/mp4",
            headers={
                "Content-Disposition": f'attachment; filename="{video_id}.mp4"',
                "Cache-Control": "no-cache",
                "Access-Control-Expose-Headers": "Content-Disposition"
            }
        )
    except Exception as e:
        logger.error(f"Stream error: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to stream video")


@app.post("/info", response_model=VideoDownloadResponse)
async def get_video_info(
    request: VideoDownloadRequest,
    _: None = Depends(check_rate_limit)
):
    """Get video metadata without download URL"""
    try:
        result = await video_service.get_video_info(str(request.url), request.quality)
        return VideoDownloadResponse(
            status="success",
            video_info=result['video_info'],
            available_formats=result['available_formats'],
            platform=result.get('platform', 'unknown')
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail={"status": "error", "message": str(e), "error_code": "INVALID_REQUEST"})


@app.get("/platforms")
async def get_supported_platforms():
    """Get list of supported social media platforms"""
    return {
        "status": "success",
        "platforms": list(URLValidator.SUPPORTED_PLATFORMS.keys()),
        "total": len(URLValidator.SUPPORTED_PLATFORMS),
        "note": "yt-dlp supports 1000+ additional sites beyond this list"
    }


@app.get("/qualities")
async def get_supported_qualities():
    """Get list of supported video qualities"""
    return {
        "status": "success",
        "qualities": [q.value for q in VideoQuality],
        "descriptions": {
            "best": "Best available quality",
            "worst": "Worst available quality",
            "360p": "360p resolution",
            "720p": "720p resolution",
            "1080p": "1080p resolution"
        }
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host=settings.HOST, port=settings.PORT, reload=settings.DEBUG)
