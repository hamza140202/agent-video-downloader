"""Reddit extractor — fallback chain.

Chain (priority order):
  1. yt-dlp Reddit extractor + OAuth2          (primary, if AVD_REDDIT_CLIENT_ID set)
  2. RSS feed + preview.redd.it image extraction (image-only fallback)
  3. Honest empty: oauth_required

From datacenter IPs, Reddit's JSON endpoint (`/comments/<id>.json`) returns 403.
The only path that works without OAuth is the RSS feed for subreddit-level metadata.
"""
from __future__ import annotations

import re
from pathlib import Path

from avd.config import get_settings
from avd.extractors.base import BaseExtractor
from avd.extractors.registry import ExtractorRegistry
from avd.models import DownloadMetadata, ExtractOutcome, ExtractorMeta
from avd.utils.fs import detect_file_type, ensure_dir, safe_unlink
from avd.utils.http import fetch_json, fetch_text, stream_download
from avd.utils.logging import get_logger

log = get_logger("avd.extractors.reddit")

REDDIT_URL_PATTERNS = [
    r"^https?://(?:www\.|old\.|new\.|np\.)?reddit\.com/.+",
    r"^https?://redd\.it/.+",
    r"^https?://v\.redd\.it/.+",
]

REDDIT_CDN_ALLOWLIST = (
    "v.redd.it",
    "redditmedia.com",
    "reddit.com",
    "redd.it",
    "preview.redd.it",
    "external-preview.redd.it",
    "i.redd.it",
)


def _is_allowed_cdn(url: str) -> bool:
    return any(host in url.lower() for host in REDDIT_CDN_ALLOWLIST)


def _extract_post_id(url: str) -> str | None:
    """Extract post ID from a Reddit URL."""
    m = re.search(r"/comments/([a-z0-9]{5,})", url, re.IGNORECASE)
    if m:
        return m.group(1)
    m = re.search(r"/([a-z0-9]{5,})(?:/|$|\?)", url, re.IGNORECASE)
    if m:
        return m.group(1)
    return None


async def _get_oauth_token() -> str | None:
    """Fetch a Reddit OAuth2 bearer token using HTTP Basic + throwaway creds."""
    s = get_settings()
    if not (s.reddit_client_id and s.reddit_client_secret and s.reddit_username and s.reddit_password):
        return None
    import httpx
    async with httpx.AsyncClient(timeout=15.0) as client:
        try:
            r = await client.post(
                "https://www.reddit.com/api/v1/access_token",
                auth=(s.reddit_client_id, s.reddit_client_secret),
                data={
                    "grant_type": "password",
                    "username": s.reddit_username,
                    "password": s.reddit_password,
                },
                headers={"User-Agent": s.reddit_user_agent},
            )
            if r.status_code != 200:
                return None
            data = r.json()
            return data.get("access_token")
        except Exception:
            return None


