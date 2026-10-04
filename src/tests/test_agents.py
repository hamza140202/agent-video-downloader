"""Unit tests for the Orchestrator + Verifier + TruthAgent."""
import pytest


def test_registry_has_all_platforms():
    """All 6 platform extractors should be auto-registered."""
    from avd.extractors.registry import ExtractorRegistry

    plats = ExtractorRegistry.supported_platforms()
    for p in ["tiktok", "twitter", "reddit", "instagram", "rednote", "douyin"]:
        assert p in plats, f"missing platform: {p}"


def test_candidates_for_tiktok_url():
    """A known TikTok URL should match the tiktok extractor."""
    from avd.extractors.registry import ExtractorRegistry

    candidates = ExtractorRegistry.candidates("https://www.tiktok.com/@anyuser/video/6718335390845095173")
    assert len(candidates) >= 1
    assert "tiktok" in candidates[0][0].meta.platforms


def test_candidates_for_unknown_url():
    """A non-matching URL should return no candidates."""
    from avd.extractors.registry import ExtractorRegistry

    candidates = ExtractorRegistry.candidates("https://www.youtube.com/watch?v=dQw4w9WgXcQ")
    assert len(candidates) == 0


def test_candidates_for_twitter_url():
    """Twitter URLs should match."""
    from avd.extractors.registry import ExtractorRegistry

    candidates = ExtractorRegistry.candidates("https://x.com/jack/status/20")
    assert len(candidates) >= 1
    assert "twitter" in candidates[0][0].meta.platforms


def test_candidates_for_reddit_url():
    """Reddit URLs should match."""
    from avd.extractors.registry import ExtractorRegistry

    candidates = ExtractorRegistry.candidates("https://www.reddit.com/r/aww/comments/abc/")
    assert len(candidates) >= 1


def test_candidates_for_instagram_url():
    """Instagram URLs should match."""
    from avd.extractors.registry import ExtractorRegistry

    candidates = ExtractorRegistry.candidates("https://www.instagram.com/p/CxYz1234567/")
    assert len(candidates) >= 1


def test_candidates_for_rednote_url():
    """Rednote URLs should match."""
    from avd.extractors.registry import ExtractorRegistry

    candidates = ExtractorRegistry.candidates("https://www.xiaohongshu.com/explore/64dxxexampleid000000000001")
    assert len(candidates) >= 1


def test_candidates_for_douyin_url():
    """Douyin URLs should match."""
    from avd.extractors.registry import ExtractorRegistry

    candidates = ExtractorRegistry.candidates("https://www.douyin.com/video/7126745726494821640")
    assert len(candidates) >= 1


@pytest.mark.asyncio
async def test_verifier_rejects_html(tmp_path):
    """Verifier should reject an HTML error page."""
    from avd.verifier import Verifier

    p = tmp_path / "fake.mp4"
    p.write_text("<html><body>403 Forbidden</body></html>")

    v = Verifier()
    # Use expected_meta to lower min_size just for this test (avoids mutating the singleton)
    report = await v.verify(p, expected_meta={"size_bytes_min": 1})
    assert not report.integrity_ok
    assert "E_HTML_ERROR_PAGE" in report.issues or "E_MAGIC_BYTES_UNKNOWN" in report.issues


@pytest.mark.asyncio
async def test_verifier_rejects_missing_file(tmp_path):
    """Verifier should report E_FILE_NOT_FOUND for a missing file."""
    from avd.verifier import Verifier

    v = Verifier()
    report = await v.verify(tmp_path / "nonexistent.mp4")
    assert not report.integrity_ok
    assert "E_FILE_NOT_FOUND" in report.issues


@pytest.mark.asyncio
async def test_verifier_rejects_tiny_file(tmp_path):
    """Verifier should reject a file smaller than min_size_bytes."""
    from avd.verifier import Verifier

    p = tmp_path / "tiny.mp4"
    p.write_bytes(b"\x00\x00\x00\x20ftypisom" + b"\x00" * 100)  # 110 bytes total
    v = Verifier()
    # min_size_bytes default is 1MB
    report = await v.verify(p)
    assert not report.integrity_ok
    assert "E_SIZE_TOO_SMALL" in report.issues


@pytest.mark.asyncio
async def test_truth_agent_handles_unknown_platform():
    """TruthAgent should return unverifiable for an unknown platform."""
    from avd.truth_agent import TruthAgent

    t = TruthAgent()
    report = await t.cross_check("https://www.example.com/some-post", {"title": "x"})
    assert report.verdict == "unverifiable"


def test_magic_byte_detection_mp4(tmp_path):
    """Magic byte detection should identify a fake MP4."""
    from avd.utils.fs import detect_file_type

    p = tmp_path / "test.mp4"
    # MP4 ftyp box header: offset 4-8 = 'ftyp'
    p.write_bytes(b"\x00\x00\x00\x20ftypisom\x00\x00\x00\x00")
    kind, mime = detect_file_type(p)
    assert kind == "mp4"
    assert mime == "video/mp4"


def test_magic_byte_detection_jpg(tmp_path):
    """Magic byte detection should identify a JPEG."""
    from avd.utils.fs import detect_file_type

    p = tmp_path / "test.jpg"
    p.write_bytes(b"\xff\xd8\xff\xe0\x00\x10JFIF")
    kind, mime = detect_file_type(p)
    assert kind == "jpg"
    assert mime == "image/jpeg"


def test_magic_byte_detection_html(tmp_path):
    """Magic byte detection should identify an HTML error page."""
    from avd.utils.fs import detect_file_type

    p = tmp_path / "test.mp4"
    p.write_text("<html>403 forbidden</html>")
    kind, mime = detect_file_type(p)
    assert kind == "html"


def test_magic_byte_detection_png(tmp_path):
    """Magic byte detection should identify a PNG."""
    from avd.utils.fs import detect_file_type

    p = tmp_path / "test.png"
    p.write_bytes(b"\x89PNG\r\n\x1a\n")
    kind, mime = detect_file_type(p)
    assert kind == "png"


def test_breaker_host_extraction():
    """host_of() should extract the host from a URL."""
    from avd.utils.breaker import host_of

    assert host_of("https://www.tiktok.com/@user/video/123") == "www.tiktok.com"
    assert host_of("https://api.fxtwitter.com/status/20") == "api.fxtwitter.com"


def test_breaker_state_machine():
    """Breaker should open after N failures and recover after reset_timeout."""
    from avd.utils.breaker import _Breaker

    b = _Breaker(fail_max=3, reset_timeout_s=1)  # short timeout for fast test
    assert not b.is_open
    b.record_failure()
    b.record_failure()
    assert not b.is_open
    b.record_failure()  # 3rd failure → opens
    assert b.is_open
    # Wait for reset_timeout to elapse (breaker transitions to half_open on next is_open)
    import time
    time.sleep(1.1)
    assert not b.is_open  # triggers half_open transition
    b.record_success()  # half_open → success → closed
    assert not b.is_open
    # New failure should not open immediately
    b.record_failure()
    assert not b.is_open
