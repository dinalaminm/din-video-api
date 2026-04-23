import yt_dlp
import asyncio
import logging
import os
from typing import Dict, Any
from app.models import VideoInfo, VideoFormat, VideoQuality
from app.utils.validators import URLValidator

logger = logging.getLogger(__name__)

# Cookie file path — upload cookies.txt to repo root
COOKIE_FILE = 'cookies.txt' if os.path.exists('cookies.txt') else None


class VideoDownloadService:
    """Download videos from all major social media platforms using yt-dlp"""

    USER_AGENT = (
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
        'AppleWebKit/537.36 (KHTML, like Gecko) '
        'Chrome/120.0.0.0 Safari/537.36'
    )

    QUALITY_MAP = {
        VideoQuality.BEST:  'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
        VideoQuality.WORST: 'worstvideo+worstaudio/worst',
        VideoQuality.P360:  'bestvideo[height<=360]+bestaudio/best[height<=360]',
        VideoQuality.P720:  'bestvideo[height<=720]+bestaudio/best[height<=720]',
        VideoQuality.P1080: 'bestvideo[height<=1080]+bestaudio/best[height<=1080]',
    }

    def _base_opts(self) -> dict:
        return {
            'quiet': True,
            'no_warnings': True,
            'extract_flat': False,
            'no_check_certificate': True,
            'retries': 3,
            'fragment_retries': 3,
            'user_agent': self.USER_AGENT,
            'http_headers': {
                'User-Agent': self.USER_AGENT,
                'Accept-Language': 'en-US,en;q=0.9',
            },
            # Use cookie file if available (helps YouTube, Instagram)
            **({'cookiefile': COOKIE_FILE} if COOKIE_FILE else {}),
        }

    def _build_opts(self, quality: VideoQuality, platform: str) -> dict:
        opts = self._base_opts()
        opts['format'] = self.QUALITY_MAP.get(quality, self.QUALITY_MAP[VideoQuality.BEST])

        # Platform-specific tweaks
        if platform == 'youtube':
            # YouTube: use po_token workaround + android client
            opts['extractor_args'] = {
                'youtube': {
                    'player_client': ['android', 'web'],
                    'skip': ['hls', 'dash'],
                }
            }
            # If no cookie file, try with age bypass
            if not COOKIE_FILE:
                opts['age_limit'] = 99

        elif platform == 'tiktok':
            opts['extractor_args'] = {
                'tiktok': {
                    'app_version': '20.9.3',
                    'manifest_app_version': '209',
                }
            }
            # TikTok: prefer direct mp4, skip HLS
            opts['format'] = 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/download'

        elif platform == 'instagram':
            # Instagram needs cookies for most content
            opts['extractor_args'] = {
                'instagram': {'include_feeds': ['reels']}
            }

        elif platform == 'twitter':
            opts['extractor_args'] = {
                'twitter': {'api': ['syndication']}
            }

        return opts

    async def get_video_info(self, url: str, quality: VideoQuality = VideoQuality.BEST) -> Dict[str, Any]:
        if not URLValidator.is_valid_url(url):
            raise ValueError("অবৈধ URL। সঠিক ভিডিও লিংক দিন।")

        url = URLValidator.normalize_url(url)
        platform = URLValidator.detect_platform(url)

        if 'fb.watch' in url:
            url = await self._resolve_redirect(url)

        loop = asyncio.get_event_loop()
        try:
            return await loop.run_in_executor(
                None, self._extract, url, quality, platform
            )
        except ValueError:
            raise
        except Exception as e:
            logger.error(f"Extraction error: {e}")
            raise ValueError(f"ভিডিও প্রসেস করতে ব্যর্থ: {str(e)}")

    async def _resolve_redirect(self, url: str) -> str:
        import aiohttp
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as s:
                for _ in range(5):
                    async with s.get(url, allow_redirects=False,
                                     headers={'User-Agent': self.USER_AGENT}) as r:
                        if r.status in (301, 302, 303, 307, 308):
                            loc = r.headers.get('Location', '')
                            if loc:
                                url = loc if loc.startswith('http') else f"https://facebook.com{loc}"
                            else:
                                break
                        else:
                            break
        except Exception as e:
            logger.warning(f"Redirect resolve failed: {e}")
        return url

    def _extract(self, url: str, quality: VideoQuality, platform: str) -> Dict[str, Any]:
        opts = self._build_opts(quality, platform)

        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(url, download=False)
                if not info:
                    raise ValueError("কোনো ভিডিও তথ্য পাওয়া যায়নি।")
                return self._process(info, platform)

        except yt_dlp.DownloadError as e:
            msg = str(e).lower()
            if 'sign in' in msg or 'bot' in msg or 'cookie' in msg:
                if platform == 'youtube':
                    raise ValueError(
                        "YouTube এই মুহূর্তে cookies ছাড়া কাজ করছে না। "
                        "repo-তে cookies.txt যোগ করুন।"
                    )
                raise ValueError("এই ভিডিও দেখতে login দরকার। cookies.txt যোগ করুন।")
            elif 'private' in msg or 'not available' in msg:
                raise ValueError("এই ভিডিওটি প্রাইভেট অথবা উপলব্ধ নয়।")
            elif 'age' in msg:
                raise ValueError("এই ভিডিওতে বয়স সীমাবদ্ধতা রয়েছে।")
            elif 'unsupported url' in msg:
                raise ValueError("এই প্ল্যাটফর্ম সাপোর্টেড নয়।")
            else:
                raise ValueError(f"ডাউনলোড ত্রুটি: {str(e)}")
        except ValueError:
            raise
        except Exception as e:
            raise ValueError(f"অপ্রত্যাশিত ত্রুটি: {str(e)}")

    def _process(self, info: Dict[str, Any], platform: str) -> Dict[str, Any]:
        video_info = VideoInfo(
            title=info.get('title', 'Unknown'),
            duration=info.get('duration'),
            thumbnail=info.get('thumbnail'),
            uploader=info.get('uploader') or info.get('channel') or info.get('creator'),
            view_count=info.get('view_count'),
            upload_date=info.get('upload_date'),
        )

        # Best download URL
        download_url = info.get('url') or info.get('webpage_url')

        # Collect available formats
        formats = []
        seen = set()
        for fmt in info.get('formats', []):
            url = fmt.get('url', '')
            height = fmt.get('height')
            ext = fmt.get('ext', 'mp4')
            if not url or not height:
                continue
            key = (height, ext)
            if key in seen:
                continue
            seen.add(key)
            formats.append(VideoFormat(
                quality=f"{height}p",
                format_id=fmt.get('format_id', ''),
                ext=ext,
                filesize=fmt.get('filesize') or fmt.get('filesize_approx'),
                url=url,
            ))

        formats.sort(
            key=lambda x: int(x.quality.replace('p', '')) if x.quality.replace('p', '').isdigit() else 0,
            reverse=True,
        )

        return {
            'video_info': video_info,
            'download_url': download_url,
            'available_formats': formats[:10],
            'platform': platform,
        }


video_service = VideoDownloadService()
