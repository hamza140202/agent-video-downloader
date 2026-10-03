"""Rednote extractor tests."""
import pytest


@pytest.mark.asyncio
async def test_rednote_extract_id():
    """Test Rednote note ID extraction."""
    from avd.extractors.rednote import _extract_note_id

    # Real note IDs are 24+ chars hex
    assert _extract_note_id("https://www.xiaohongshu.com/explore/64dxxexampleid000000000001") == "64dxxexampleid000000000001"


@pytest.mark.asyncio
async def test_rednote_cdn_allowlist():
    """Test CDN allowlist check."""
    from avd.extractors.rednote import _is_allowed_cdn

    assert _is_allowed_cdn("https://sns-video.xhscdn.com/abc.mp4")
    assert _is_allowed_cdn("https://sns-img.xhscdn.com/abc.jpg")
    assert not _is_allowed_cdn("https://evil.com/video.mp4")
