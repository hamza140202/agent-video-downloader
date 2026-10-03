"""Instagram extractor tests (smoke + offline)."""
import pytest


@pytest.mark.asyncio
async def test_instagram_extract_shortcode():
    """Test Instagram shortcode extraction."""
    from avd.extractors.instagram import _extract_shortcode

    assert _extract_shortcode("https://www.instagram.com/p/CxYz1234567/") == "CxYz1234567"
    assert _extract_shortcode("https://www.instagram.com/reel/CxYz9876543/") == "CxYz9876543"


@pytest.mark.asyncio
async def test_instagram_cdn_allowlist():
    """Test CDN allowlist check."""
    from avd.extractors.instagram import _is_allowed_cdn

    assert _is_allowed_cdn("https://scontent.cdninstagram.com/v/abc.mp4")
    assert _is_allowed_cdn("https://video.fbcdn.com/v/abc.mp4")
    assert not _is_allowed_cdn("https://evil.com/video.mp4")


@pytest.mark.asyncio
@pytest.mark.smoke
async def test_instagram_best_effort_or_honest_empty(tmp_path):
    """Instagram from datacenter IP — either download or honest empty."""
    from avd.extractors.instagram import InstagramExtractor

    ex = InstagramExtractor()
    outcome = await ex.extract(
        "https://www.instagram.com/p/CxYz1234567/",
        dest=tmp_path,
        opts={},
    )
    # Either we got media, or we got an honest empty
    if outcome.ok:
        assert outcome.artifact_path.exists()
    else:
        assert outcome.error in (
            "datacenter_ip_walled",
            "no_shortcode",
            "no_media_url",
            "all_slots_failed",
            "http_404",
            "cdn_not_allowed",
        ), f"unexpected error: {outcome.error}"
