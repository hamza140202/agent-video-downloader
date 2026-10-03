"""Douyin extractor — fallback chain.

Chain (priority order):
  1. yt-dlp Douyin + self-minted anonymous cookies (verified walled 2026-10-03)
  2. Self-hosted Evil0ctal/Douyin_TikTok_Download_API v5 sidecar (if AVD_DOUYIN_DTK_URL set)
  3. Honest empty: datacenter_ip_walled

Douyin is the second-hardest platform. The verification wall (a_bogus, X-Bogus, X-Gnarly,
X-Dynosaur signatures) blocks even anonymous-cookie CLI access. The only working path is
self-hosting the Evil0ctal stack with its CloakBrowser guest-identity minter — which
requires Docker + a headless browser, out of scope for the default no-Docker install.
"""
from __future__ import annotations

import re
from pathlib import Path

from avd.config import get_settings
from avd.extractors.base import BaseExtractor
from avd.extractors.registry import ExtractorRegistry
from avd.models import DownloadMetadata, ExtractOutcome, ExtractorMeta
from avd.utils.fs import detect_file_type, ensure_dir, safe_unlink
from avd.utils.http import fetch_json, stream_download
from avd.utils.logging import get_logger

log = get_logger("avd.extractors.douyin")

DOUYIN_URL_PATTERNS = [
    r"^https?://(?:www\.)?douyin\.com/.+",
    r"^https?://v\.douyin\.com/.+",
    r"^https?://iesdouyin\.com/.+",
]

DOUYIN_CDN_ALLOWLIST = (
    "douyin.com",
    "douyinvod.com",
    "bytecdn.cn",
    "byteimg.com",
    "douyinpic.com",
    "aweme.snssdk.com",
)


def _is_allowed_cdn(url: str) -> bool:
    return any(host in url.lower() for host in DOUYIN_CDN_ALLOWLIST)


def _extract_aweme_id(url: str) -> str | None:
    """Extract the aweme_id (numeric video ID) from a Douyin URL."""
    m = re.search(r"/video/(\d{10,})", url)
    if m:
        return m.group(1)
    m = re.search(r"modal_id=(\d{10,})", url)
    if m:
        return m.group(1)
    m = re.search(r"/(\d{10,})\b", url)
    if m:
        return m.group(1)
    return None


async def _try_dtk_sidecar(url: str, dest: Path, opts: dict) -> ExtractOutcome:
    """Slot 1: Self-hosted Evil0ctal DTK API sidecar (only if AVD_DOUYIN_DTK_URL set)."""
    s = get_settings()
    if not s.douyin_dtk_url:
        return ExtractOutcome(ok=False, extractor_name="douyin:dtk", error="dtk_not_configured")
    aweme_id = _extract_aweme_id(url)
    if not aweme_id:
        return ExtractOutcome(ok=False, extractor_name="douyin:dtk", error="no_aweme_id")
    api_url = f"{s.douyin_dtk_url.rstrip('/')}/api/v1/douyin/web/fetch_one_video?aweme_id={aweme_id}"
    status, data, _ = await fetch_json(api_url, headers={"User-Agent": "Mozilla/5.0"})
    if status != 200 or not isinstance(data, dict):
        return ExtractOutcome(ok=False, extractor_name="douyin:dtk", error=f"http_{status}")
    # DTK returns {code:200, data:{aweme_detail:{video:{play_addr:{url_list:[...]}}}}}
    detail = (data.get("data") or {}).get("aweme_detail") or {}
    video_obj = detail.get("video") or {}
    play_addr = video_obj.get("play_addr") or {}
    urls = play_addr.get("url_list") or []
    if not urls:
        return ExtractOutcome(ok=False, extractor_name="douyin:dtk", error="no_video_url")
    vid_url = urls[0]
    if not _is_allowed_cdn(vid_url):
        return ExtractOutcome(ok=False, extractor_name="douyin:dtk", error="cdn_not_allowed")
    out_path = dest if str(dest).endswith(".mp4") else dest / f"{aweme_id}.mp4"
    ensure_dir(out_path.parent)
    ok, _, err = await stream_download(vid_url, str(out_path), headers={"Referer": "https://www.douyin.com/"})
    if not ok:
        return ExtractOutcome(ok=False, extractor_name="douyin:dtk", error=f"download_{err}")
    kind, _ = detect_file_type(out_path)
    if kind not in ("mp4", None):
        safe_unlink(out_path)
        return ExtractOutcome(ok=False, extractor_name="douyin:dtk", error=f"magic_byte_{kind}")
    return ExtractOutcome(
        ok=True,
        artifact_path=Path(out_path),
        metadata=DownloadMetadata(
            source_platform_post_id=aweme_id,
            title=detail.get("desc"),
            author=str((detail.get("author") or {}).get("uid") or ""),
        ),
        extractor_name="douyin:dtk",
        raw_info=data,
    )