async def _try_ytdlp_oauth(url: str, dest: Path, opts: dict) -> ExtractOutcome:
    """Slot 1: yt-dlp Reddit with OAuth2 token in headers."""
    s = get_settings()
    if not (s.reddit_client_id and s.reddit_client_secret):
        return ExtractOutcome(ok=False, extractor_name="reddit:ytdlp", error="oauth_not_configured")

    pid = _extract_post_id(url)
    if not pid:
        return ExtractOutcome(ok=False, extractor_name="reddit:ytdlp", error="no_post_id")

    try:
        import yt_dlp
    except ImportError:
        return ExtractOutcome(ok=False, extractor_name="reddit:ytdlp", error="yt_dlp_not_installed")

    token = await _get_oauth_token()
    if not token:
        return ExtractOutcome(ok=False, extractor_name="reddit:ytdlp", error="oauth_token_failed")

    # Build yt-dlp options with bearer auth header
    out_path = dest if str(dest).endswith(".mp4") else dest / f"{pid}.mp4"
    ensure_dir(out_path.parent)

    ytdlp_opts = {
        "outtmpl": str(out_path),
        "format": "best[ext=mp4]/best",
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "http_headers": {
            "Authorization": f"Bearer {token}",
            "User-Agent": s.reddit_user_agent,
        },
    }
    try:
        with yt_dlp.YoutubeDL(ytdlp_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            if info is None:
                return ExtractOutcome(ok=False, extractor_name="reddit:ytdlp", error="ytdlp_extract_failed")
            metadata = DownloadMetadata(
                source_platform_post_id=pid,
                title=info.get("title"),
                author=info.get("uploader") or info.get("channel"),
                duration_s=info.get("duration"),
            )
            kind, _ = detect_file_type(out_path)
            if kind not in ("mp4", None):
                safe_unlink(out_path)
                return ExtractOutcome(ok=False, extractor_name="reddit:ytdlp", error=f"magic_byte_{kind}")
            return ExtractOutcome(
                ok=True,
                artifact_path=Path(out_path),
                metadata=metadata,
                extractor_name="reddit:ytdlp",
                raw_info={"title": info.get("title"), "duration": info.get("duration")},
            )
    except Exception as e:
        return ExtractOutcome(ok=False, extractor_name="reddit:ytdlp", error=str(e))


async def _try_rss(url: str, dest: Path, opts: dict) -> ExtractOutcome:
    """Slot 2: RSS feed — metadata + image extraction (no video bytes)."""
    pid = _extract_post_id(url)
    if not pid:
        return ExtractOutcome(ok=False, extractor_name="reddit:rss", error="no_post_id")
    # Try the post's RSS — most subreddits support this
    # Sub-level: /r/<sub>/.rss ; post-level via comment feed
    # Best-effort: fetch the post URL with .rss suffix
    rss_url = url.split("?")[0].rstrip("/") + "/.rss"
    status, text = await fetch_text(rss_url, headers={"User-Agent": "python:avd:1.0.0"})
    if status != 200 or not text:
        return ExtractOutcome(ok=False, extractor_name="reddit:rss", error=f"http_{status}")
    # Extract preview.redd.it image URLs — honest "metadata-only" result
    img_match = re.search(r"https://preview\.redd\.it/[^\s\"<]+\.jpg", text)
    if img_match:
        img_url = img_match.group(0).replace("&amp;", "&")
        if not _is_allowed_cdn(img_url):
            return ExtractOutcome(ok=False, extractor_name="reddit:rss", error="cdn_not_allowed")
        out_path = dest if str(dest).endswith((".jpg", ".png")) else dest / f"{pid}.jpg"
        ensure_dir(out_path.parent)
        ok, _, err = await stream_download(img_url, str(out_path))
        if not ok:
            return ExtractOutcome(ok=False, extractor_name="reddit:rss", error=f"download_{err}")
        return ExtractOutcome(
            ok=True,
            artifact_path=Path(out_path),
            metadata=DownloadMetadata(
                source_platform_post_id=pid,
                title="RSS metadata-only",
            ),
            extractor_name="reddit:rss",
        )
    return ExtractOutcome(ok=False, extractor_name="reddit:rss", error="no_media_in_rss")


class RedditExtractor(BaseExtractor):
    meta = ExtractorMeta(
        name="reddit",
        priority=130,
        url_patterns=REDDIT_URL_PATTERNS,
        platforms=["reddit"],
        description="Reddit fallback chain: yt-dlp+OAuth → RSS image extraction",
    )

    async def extract(self, url: str, *, dest: Path, opts: dict | None = None) -> ExtractOutcome:
        opts = opts or {}
        # Expand redd.it short links
        if "redd.it/" in url and "v.redd.it" not in url:
            from avd.utils.http import head_url
            expanded = await head_url(url)
            if expanded:
                url = expanded

        for slot in (_try_ytdlp_oauth, _try_rss):
            try:
                outcome = await slot(url, dest, opts)
                if outcome.ok:
                    log.info("reddit_slot_ok", slot=outcome.extractor_name, url=url)
                    return outcome
                log.info("reddit_slot_fail", slot=outcome.extractor_name, error=outcome.error, url=url)
            except Exception as e:
                log.warning("reddit_slot_exception", slot=slot.__name__, error=str(e))

        # Final honest-empty: tell the caller what's missing
        s = get_settings()
        if not (s.reddit_client_id and s.reddit_client_secret):
            return ExtractOutcome(
                ok=False,
                extractor_name="reddit:chain",
                error="oauth_required",
            )
        return ExtractOutcome(ok=False, extractor_name="reddit:chain", error="all_slots_failed")


ExtractorRegistry.register(RedditExtractor())
