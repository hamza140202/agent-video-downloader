# AGENTS.md — Agent Contracts & Perfection Prompting

> **The contract document.** Every agent in this system is specified here as a Protocol interface, a behavioral contract, and an "if-then" decision tree. When an LLM agent (Claude, GLM, etc.) is invoked to modify or extend this system, it MUST read this file first and treat these contracts as inviolable.

> **Status:** ✅ v1.2.0 PyPI-published, 2026-10-03. Install: `pip install agent-video-downloader && avd agent-setup`. Live on https://pypi.org/project/agent-video-downloader/

---

## 0. Agent taxonomy

Four agents. Each is a **plain Python class** that implements a `typing.Protocol`. They are **not** LLM-backed — they are deterministic, replayable, testable.

```
┌──────────────────────────────────────────────────────────────────────┐
│                          AGENT LAYER                                  │
├──────────────────────────────────────────────────────────────────────┤
│                                                                       │
│   ┌──────────────┐   ┌──────────────┐   ┌──────────────┐            │
│   │ Orchestrator │ ─▶│  Extractor   │   │ Truth Agent  │            │
│   │   (driver)   │   │  Registry    │   │ (cross-check)│            │
│   └──────┬───────┘   └──────┬───────┘   └──────────────┘            │
│          │                  │                                          │
│          ▼                  ▼                                          │
│   ┌──────────────┐   ┌──────────────┐                                │
│   │   Verifier   │   │   Tester     │                                │
│   │  (validate)  │   │  (self-test) │                                │
│   └──────────────┘   └──────────────┘                                │
│                                                                       │
└──────────────────────────────────────────────────────────────────────┘
```

The Orchestrator is the **only** agent that callers invoke directly. The Verifier, Truth Agent, and Tester are **sub-agents** invoked by the Orchestrator (or by the user via `avd verify` / `avd test`).

---

## 1. Orchestrator

### Role
Owns the lifecycle of a single download request: URL intake → platform routing → fallback chain driving → Verifier invocation → Truth Agent cross-check → result reporting. Also owns the SQLite jobs table for resume capability.

### Protocol signature
```python
class Orchestrator(Protocol):
    """Top-level driver. Callers only ever talk to this agent."""
    registry: "ExtractorRegistry"
    verifier: "Verifier"
    truth: "TruthAgent"

    async def download(self, url: str, *, dest: Path, opts: dict | None = None) -> DownloadResult:
        """Single URL → single artifact. Drives the full chain."""

    async def batch(self, urls: list[str], *, dest: Path, opts: dict | None = None) -> list[DownloadResult]:
        """Many URLs in parallel. Per-host semaphore prevents hammering."""

    def supported(self) -> list[str]:
        """Return list of platform names the registry can serve."""

    async def resume(self, job_id: str) -> DownloadResult:
        """Resume a job from the SQLite jobs table."""

    async def replay(self, dlq_entry_id: str) -> DownloadResult:
        """Replay a dead-letter queue entry after root-cause fix."""
```

### Behavioral contract
1. Receive URL.
2. Normalize URL (strip tracking params, expand short links via HEAD-follow chain).
3. Look up `ExtractorRegistry.candidates(url)` → list of `(extractor, priority)`.
4. If list is empty → return `DownloadResult(status="empty", reason="no_extractor_match")`.
5. Sort by `priority` ascending.
6. For each extractor in order:
   a. Check per-host circuit breaker — if open, skip with `reason="circuit_open"`.
   b. Invoke `extractor.extract(url, dest=dest, opts=opts)` inside a `tenacity` retry policy.
   c. If outcome is `ok=True`:
      - Invoke `Verifier.verify(outcome.artifact_path, expected_meta=outcome.metadata)`.
      - If `verifier_report.integrity_ok` is `True`:
        - Invoke `TruthAgent.cross_check(url, downloaded_meta=outcome.metadata)`.
        - Compose final `DownloadResult(status="ok", ...)` with full provenance.
        - **Return immediately** — do not try further extractors.
      - Else: log `"verifier_rejected"` with the failure list, mark this extractor's outcome as invalid, continue to the next extractor.
   d. If outcome is `ok=False`:
      - Log `"extractor_failed"` with the failure signal.
      - Record the slot in `metadata.slots_tried`.
      - Continue to next extractor.
