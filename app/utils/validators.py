import re
from urllib.parse import urlparse


class URLValidator:
    """Validator for social media video URLs"""

    SUPPORTED_PLATFORMS = {
        "facebook": [
            r'https?://(?:www\.|web\.|m\.)?facebook\.com/watch',
            r'https?://(?:www\.|web\.|m\.)?facebook\.com/.*?/videos/\d+',
            r'https?://(?:www\.|web\.|m\.)?facebook\.com/video\.php',
            r'https?://fb\.watch/[a-zA-Z0-9_-]+',
            r'https?://(?:www\.|web\.|m\.)?facebook\.com/reel/\d+',
            r'https?://(?:www\.|web\.|m\.)?facebook\.com/share/[vr]/[a-zA-Z0-9_-]+',
        ],
        "youtube": [
            r'https?://(?:www\.)?youtube\.com/watch\?v=[\w-]+',
            r'https?://youtu\.be/[\w-]+',
            r'https?://(?:www\.)?youtube\.com/shorts/[\w-]+',
            r'https?://(?:www\.)?youtube\.com/live/[\w-]+',
        ],
        "instagram": [
            r'https?://(?:www\.)?instagram\.com/p/[\w-]+',
            r'https?://(?:www\.)?instagram\.com/reel/[\w-]+',
            r'https?://(?:www\.)?instagram\.com/tv/[\w-]+',
        ],
        "tiktok": [
            r'https?://(?:www\.)?tiktok\.com/@[\w.-]+/video/\d+',
            r'https?://vm\.tiktok\.com/[\w-]+',
            r'https?://vt\.tiktok\.com/[\w-]+',
        ],
        "twitter": [
            r'https?://(?:www\.)?twitter\.com/\w+/status/\d+',
            r'https?://(?:www\.)?x\.com/\w+/status/\d+',
        ],
        "reddit": [
            r'https?://(?:www\.)?reddit\.com/r/\w+/comments/[\w-]+',
            r'https?://v\.redd\.it/[\w-]+',
        ],
        "vimeo": [
            r'https?://(?:www\.)?vimeo\.com/\d+',
            r'https?://player\.vimeo\.com/video/\d+',
        ],
        "dailymotion": [
            r'https?://(?:www\.)?dailymotion\.com/video/[\w-]+',
            r'https?://dai\.ly/[\w-]+',
        ],
        "twitch": [
            r'https?://(?:www\.)?twitch\.tv/videos/\d+',
            r'https?://clips\.twitch\.tv/[\w-]+',
        ],
        "pinterest": [
            r'https?://(?:www\.)?pinterest\.com/pin/\d+',
            r'https?://pin\.it/[\w-]+',
        ],
        "linkedin": [
            r'https?://(?:www\.)?linkedin\.com/posts/[\w-]+',
            r'https?://(?:www\.)?linkedin\.com/feed/update/[\w:-]+',
        ],
        "snapchat": [
            r'https?://(?:www\.)?snapchat\.com/spotlight/[\w-]+',
        ],
    }

    ALL_PATTERNS = [p for patterns in SUPPORTED_PLATFORMS.values() for p in patterns]

    @classmethod
    def detect_platform(cls, url: str) -> str:
        """Detect which platform the URL belongs to"""
        if not url:
            return "unknown"
        for platform, patterns in cls.SUPPORTED_PLATFORMS.items():
            for pattern in patterns:
                if re.search(pattern, url, re.IGNORECASE):
                    return platform
        return "unknown"

    @classmethod
    def is_valid_url(cls, url: str) -> bool:
        """Check if URL is a valid supported social media video URL"""
        if not url:
            return False
        try:
            parsed = urlparse(url)
            if not parsed.scheme or not parsed.netloc:
                return False
        except Exception:
            return False
        # Allow any http/https URL — let yt-dlp decide if unsupported
        return parsed.scheme in ("http", "https")

    # Keep old name for backward compatibility
    @classmethod
    def is_valid_facebook_url(cls, url: str) -> bool:
        return cls.is_valid_url(url)

    @classmethod
    def normalize_url(cls, url: str) -> str:
        """Normalize URL for consistent processing"""
        if 'facebook.com' in url or 'fb.watch' in url:
            url = re.sub(r'[&?](fbclid|ref|source|__tn__|__cft__|hash)=[^&]*', '', url)
            url = re.sub(r'[&?]$', '', url)
            url = url.replace('web.facebook.com', 'www.facebook.com')
            url = url.replace('m.facebook.com', 'www.facebook.com')
        if 'x.com' in url:
            url = url.replace('x.com', 'twitter.com')
        return url
