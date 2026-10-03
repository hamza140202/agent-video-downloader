"""Rednote / Xiaohongshu extractor — fallback chain.

Chain (priority order):
  1. yt-dlp XiaoHongShu extractor + anonymous cookie
  2. Direct HTML scrape + og:video
  3. Honest empty: xsec_token_missing or datacenter_ip_walled
"""
from __future__ import annotations

import re
from pathlib import Path

from avd.extractors.base import BaseExtractor
from avd.extractors.registry import ExtractorRegistry
from avd.models import DownloadMetadata, ExtractOutcome, ExtractorMeta
from avd.utils.fs import detect_file_type, ensure_dir, safe_unlink
from avd.utils.http import fetch_text, stream_download
from avd.utils.logging import get_logger

log = get_logger("avd.extractors.rednote")

REDNOTE_URL_PATTERNS = [
    r"^https?://(?:www\.)?xiaohongshu\.com/.+",
    r"^https?://xhslink\.com/.+",
]

REDNOTE_CDN_ALLOWLIST = (
    "sns-video.xhscdn.com",
    "sns-img.xhscdn.com",
    "xhscdn.com",
    "xiaohongshu.com",
)


def _is_allowed_cdn(url: str) -> bool:
    return any(host in url.lower() for host in REDNOTE_CDN_ALLOWLIST)


def _extract_note_id(url: str) -> str | None:
    m = re.search(r"/(?:explore|discovery/item|user/profile/[^/]+)/([a-z0-9]{24,})", url, re.IGNORECASE)
    if m:
        return m.group(1)
    m = re.search(r"/(?:explore|discovery/item)/([a-zA-Z0-9]+)", url, re.IGNORECASE)
    if m:
        return m.group(1)
    return None


async def _try_ytdlp(url: str, dest: Path, opts: dict) -> ExtractOutcome:
    """Slot 1: yt-dlp XiaoHongShu extractor."""
    note_id = _extract_note_id(url)
    if not note_id:
        return ExtractOutcome(ok=False, extractor_name="rednote:ytdlp", error="no_note_id")
    try:
        import yt_dlp
    except ImportError:
        return ExtractOutcome(ok=False, extractor_name="rednote:ytdlp", error="yt_dlp_not_installed")
    out_path = dest if str(dest).endswith(".mp4") else dest / f"{note_id}.mp4"
    ensure_dir(out_path.parent)
    ytdlp_opts = {
        "outtmpl": str(out_path),
        "format": "best[ext=mp4]/best",
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "http_headers": {
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Referer": "https://www.xiaohongshu.com/",
        },
    }
    try:
        with yt_dlp.YoutubeDL(ytdlp_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            if info is None:
                return ExtractOutcome(ok=False, extractor_name="rednote:ytdlp", error="ytdlp_extract_failed")
            metadata = DownloadMetadata(
                source_platform_post_id=note_id,
                title=info.get("title"),
                author=info.get("uploader") or info.get("channel"),
                duration_s=info.get("duration"),
            )
            kind, _ = detect_file_type(out_path)
            if kind not in ("mp4", None):
                safe_unlink(out_path)
                return ExtractOutcome(ok=False, extractor_name="rednote:ytdlp", error=f"magic_byte_{kind}")
            return ExtractOutcome(
                ok=True,
                artifact_path=Path(out_path),
                metadata=metadata,
                extractor_name="rednote:ytdlp",
            )
    except Exception as e:
        msg = str(e)
        if "No video formats found" in msg:
            return ExtractOutcome(ok=False, extractor_name="rednote:ytdlp", error="xsec_token_missing")
        return ExtractOutcome(ok=False, extractor_name="rednote:ytdlp", error=msg)


async def _try_html_scrape(url: str, dest: Path, opts: dict) -> ExtractOutcome:
    """Slot 2: HTML scrape for og:video / og:image."""
    note_id = _extract_note_id(url)
    if not note_id:
        return ExtractOutcome(ok=False, extractor_name="rednote:html", error="no_note_id")
    headers = {
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    }
    status, html = await fetch_text(url, headers=headers)
    if status != 200 or not html:
        return ExtractOutcome(ok=False, extractor_name="rednote:html", error=f"http_{status}")
    # Try og:video first
    m = re.search(r'<meta[^>]+property="og:video[^"]*"[^>]+content="([^"]+)"', html, re.IGNORECASE)
    if not m:
        m = re.search(r'<meta[^>]+property="og:image"[^>]+content="([^"]+)"', html, re.IGNORECASE)
    if not m:
        return ExtractOutcome(ok=False, extractor_name="rednote:html", error="no_og_media")
    media_url = m.group(1).replace("&amp;", "&")
    if not _is_allowed_cdn(media_url):
        return ExtractOutcome(ok=False, extractor_name="rednote:html", error="cdn_not_allowed")
    ext = ".mp4" if "video" in (media_url.lower() + html.lower()) else ".jpg"
    out_path = dest if str(dest).endswith((".mp4", ".jpg", ".webp")) else dest / f"{note_id}{ext}"
    ensure_dir(out_path.parent)
    ok, _, err = await stream_download(media_url, str(out_path), headers={"Referer": "https://www.xiaohongshu.com/"})
    if not ok:
        return ExtractOutcome(ok=False, extractor_name="rednote:html", error=f"download_{err}")
    kind, _ = detect_file_type(out_path)
    if kind not in ("mp4", "jpg", "webp", None):
        safe_unlink(out_path)
        return ExtractOutcome(ok=False, extractor_name="rednote:html", error=f"magic_byte_{kind}")
    return ExtractOutcome(
        ok=True,
        artifact_path=Path(out_path),
        metadata=DownloadMetadata(source_platform_post_id=note_id),
        extractor_name="rednote:html",
    )


class RednoteExtractor(BaseExtractor):
    meta = ExtractorMeta(
        name="rednote",
        priority=150,
        url_patterns=REDNOTE_URL_PATTERNS,
        platforms=["rednote"],
        description="Rednote/Xiaohongshu fallback chain: yt-dlp → HTML og:video",
    )

    async def extract(self, url: str, *, dest: Path, opts: dict | None = None) -> ExtractOutcome:
        opts = opts or {}
        # Expand xhslink short
        if "xhslink.com/" in url:
            from avd.utils.http import head_url
            expanded = await head_url(url)
            if expanded:
                url = expanded
        for slot in (_try_ytdlp, _try_html_scrape):
            try:
                outcome = await slot(url, dest, opts)
                if outcome.ok:
                    log.info("rednote_slot_ok", slot=outcome.extractor_name, url=url)
                    return outcome
                log.info("rednote_slot_fail", slot=outcome.extractor_name, error=outcome.error, url=url)
            except Exception as e:
                log.warning("rednote_slot_exception", slot=slot.__name__, error=str(e))
        return ExtractOutcome(ok=False, extractor_name="rednote:chain", error="datacenter_ip_walled")


ExtractorRegistry.register(RednoteExtractor())