7. If all extractors exhausted:
   - Write a DLQ entry to `logs/dlq.jsonl`.
   - Return `DownloadResult(status="failed", reason="all_extractors_exhausted", slots_tried=[...])`.

### Decision tree (per download)
```
URL in?
  │
  ├─ normalize → expand short links (HEAD follow, max 3 hops)
  │
  ├─ registry.candidates(url) → list[Extractor]
  │     │
  │     └─ empty? → return empty ("no_extractor_match")
  │
  ├─ for extractor in sorted(candidates, by priority):
  │     │
  │     ├─ breaker.open(host)? → skip, continue
  │     │
  │     ├─ outcome = retry(extractor.extract(...))
  │     │
  │     ├─ outcome.ok?
  │     │     ├─ YES → verifier.verify(outcome.artifact)
  │     │     │           ├─ integrity_ok? → truth.cross_check → return ok
  │     │     │           └─ NO → continue (verifier_rejected)
  │     │     └─ NO → continue (extractor_failed)
  │
  ├─ all exhausted → write DLQ, return failed
```

### State persistence
- SQLite DB at `~/.avd/jobs.sqlite` (override with `AVD_DB_PATH`).
- Schema: `jobs(id, url, platform, status, artifact_path, extractor_chain_json, slots_tried_json, verifier_report_json, truth_report_json, created_at, updated_at, error)`.
- Every `download()` call opens (or resumes) a job row.
- Final result is committed before returning.

### Concurrency model
- Per-host `asyncio.Semaphore(3)` — never more than 3 in-flight requests to one host.
- Global `asyncio.Semaphore(8)` for batch jobs.
- yt-dlp's blocking `download()` is wrapped in `asyncio.to_thread()` to keep the event loop responsive.
- ffprobe/ffmpeg invocations go through a `ProcessPoolExecutor(max_workers=2)` to avoid GIL contention.

---

## 2. Verifier

### Role
After a download finishes, the Verifier confirms the artifact is a real video file (not an HTML error page, not a truncated stream, not a wrong-format artifact). It uses `ffprobe`/`ffmpeg` as the source of truth.

### Protocol signature
```python
class VerifierReport(BaseModel):
    artifact_path: Path
    exists: bool
    size_bytes: int
    mime_type: str | None       # via python-magic
    has_video_stream: bool
    has_audio_stream: bool
    duration_s: float | None
    codec_video: str | None
    codec_audio: str | None
    container: str | None
    integrity_ok: bool           # aggregate verdict
    issues: list[str]           # human-readable list of failures

class Verifier(Protocol):
    async def verify(self, artifact: Path, *, expected_meta: dict | None = None) -> VerifierReport:
        """6-layer integrity check. Returns full report."""
```

### 6-layer integrity check (per `ytagent` doctrine)
1. **File exists** at `artifact_path` after the atomic `os.replace`.
2. **Size ≥ `min_size_bytes`** (default 1 MB; configurable per-platform — TikTok slideshows can be smaller).
3. **Magic bytes** match a known video/audio container:
   - MP4: `f"ftyp{0x69 0x73 0x6f 0x6d}"` or `ftypmp4` etc. at offset 4.
   - WebM: `0x1A 0x45 0xDF 0xA3` at offset 0.
   - MP3: `ID3` at offset 0 or `0xFF 0xFB` frame sync.
   - JPEG: `0xFF 0xD8 0xFF`.
   - PNG: `0x89 0x50 0x4E 0x47`.
4. **`ffprobe -show_format -show_streams` exits 0** — proves ffprobe can parse the container.
5. **Duration > 0** AND at least one stream exists (video or audio).
6. **`moov` atom present** at a sane offset (MP4 only — defends against truncated moov-write before crash).

