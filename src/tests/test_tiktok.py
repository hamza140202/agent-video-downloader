"""TikTok extractor tests (smoke + offline)."""
import pytest


@pytest.mark.asyncio
@pytest.mark.smoke
async def test_tiktok_download_smoke(tmp_path):
    """End-to-end: download a known TikTok URL.

    Verified live 2026-10-03 against TikWM API.
    """
    from avd.extractors.tiktok import TikTokExtractor

    ex = TikTokExtractor()
    outcome = await ex.extract(
        "https://www.tiktok.com/@anyuser/video/6718335390845095173",
        dest=tmp_path,
        opts={},
    )
    assert outcome.ok, f"download failed: {outcome.error}"
    assert outcome.artifact_path.exists()
    assert outcome.artifact_path.stat().st_size > 100_000  # at least 100KB


@pytest.mark.asyncio
async def test_tiktok_extract_id():
    """Test TikTok video ID extraction."""
    from avd.extractors.tiktok import _extract_tiktok_id

    assert _extract_tiktok_id("https://www.tiktok.com/@anyuser/video/6718335390845095173") == "6718335390845095173"
    assert _extract_tiktok_id("https://www.tiktok.com/t/ZPRK1n3FR/") is None  # short, no numeric
    assert _extract_tiktok_id("https://www.tiktok.com/@user/video/7234567890123456789") == "7234567890123456789"


@pytest.mark.asyncio
async def test_tiktok_cdn_allowlist():
    """Test CDN allowlist check."""
    from avd.extractors.tiktok import _is_allowed_cdn

    assert _is_allowed_cdn("https://p16-sign.tiktokcdn-us.com/video.mp4")
    assert _is_allowed_cdn("https://www.tikwm.com/dl/video/abc.mp4")
    assert not _is_allowed_cdn("https://evil.com/video.mp4")