async def _try_ytdlp(url: str, dest: Path, opts: dict) -> ExtractOutcome:
    """Slot 2: yt-dlp Douyin with anonymous cookies (almost always walled from datacenter IP)."""
    aweme_id = _extract_aweme_id(url)
    if not aweme_id:
        return ExtractOutcome(ok=False, extractor_name="douyin:ytdlp", error="no_aweme_id")
    try:
        import yt_dlp
    except ImportError:
        return ExtractOutcome(ok=False, extractor_name="douyin:ytdlp", error="yt_dlp_not_installed")
    out_path = dest if str(dest).endswith(".mp4") else dest / f"{aweme_id}.mp4"
    ensure_dir(out_path.parent)
    ytdlp_opts = {
        "outtmpl": str(out_path),
        "format": "best[ext=mp4]/best",
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "http_headers": {
            "User-Agent": "Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36",
            "Accept-Language": "zh-CN,zh;q=0.9",
            "Referer": "https://www.douyin.com/",
        },
    }
    try:
        with yt_dlp.YoutubeDL(ytdlp_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            if info is None:
                return ExtractOutcome(ok=False, extractor_name="douyin:ytdlp", error="ytdlp_extract_failed")
            return ExtractOutcome(
                ok=True,
                artifact_path=Path(out_path),
                metadata=DownloadMetadata(
                    source_platform_post_id=aweme_id,
                    title=info.get("title"),
                    author=info.get("uploader"),
                    duration_s=info.get("duration"),
                ),
                extractor_name="douyin:ytdlp",
            )
    except Exception as e:
        msg = str(e)
        if "Fresh cookies" in msg or "cookies" in msg.lower():
            return ExtractOutcome(ok=False, extractor_name="douyin:ytdlp", error="datacenter_ip_walled")
        return ExtractOutcome(ok=False, extractor_name="douyin:ytdlp", error=msg)


class DouyinExtractor(BaseExtractor):
    meta = ExtractorMeta(
        name="douyin",
        priority=160,
        url_patterns=DOUYIN_URL_PATTERNS,
        platforms=["douyin"],
        description="Douyin fallback chain: DTK sidecar → yt-dlp → honest empty",
    )

    async def extract(self, url: str, *, dest: Path, opts: dict | None = None) -> ExtractOutcome:
        opts = opts or {}
        # Expand v.douyin.com short
        if "v.douyin.com/" in url:
            from avd.utils.http import head_url
            expanded = await head_url(url)
            if expanded:
                url = expanded
        for slot in (_try_dtk_sidecar, _try_ytdlp):
            try:
                outcome = await slot(url, dest, opts)
                if outcome.ok:
                    log.info("douyin_slot_ok", slot=outcome.extractor_name, url=url)
                    return outcome
                log.info("douyin_slot_fail", slot=outcome.extractor_name, error=outcome.error, url=url)
            except Exception as e:
                log.warning("douyin_slot_exception", slot=slot.__name__, error=str(e))
        return ExtractOutcome(
            ok=False,
            extractor_name="douyin:chain",
            error="datacenter_ip_walled",
        )


ExtractorRegistry.register(DouyinExtractor())
