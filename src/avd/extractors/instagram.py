"""Instagram extractor — fallback chain.

Chain (priority order):
  1. embed/captioned/ with facebookexternalhit UA  (primary)
  2. OpenGraph tags (og:image, og:video:secure_url)
  3. Third-party mirror (picnob / pixnoy / ddinstagram) — best-effort
  4. Honest empty: datacenter_ip_walled

Instagram is the hardest platform — every direct API path returns 403 from datacenter IPs.
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

log = get_logger("avd.extractors.instagram")

INSTAGRAM_URL_PATTERNS = [
    r"^https?://(?:www\.)?instagram\.com/.+",
    r"^https?://instagr\.am/.+",
]

INSTAGRAM_CDN_ALLOWLIST = (
    "cdninstagram.com",
    "fbcdn.net",
    "fbcdn.com",
    "scontent",
    "instagram.com",
)


def _is_allowed_cdn(url: str) -> bool:
    return any(host in url.lower() for host in INSTAGRAM_CDN_ALLOWLIST)


def _extract_shortcode(url: str) -> str | None:
    """Extract the 11-char shortcode from /p/<code> or /reel/<code>."""
    m = re.search(r"/(?:p|reel|reels|tv)/([A-Za-z0-9_-]{5,})", url)
    if m:
        return m.group(1)
    return None


async def _try_embed_captioned(url: str, dest: Path, opts: dict) -> ExtractOutcome:
    """Slot 1: /p/<code>/embed/captioned/ with facebookexternalhit UA."""
    code = _extract_shortcode(url)
    if not code:
        return ExtractOutcome(ok=False, extractor_name="instagram:embed", error="no_shortcode")
    embed_url = f"https://www.instagram.com/p/{code}/embed/captioned/"
    headers = {"User-Agent": "facebookexternalhit/1.1"}
    status, html = await fetch_text(embed_url, headers=headers)
    if status != 200 or not html:
        return ExtractOutcome(ok=False, extractor_name="instagram:embed", error=f"http_{status}")
    # Look for video URL
    m = re.search(r"https://[^\"' ]+(?:cdninstagram|fbcdn)[^\"' ]+\.(?:mp4|webp|jpg)", html)
    if not m:
        # Check for contextJSON:null (the wall)
        if "contextJSON:null" in html or html.strip() == "":
            return ExtractOutcome(ok=False, extractor_name="instagram:embed", error="datacenter_ip_walled")
        return ExtractOutcome(ok=False, extractor_name="instagram:embed", error="no_media_url")
    media_url = m.group(0).replace("\\u002F", "/").replace("&amp;", "&").replace("\\/", "/")
    if not _is_allowed_cdn(media_url):
        return ExtractOutcome(ok=False, extractor_name="instagram:embed", error="cdn_not_allowed")
    out_path = dest if str(dest).endswith((".mp4", ".jpg", ".webp")) else dest / f"{code}.mp4"
    ensure_dir(out_path.parent)
    ok, _, err = await stream_download(media_url, str(out_path), headers={"Referer": "https://www.instagram.com/"})
    if not ok:
        return ExtractOutcome(ok=False, extractor_name="instagram:embed", error=f"download_{err}")
    kind, _ = detect_file_type(out_path)
    if kind not in ("mp4", "jpg", "webp", None):
        safe_unlink(out_path)
        return ExtractOutcome(ok=False, extractor_name="instagram:embed", error=f"magic_byte_{kind}")
    return ExtractOutcome(
        ok=True,
        artifact_path=Path(out_path),
        metadata=DownloadMetadata(source_platform_post_id=code),
        extractor_name="instagram:embed",
    )


async def _try_og_meta(url: str, dest: Path, opts: dict) -> ExtractOutcome:
    """Slot 2: OpenGraph tags on /p/<code>/."""
    code = _extract_shortcode(url)
    if not code:
        return ExtractOutcome(ok=False, extractor_name="instagram:og", error="no_shortcode")
    page_url = f"https://www.instagram.com/p/{code}/"
    headers = {"User-Agent": "facebookexternalhit/1.1"}
    status, html = await fetch_text(page_url, headers=headers)
    if status != 200 or not html:
        return ExtractOutcome(ok=False, extractor_name="instagram:og", error=f"http_{status}")
    # og:video:secure_url or og:video
    m = re.search(r'<meta[^>]+property="og:video[^"]*"[^>]+content="([^"]+)"', html, re.IGNORECASE)
    if not m:
        m = re.search(r'<meta[^>]+property="og:image"[^>]+content="([^"]+)"', html, re.IGNORECASE)
    if not m:
        return ExtractOutcome(ok=False, extractor_name="instagram:og", error="no_og_media")
    media_url = m.group(1).replace("&amp;", "&")
    if not _is_allowed_cdn(media_url):
        return ExtractOutcome(ok=False, extractor_name="instagram:og", error="cdn_not_allowed")
    ext = ".mp4" if "video" in (media_url.lower() + html.lower()) else ".jpg"
    out_path = dest if str(dest).endswith((".mp4", ".jpg", ".webp")) else dest / f"{code}{ext}"
    ensure_dir(out_path.parent)
    ok, _, err = await stream_download(media_url, str(out_path), headers={"Referer": "https://www.instagram.com/"})
    if not ok:
        return ExtractOutcome(ok=False, extractor_name="instagram:og", error=f"download_{err}")
    kind, _ = detect_file_type(out_path)
    if kind not in ("mp4", "jpg", "webp", None):
        safe_unlink(out_path)
        return ExtractOutcome(ok=False, extractor_name="instagram:og", error=f"magic_byte_{kind}")
    return ExtractOutcome(
        ok=True,
        artifact_path=Path(out_path),
        metadata=DownloadMetadata(source_platform_post_id=code),
        extractor_name="instagram:og",
    )


async def _try_mirror(url: str, dest: Path, opts: dict) -> ExtractOutcome:
    """Slot 3: Third-party mirror (picnob / ddinstagram). Best-effort."""
    code = _extract_shortcode(url)
    if not code:
        return ExtractOutcome(ok=False, extractor_name="instagram:mirror", error="no_shortcode")
    # Try ddinstagram — anonymous redirect to CDN
    mirror_url = f"https://ddinstagram.com/p/{code}"
    headers = {"User-Agent": "Mozilla/5.0"}
    status, html = await fetch_text(mirror_url, headers=headers)
    if status != 200 or not html:
        return ExtractOutcome(ok=False, extractor_name="instagram:mirror", error=f"http_{status}")
    m = re.search(r"https://[^\"' ]+(?:cdninstagram|fbcdn)[^\"' ]+\.(?:mp4|webp|jpg)", html)
    if not m:
        return ExtractOutcome(ok=False, extractor_name="instagram:mirror", error="no_media_in_mirror")
    media_url = m.group(0).replace("&amp;", "&")
    if not _is_allowed_cdn(media_url):
        return ExtractOutcome(ok=False, extractor_name="instagram:mirror", error="cdn_not_allowed")
    ext = ".mp4" if ".mp4" in media_url.lower() else ".jpg"
    out_path = dest if str(dest).endswith((".mp4", ".jpg", ".webp")) else dest / f"{code}{ext}"
    ensure_dir(out_path.parent)
    ok, _, err = await stream_download(media_url, str(out_path))
    if not ok:
        return ExtractOutcome(ok=False, extractor_name="instagram:mirror", error=f"download_{err}")
    return ExtractOutcome(
        ok=True,
        artifact_path=Path(out_path),
        metadata=DownloadMetadata(source_platform_post_id=code),
        extractor_name="instagram:mirror",
    )


class InstagramExtractor(BaseExtractor):
    meta = ExtractorMeta(
        name="instagram",
        priority=140,
        url_patterns=INSTAGRAM_URL_PATTERNS,
        platforms=["instagram"],
        description="Instagram fallback chain: embed/captioned → og:image → mirror",
    )

    async def extract(self, url: str, *, dest: Path, opts: dict | None = None) -> ExtractOutcome:
        opts = opts or {}
        for slot in (_try_embed_captioned, _try_og_meta, _try_mirror):
            try:
                outcome = await slot(url, dest, opts)
                if outcome.ok:
                    log.info("instagram_slot_ok", slot=outcome.extractor_name, url=url)
                    return outcome
                log.info("instagram_slot_fail", slot=outcome.extractor_name, error=outcome.error, url=url)
            except Exception as e:
                log.warning("instagram_slot_exception", slot=slot.__name__, error=str(e))
        return ExtractOutcome(
            ok=False,
            extractor_name="instagram:chain",
            error="datacenter_ip_walled",
        )


ExtractorRegistry.register(InstagramExtractor())
