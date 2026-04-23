import yt_dlp
import asyncio
import logging
from typing import Dict, List, Optional, Any
from app.models import VideoInfo, VideoFormat, VideoQuality
from app.utils.validators import URLValidator
from app.config import settings

logger = logging.getLogger(__name__)


class VideoDownloadService:
    """Service for downloading videos from all major social media platforms using yt-dlp"""

    BASE_YDL_OPTS = {
        'quiet': True,
        'no_warnings': False,
        'extractaudio': False,
        'outtmpl': '/tmp/%(title)s.%(ext)s',
        'retries': 5,
        'fragment_retries': 5,
        'ignoreerrors': False,
        'no_check_certificate': True,
        'cookiefile': None,
        'extract_flat': False,
        'user_agent': (
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
            'AppleWebKit/537.36 (KHTML, like Gecko) '
            'Chrome/120.0.0.0 Safari/537.36'
        ),
        'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
        'merge_output_format': 'mp4',
        'postprocessors': [{
            'key': 'FFmpegVideoConvertor',
            'preferedformat': 'mp4',
        }],
    }

    # Platform-specific yt-dlp option overrides
    PLATFORM_OPTS = {
        'tiktok': {
            'extractor_args': {'tiktok': {'app_version': '20.9.3', 'manifest_app_version': '209'}},
        },
        'twitter': {
            # Twitter/X sometimes needs different handling
        },
        'instagram': {
            # Instagram may need cookies for private content
        },
    }

    def __init__(self):
        self.ydl_opts = self.BASE_YDL_OPTS.copy()

    async def get_video_info(self, url: str, quality: VideoQuality = VideoQuality.BEST) -> Dict[str, Any]:
        """Extract video information and download URLs from any supported platform"""

        if not URLValidator.is_valid_url(url):
            raise ValueError("অবৈধ URL। সঠিক ভিডিও লিংক দিন।")

        normalized_url = URLValidator.normalize_url(url)
        platform = URLValidator.detect_platform(normalized_url)

        # Resolve short URLs for Facebook
        if 'fb.watch' in normalized_url:
            normalized_url = await self._resolve_redirect_url(normalized_url)

        try:
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                None,
                self._extract_info,
                normalized_url,
                quality,
                platform
            )
            return result

        except Exception as e:
            logger.error(f"Error extracting video info: {str(e)}")
            raise ValueError(f"ভিডিও তথ্য বের করতে ব্যর্থ: {str(e)}")

    async def _resolve_redirect_url(self, url: str) -> str:
        """Resolve short/redirect URLs to their final destination"""
        import aiohttp
        try:
            timeout = aiohttp.ClientTimeout(total=15)
            headers = {
                'User-Agent': self.BASE_YDL_OPTS['user_agent'],
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            }
            async with aiohttp.ClientSession(timeout=timeout) as session:
                current_url = url
                for _ in range(5):
                    async with session.get(current_url, allow_redirects=False, headers=headers) as resp:
                        if resp.status in (301, 302, 303, 307, 308):
                            location = resp.headers.get('Location', '')
                            if location:
                                if location.startswith('/'):
                                    from urllib.parse import urljoin
                                    location = urljoin(current_url, location)
                                current_url = location
                            else:
                                break
                        else:
                            break
            return current_url
        except Exception as e:
            logger.warning(f"Could not resolve redirect URL: {e}")
            return url

    def _build_ydl_opts(self, quality: VideoQuality, platform: str) -> dict:
        """Build yt-dlp options based on quality and platform"""
        opts = self.BASE_YDL_OPTS.copy()

        # Apply platform-specific overrides
        if platform in self.PLATFORM_OPTS:
            opts.update(self.PLATFORM_OPTS[platform])

        # Quality selector
        quality_map = {
            VideoQuality.BEST:  'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
            VideoQuality.WORST: 'worstvideo[ext=mp4]+worstaudio[ext=m4a]/worst[ext=mp4]/worst',
            VideoQuality.P360:  'bestvideo[height<=360][ext=mp4]+bestaudio[ext=m4a]/best[height<=360][ext=mp4]/best[height<=360]',
            VideoQuality.P720:  'bestvideo[height<=720][ext=mp4]+bestaudio[ext=m4a]/best[height<=720][ext=mp4]/best[height<=720]',
            VideoQuality.P1080: 'bestvideo[height<=1080][ext=mp4]+bestaudio[ext=m4a]/best[height<=1080][ext=mp4]/best[height<=1080]',
        }
        opts['format'] = quality_map.get(quality, quality_map[VideoQuality.BEST])
        return opts

    def _extract_info(self, url: str, quality: VideoQuality, platform: str) -> Dict[str, Any]:
        """Extract video information using yt-dlp (runs in thread executor)"""
        opts = self._build_ydl_opts(quality, platform)

        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(url, download=False)
                if not info:
                    raise ValueError("কোনো ভিডিও তথ্য পাওয়া যায়নি।")
                return self._process_video_info(info, platform)

        except yt_dlp.DownloadError as e:
            error_msg = str(e)
            if 'private' in error_msg.lower() or 'not available' in error_msg.lower():
                raise ValueError("এই ভিডিওটি প্রাইভেট অথবা উপলব্ধ নয়।")
            elif 'age' in error_msg.lower():
                raise ValueError("এই ভিডিওতে বয়স সীমাবদ্ধতা রয়েছে।")
            elif 'unsupported url' in error_msg.lower():
                raise ValueError(f"এই প্ল্যাটফর্ম বা URL সাপোর্টেড নয়: {url}")
            elif 'redirect' in error_msg.lower():
                raise ValueError("URL রিডাইরেক্ট সমস্যা। সরাসরি ভিডিও লিংক কপি করে দিন।")
            else:
                raise ValueError(f"ভিডিও এক্সট্র্যাক্ট করতে ব্যর্থ: {error_msg}")
        except Exception as e:
            raise ValueError(f"অপ্রত্যাশিত ত্রুটি: {str(e)}")

    def _process_video_info(self, info: Dict[str, Any], platform: str) -> Dict[str, Any]:
        """Process and structure video information"""
        video_info = VideoInfo(
            title=info.get('title', 'Unknown Title'),
            duration=info.get('duration'),
            thumbnail=info.get('thumbnail'),
            uploader=info.get('uploader') or info.get('channel'),
            view_count=info.get('view_count'),
            upload_date=info.get('upload_date'),
        )

        download_url = info.get('url')

        available_formats = []
        for fmt in info.get('formats', []):
            if fmt.get('url') and fmt.get('height'):
                video_format = VideoFormat(
                    quality=f"{fmt['height']}p",
                    format_id=fmt.get('format_id', ''),
                    ext=fmt.get('ext', 'mp4'),
                    filesize=fmt.get('filesize'),
                    url=fmt['url'],
                )
                available_formats.append(video_format)

        available_formats.sort(
            key=lambda x: int(x.quality.replace('p', '')) if x.quality.replace('p', '').isdigit() else 0,
            reverse=True,
        )

        return {
            'video_info': video_info,
            'download_url': download_url,
            'available_formats': available_formats[:10],
            'platform': platform,
        }


# Global service instance
video_service = VideoDownloadService()
