"""pytest fixtures."""
import pytest


@pytest.fixture
def sample_urls() -> dict:
    import json
    from pathlib import Path
    p = Path(__file__).parent / "sample_urls.json"
    with open(p) as f:
        return json.load(f)