If `expected_meta` is provided (from the extractor), also check:
- `abs(duration_s - expected_meta.duration_s) <= 2.0` (±2 s tolerance)
- If `expected_meta.codec_video` is set, prefer match — but don't fail on transcode.

### Issue taxonomy
Issues are short string codes (not free text) so downstream agents can grep them:
- `E_SIZE_TOO_SMALL`
- `E_MAGIC_BYTES_MISMATCH`
- `E FFPROBE_FAILED`
- `E_NO_STREAMS`
- `E_DURATION_ZERO`
- `E_MOOV_MISSING`
- `E_DURATION_MISMATCH` (when expected_meta present)
- `E_HTML_ERROR_PAGE` (special case: bytes start with `<html` or `<!DOCTYPE`)

### Behavioral contract
1. Receive `(artifact_path, expected_meta)`.
2. Run all 6 layers.
3. Compose `VerifierReport` with `integrity_ok = all(layer_pass)`.
4. Never raise — always return a report (even on disk read error → `exists=False, integrity_ok=False, issues=["E_FILE_NOT_FOUND"]`).

---

## 3. Truth Agent

### Role
After Verifier confirms the bytes are a real video, the Truth Agent **cross-references** the downloaded artifact's metadata against the source platform's own statement about the content. This catches "wrong video downloaded" bugs and extractor hallucinations.

### Protocol signature
```python
class TruthReport(BaseModel):
    url: str
    platform: str
    source_meta: dict           # what the platform says
    downloaded_meta: dict       # what the extractor reported
    matches: dict[str, bool]    # field-by-field comparison
    confidence: float           # 0.0–1.0
    verdict: Literal["verified", "suspicious", "unverifiable"]

class TruthAgent(Protocol):
    async def cross_check(self, url: str, downloaded_meta: dict) -> TruthReport:
        """Fetch source truth, compare to downloaded, return verdict."""
```

### Per-platform source-of-truth fetchers
Each platform has a `SourceFetcher` that knows how to fetch the platform's own metadata for a URL, **without** going through the same extractor that produced the download (to avoid circular reasoning):

