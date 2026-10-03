"""Reddit extractor tests (smoke + offline)."""
import pytest


@pytest.mark.asyncio
async def test_reddit_extract_id():
    """Test Reddit post ID extraction."""
    from avd.extractors.reddit import _extract_post_id

    assert _extract_post_id("https://www.reddit.com/r/aww/comments/1bxxhzp/my_cat_is_beautiful/") == "1bxxhzp"


@pytest.mark.asyncio
async def test_reddit_cdn_allowlist():
    """Test CDN allowlist check."""
    from avd.extractors.reddit import _is_allowed_cdn

    assert _is_allowed_cdn("https://v.redd.it/abc123/DASH_1080.mp4")
    assert _is_allowed_cdn("https://preview.redd.it/abc.jpg")
    assert not _is_allowed_cdn("https://evil.com/video.mp4")


@pytest.mark.asyncio
@pytest.mark.smoke
async def test_reddit_no_oauth_returns_honest_empty(tmp_path):
    """Without OAuth env vars, Reddit extractor should return oauth_required."""
    import os

    # Make sure env vars are unset
    env_keys = ["AVD_REDDIT_CLIENT_ID", "AVD_REDDIT_CLIENT_SECRET", "AVD_REDDIT_USERNAME", "AVD_REDDIT_PASSWORD"]
    saved = {k: os.environ.pop(k, None) for k in env_keys}

    # Force settings reload
    from avd.config import get_settings
    get_settings.__wrapped__ = None  # type: ignore
    import avd.config
    avd.config._settings = None

    try:
        from avd.extractors.reddit import RedditExtractor

        ex = RedditExtractor()
        outcome = await ex.extract(
            "https://www.reddit.com/r/aww/comments/1bxxhzp/my_cat_is_beautiful/",
            dest=tmp_path,
            opts={},
        )
        # Either we get an honest empty (oauth_required) or RSS image succeeds
        assert not outcome.ok or outcome.extractor_name == "reddit:rss"
        if not outcome.ok:
            assert outcome.error in ("oauth_required", "all_slots_failed", "no_post_id")
    finally:
        for k, v in saved.items():
            if v is not None:
                os.environ[k] = v
