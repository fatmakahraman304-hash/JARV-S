"""Resolve a public TikTok video for the native HUD player."""

import re
from urllib.parse import urlsplit

from core.social_sites import SITES


def tiktok_permalink(address):
    try:
        url = urlsplit(address)
        if (url.scheme != "https" or url.hostname not in SITES["tiktok"][2]
                or url.port not in (None, 443) or url.username is not None):
            return ""
    except ValueError:
        return ""
    if not re.fullmatch(r"/@[A-Za-z0-9_.]{1,64}/video/[0-9]{1,24}/?", url.path):
        return ""
    return "https://" + url.hostname + url.path


def resolve_video(address):
    import yt_dlp

    address = tiktok_permalink(address)
    if not address:
        raise ValueError("TikTok video adresi geçersiz.")
    options = {
        "quiet": True, "no_warnings": True, "skip_download": True,
        "noplaylist": True, "socket_timeout": 10, "retries": 1,
        "format": "best[ext=mp4][protocol=https][vcodec^=h264]/"
                  "best[ext=mp4][protocol=https][vcodec^=avc]/best[ext=mp4][protocol=https]",
    }
    with yt_dlp.YoutubeDL(options) as downloader:
        info = downloader.extract_info(address, download=False, ie_key="TikTok")
    stream = (info or {}).get("url", "")
    target = urlsplit(stream)
    if (target.scheme != "https" or not target.hostname or target.username is not None
            or target.port not in (None, 443)
            or not target.hostname.endswith((".tiktokcdn.com", ".tiktokcdn-us.com",
                                              ".tiktokv.com", ".byteoversea.com",
                                              ".ibytedtos.com"))):
        raise ValueError("TikTok oynatma adresi bulunamadı.")
    return stream, str(info.get("title") or "TikTok")[:80]