| Platform | Source fetcher | What it returns |
|---|---|---|
| TikTok | `TikTokOEmbedFetcher` — `https://www.tiktok.com/oembed?url=...` | `author_name`, `title`, `thumbnail_url` (no duration — TikTok oEmbed doesn't include it) |
| Twitter/X | `TwitterSyndicationFetcher` — `cdn.syndication.twimg.com/tweet-result?id=...&token=x` | `text`, `user.screen_name`, `favorite_count`, `media[].url` |
| Reddit | `RedditRSSFetcher` — `https://www.reddit.com/r/<sub>/.rss` (post-level lookup by id) | `title`, `author`, `link` |
| Instagram | `InstagramOGFetcher` — `https://www.instagram.com/p/<code>/` with `facebookexternalhit` UA → `og:image`, `og:title` | `og:title`, `og:image` |
| Rednote | `XHSHTMLFetcher` — `https://www.xiaohongshu.com/explore/<id>` → JSON-LD / og: tags | `title`, `desc`, image thumbnail |
| Douyin | `DouyinOGFetcher` — best-effort og: tags from share URL | `og:title`, `og:image` (low confidence — Douyin walls everything) |

### Comparison logic (per `ytagent`)
| Field | Match rule |
|---|---|
| `title` | Levenshtein ratio ≥ 0.7 (fuzzy match — titles get truncated differently by different surfaces) |
| `author_id` / `screen_name` | Exact match (case-insensitive) |
| `duration_s` | `abs(source - downloaded) <= 2.0` seconds |
| `thumbnail_url` host | Same hostname (the path may differ between surfaces) |
| `media_count` | Exact match (e.g., a 4-photo tweet must produce 4 images) |

### Verdict rules
- **`verified`**: ≥ 3 fields checked AND all match.
- **`suspicious`**: ≥ 1 field mismatched (e.g., title differs by > 30%).
- **`unverifiable`**: source fetcher returned nothing (datacenter IP block, deleted content, etc.). This is a valid outcome — does NOT fail the download. The Verifier's `integrity_ok` is the hard gate; Truth is advisory.

### Behavioral contract
1. Receive `(url, downloaded_meta)`.
2. Identify platform from URL pattern.
3. Look up `SourceFetcher` for that platform.
4. Fetch source metadata (with bounded retries, 5 s timeout).
5. If fetch fails → return `verdict="unverifiable", source_meta={}, matches={}`.
6. If fetch succeeds → run field-by-field comparison.
7. Return `TruthReport`.
8. Never raise — always return a report.

---

## 4. Tester

### Role
Self-test the entire system end-to-end. Run by the user (`avd test`) or by CI. Uses a curated `sample_urls.json` of known-good public posts per platform.

### Protocol signature
```python
class TestReport(BaseModel):
    platform: str
    sample_url: str
    extractor_used: str
    downloaded: bool
    verified: bool
    truth_checked: bool
    truth_verdict: Literal["verified", "suspicious", "unverifiable", "skipped"]
    duration_s: float
    artifact_path: Path | None
    error: str | None

class Tester(Protocol):
    async def run(self, platforms: list[str] | None = None, *, smoke: bool = True) -> list[TestReport]:
        """Run end-to-end on sample_urls.json."""

    def samples(self) -> dict[str, list[str]]:
        """Return the curated sample URL set per platform."""
```

### Modes
- `--smoke` (default): one URL per platform, must pass ≥ 4 of 6 platforms. ~30 s.
- `--full`: all URLs in `sample_urls.json`, must pass ≥ 80% per platform. ~5 min.
- `--platform tiktok`: only run one platform's tests.

### Behavioral contract
1. Load `tests/sample_urls.json`.
2. Filter by `platforms` arg if provided.
3. If `smoke=True`, take first URL per platform; else take all.
4. For each URL, invoke `Orchestrator.download()`.
5. Compose `TestReport` from the `DownloadResult` (extract `extractor_used` from `extractor_chain[-1]`, etc.).
6. Print a `rich` table to stderr with pass/fail per URL.
7. Write JSON results to `tests/results/<timestamp>.json`.
8. Exit code: 0 if smoke threshold met, 1 otherwise.

### Sample URL curation rules
- All URLs are **public, well-known, durable** posts (e.g., `@jack`'s first tweet for Twitter, a known-durable TikTok video).
- No private, deleted, or NSFW content.
- Each platform has ≥ 3 samples: one happy path, one image-only (where applicable), one short-link/redirect form.

---

## 5. Inter-agent message contracts

All inter-agent payloads are **pydantic models**, validated on both sides. No bare dicts cross agent boundaries.

### DownloadResult (Orchestrator output → caller)
```python
class DownloadResult(BaseModel):
    url: str
    platform: str
    status: Literal["ok", "empty", "failed"]
    reason: str | None = None
    artifact_path: Path | None
    metadata: DownloadMetadata
    extractor_chain: list[str]
    slots_tried: list[SlotAttempt]
    verifier_report: VerifierReport | None
    truth_report: TruthReport | None
    error: str | None
    job_id: str
    started_at: datetime
    finished_at: datetime

class DownloadMetadata(BaseModel):
    title: str | None
    author: str | None
    duration_s: float | None
    thumbnail_url: str | None
    source_platform_post_id: str | None
    extra: dict  # platform-specific

class SlotAttempt(BaseModel):
    extractor_name: str
    outcome: Literal["ok", "verifier_rejected", "extractor_failed", "skipped"]
    failure_signal: str | None
    duration_s: float
```

### Extractor outcome (Extractor → Orchestrator)
```python
class ExtractOutcome(BaseModel):
    ok: bool
    artifact_path: Path | None
    metadata: DownloadMetadata
    extractor_name: str
    error: str | None = None
    raw_info: dict | None = None  # the raw API response, for debugging
```

---

## 6. Perfection prompting rules (for LLM agents that modify this system)

When an LLM agent (Claude, GLM, Cursor, Cline, etc.) is asked to modify, extend, or debug this system, it MUST:

1. **Read `CLAUDE.md` first**, then this file, then `docs/architecture.md`, then `docs/research-report.md`. **No skimming.** Length means complexity; complexity means ways to fail.
2. **Treat Protocol signatures as inviolable.** Do not add methods to an agent interface without amending this file first.
3. **Honest negatives are first-class.** Never raise an exception for a "deleted content" or "datacenter IP walled" scenario. Return a structured empty.
4. **Atomic writes only.** Stream to `.part` → verify → `os.replace`. Never write the final filename until all gates pass.
5. **No silent fallback.** Every extractor swap logs the failure signal. Every Verifier rejection logs the issue code.
6. **Politeness is a hard constraint.** Bounded retries (max 3 per extractor), 0.6 s decode sleeps, per-host circuit breaker (default 5 failures → 5 min cooldown).
7. **Magic bytes gate.** No artifact is reported downloaded until its bytes prove its type (see Verifier §3).
8. **CDN allowlist.** Bytes are only fetched from known CDN hostnames per platform (see `docs/endpoint-matrix.md`). Unknown hosts → reject.
9. **Tests are first-class.** Every new extractor or extractor method must ship with happy + failure path tests. `avd test --smoke` is part of CI.
10. **Logs on stderr, data on stdout.** Pipe-safe always.
11. **No paid APIs.** No TikHub, no Cobalt SaaS. Self-hosted open-source instances are acceptable.
12. **No login flows.** No "user must log in" prompts. OAuth (Reddit) is the only exception, and uses throwaway script apps the user pre-configures — never their personal account.
13. **Per-extractor file.** Each platform has its own file under `src/avd/extractors/`. Each file declares its fallback chain in priority order.
14. **Per-platform endpoint matrix.** `docs/endpoint-matrix.md` is a living document. When you add or verify an endpoint, update it with date and vantage point.

---

## 7. Agent invocation examples

### Single download
```python
import asyncio
from pathlib import Path
from avd.orchestrator import Orchestrator

async def main():
    orch = Orchestrator()
    result = await orch.download(
        "https://www.tiktok.com/@anyuser/video/6718335390845095173",
        dest=Path("./download"),
    )
    print(result.status, result.artifact_path)

asyncio.run(main())
```

### Batch
```python
results = await orch.batch(
    ["url1", "url2", "url3"],
    dest=Path("./download"),
    opts={"concurrency": 3},
)
```

### Verify an existing file
```python
from avd.verifier import Verifier
report = await Verifier().verify(Path("./download/tiktok/123.mp4"))
print(report.integrity_ok, report.issues)
```

### Run the tester
```python
from avd.tester import Tester
reports = await Tester().run(platforms=["tiktok", "twitter"], smoke=True)
for r in reports:
    print(r.platform, r.downloaded, r.verified)
```

### MCP server mode
```bash
avd mcp   # speaks JSON-RPC 2.0 on stdio
```

---

## 8. Failure modes the agents must NOT cause

| Anti-pattern | Why forbidden |
|---|---|
| Raising `Exception` for "video not found" | Honest negatives must be structured, not exceptions. |
| Writing to the final filename before verification | Half-written files break resume. |
| Hardcoding a User-Agent that triggers a Cloudflare block | Use the per-platform UA from `endpoint-matrix.md`. |
| Storing a resolved TikWM media URL for > 60 s | TikWM URLs expire in minutes. Decode → download gap must be tiny. |
| Hitting a public API more than 3 times in 1 s | Politeness violation. Use the per-host semaphore. |
| Skipping the Verifier for "trusted" extractors | Verifier is the hard gate. No bypass. |
| Logging the full URL with `?xsec_token=...` to plaintext logs | Tokens leak. Hash before logging. |
| Reusing a circuit-broken host without cooldown | Triggers repeated failures. |
| Importing `playwright` or `selenium` in core extractors | Browser automation is opt-in only, in `src/avd/extractors/_browser_fallback.py`. |

---

*This document is the agent contract. Violations are bugs.*
