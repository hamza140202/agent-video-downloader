"""Douyin extractor tests."""
import pytest


@pytest.mark.asyncio
async def test_douyin_extract_id():
    """Test Douyin aweme_id extraction."""
    from avd.extractors.douyin import _extract_aweme_id

    assert _extract_aweme_id("https://www.douyin.com/video/7126745726494821640") == "7126745726494821640"
    assert _extract_aweme_id("https://www.douyin.com/jingxuan?modal_id=7234567890123456789") == "7234567890123456789"


@pytest.mark.asyncio
async def test_douyin_cdn_allowlist():
    """Test CDN allowlist check."""
    from avd.extractors.douyin import _is_allowed_cdn

    assert _is_allowed_cdn("https://v.douyin.com/abc.mp4")
    assert _is_allowed_cdn("https://douyinvod.com/abc.mp4")
    assert not _is_allowed_cdn("https://evil.com/video.mp4")


@pytest.mark.asyncio
@pytest.mark.smoke
async def test_douyin_honest_empty_without_dtk(tmp_path):
    """Without DTK sidecar configured, Douyin should return datacenter_ip_walled."""
    import os
    saved = os.environ.pop("AVD_DOUYIN_DTK_URL", None)

    import avd.config
    avd.config._settings = None

    try:
        from avd.extractors.douyin import DouyinExtractor

        ex = DouyinExtractor()
        outcome = await ex.extract(
            "https://www.douyin.com/video/7126745726494821640",
            dest=tmp_path,
            opts={},
        )
        assert not outcome.ok
        assert outcome.error in ("datacenter_ip_walled", "all_slots_failed", "yt_dlp_not_installed")
    finally:
        if saved is not None:
            os.environ["AVD_DOUYIN_DTK_URL"] = saved
