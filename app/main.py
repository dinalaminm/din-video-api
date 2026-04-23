from fastapi import FastAPI, HTTPException, Depends, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse, FileResponse as FFileResponse
from fastapi.staticfiles import StaticFiles
import logging
import sys
import os
import asyncio
import tempfile
from contextlib import asynccontextmanager
import aiohttp
from urllib.parse import urlparse

from app.config import settings
from app.models import VideoDownloadRequest, VideoDownloadResponse, VideoQuality
from app.services.video_service import video_service
from app.utils.rate_limiter import check_rate_limit
from app.utils.validators import URLValidator

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

# Proxy headers to pass to CDN when streaming
PROXY_HEADERS = {
    'User-Agent': (
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
        'AppleWebKit/537.36 (KHTML, like Gecko) '
        'Chrome/120.0.0.0 Safari/537.36'
    ),
    'Accept': '*/*',
    'Accept-Language': 'en-US,en;q=0.9',
    'Accept-Encoding': 'identity',
    'Connection': 'keep-alive',
}

TIKTOK_HEADERS = {
    **PROXY_HEADERS,
    'Referer': 'https://www.tiktok.com/',
    'Origin': 'https://www.tiktok.com',
}

PLATFORM_HEADERS = {
    'tiktok':    TIKTOK_HEADERS,
    'instagram': {**PROXY_HEADERS, 'Referer': 'https://www.instagram.com/'},
    'twitter':   {**PROXY_HEADERS, 'Referer': 'https://twitter.com/'},
    'facebook':  {**PROXY_HEADERS, 'Referer': 'https://www.facebook.com/'},
}


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("🚀 Social Video Downloader API starting...")
    yield
    logger.info("📴 Shutting down...")


app = FastAPI(
    title="Social Video Downloader API",
    version="2.1.0",
    description="Download videos from Facebook, YouTube, TikTok, Instagram, Twitter and more.",
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
    logger.error(f"Unhandled: {exc}", exc_info=True)
    return JSONResponse(status_code=500, content={"status": "error", "message": "Internal server error"})


@app.get("/")
async def root():
    from fastapi.responses import FileResponse
    return FileResponse("static/index.html")


@app.get("/health")
async def health():
    return {
        "status": "healthy",
        "version": "2.1.0",
        "platforms": list(URLValidator.SUPPORTED_PLATFORMS.keys())
    }


@app.post("/download", response_model=VideoDownloadResponse)
async def download_video(request: VideoDownloadRequest, _: None = Depends(check_rate_limit)):
    try:
        result = await video_service.get_video_info(str(request.url), request.quality)
        return VideoDownloadResponse(
            status="success",
            video_info=result['video_info'],
            download_url=result['download_url'],
            available_formats=result['available_formats'],
            platform=result.get('platform', 'unknown')
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail={"status": "error", "message": str(e)})
    except Exception as e:
        logger.error(f"Download error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail={"status": "error", "message": "Processing failed"})


@app.get("/stream/video")
async def stream_video(url: str, platform: str = "unknown"):
    """
    Server-side proxy stream — forwards the video with correct headers.
    This solves 403 Forbidden issues (TikTok, Instagram, etc.)
    """
    try:
        parsed = urlparse(url)
        if not parsed.scheme or not parsed.netloc:
            raise HTTPException(status_code=400, detail="Invalid URL")

        # Pick correct referer/headers for platform
        headers = PLATFORM_HEADERS.get(platform, PROXY_HEADERS)

        async def generate():
            timeout = aiohttp.ClientTimeout(total=300, connect=15)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(url, headers=headers, allow_redirects=True) as resp:
                    if resp.status not in (200, 206):
                        logger.error(f"CDN returned {resp.status} for {url}")
                        return
                    async for chunk in resp.content.iter_chunked(65536):
                        yield chunk

        return StreamingResponse(
            generate(),
            media_type="video/mp4",
            headers={
                "Content-Disposition": 'attachment; filename="video.mp4"',
                "Cache-Control": "no-cache",
                "Access-Control-Expose-Headers": "Content-Disposition",
            }
        )
    except Exception as e:
        logger.error(f"Stream error: {e}")
        raise HTTPException(status_code=500, detail="Stream failed")


@app.get("/platforms")
async def platforms():
    return {
        "status": "success",
        "platforms": list(URLValidator.SUPPORTED_PLATFORMS.keys()),
    }


@app.get("/qualities")
async def qualities():
    return {
        "status": "success",
        "qualities": [q.value for q in VideoQuality],
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host=settings.HOST, port=settings.PORT, reload=settings.DEBUG)
