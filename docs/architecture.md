# Multi-Agent Video Downloader — Architecture

> **Task ID:** 2-b
> **Scope:** A single-machine, pure-Python, multi-agent CLI orchestrator for downloading short-form videos from TikTok, Instagram, Douyin, Rednote (Xiaohongshu), Reddit, and X.com (formerly Twitter).
> **Constraint:** No external LLM API calls. The "agents" are Python modules with typed interfaces, not LLM-backed chat agents.

> **Status:** ✅ v1.2.0 PyPI-published, 2026-10-03. https://pypi.org/project/agent-video-downloader/

---

## 1. Executive Summary

This document specifies a **multi-agent Python orchestration system** built around four cooperating agent modules:

| Agent       | Responsibility                                                       |
|-------------|----------------------------------------------------------------------|
| Orchestrator| Receives a URL, routes it to the right extractor, runs the fallback chain, and reports results. |
| Verifier    | Validates the downloaded artifact: file size > 0, MIME type, ffprobe streams, integrity (decode-able). |
| Truth       | Cross-references downloaded metadata against the **original platform's** published metadata (title, duration, author, view count) to detect "fake" downloads (wrong clip, re-upload, watermark-removed mismatch). |
| Tester      | Runs end-to-end self-tests on the local machine with curated sample URLs per extractor. |

### Pattern selection rationale

A short survey of the multi-agent landscape (CrewAI, AutoGen, LangGraph, custom):

- **CrewAI / AutoGen / LangGraph** are LLM-orchestration frameworks. They are designed around chat-style message passing between LLM-backed agents. They are heavy, opinionated, and **not appropriate** for a pure-Python CLI tool with no LLM in the loop.
- **LangGraph's "state graph"** concept, however, is genuinely useful as a mental model: a finite state machine where each node is a Python function and edges are transitions conditioned on state.
- The recommended pattern is therefore a **custom LangGraph-inspired state machine**, where each "agent" is a Python class implementing a small Protocol, and the orchestrator is a sequential/branching state graph.

This gives us:
- Zero LLM dependency
- Pure-Python, testable with pytest
- Easy to reason about (state is explicit, not emergent)
- Backwards-compatible with all the resilience primitives (`tenacity`, `pybreaker`) we want to reuse.

---

## 2. System Architecture Diagram (ASCII)

```
                            ┌──────────────────────────────────┐
                            │            CLI Layer              │
                            │  (Typer commands + Rich UI)       │
                            │  avd download <url> | avd test    │
                            │  avd verify <file> | avd truth    │
                            └──────────────┬───────────────────┘
                                           │
                                           ▼
            ┌────────────────────────────────────────────────────────────┐
            │                      Orchestrator                          │
            │  ┌───────────┐  ┌──────────────┐  ┌────────────────────┐  │
            │  │ URL Parser │→ │ Router Table │→ │ Fallback Chain Mgr │  │
            │  └───────────┘  └──────────────┘  └────────────────────┘  │
            │         │                                  │               │
            │         ▼                                  ▼               │
            │  ┌──────────────────────────────────────────────────┐      │
            │  │              Extractor Registry                 │      │
            │  │  TikTok │ Instagram │ Douyin │ Rednote │ Reddit │      │
            │  │  X.com  │ Generic-yt-dlp │ gallery-dl │ direct │      │
            │  └──────────────────────────────────────────────────┘      │
            └─────────────────────────────┬──────────────────────────────┘
                                          │  (artifact path + metadata)
                   ┌──────────────────────┼──────────────────────┐
                   ▼                      ▼                      ▼
        ┌─────────────────┐    ┌──────────────────┐    ┌──────────────────┐
        │     Verifier    │    │   Truth Agent    │    │   State Store    │
        │  ffprobe + MIME │    │ platform API call│    │ SQLite + JSON    │
        │  integrity scan │    │ title/duration ✓ │    │ resume + history  │
        └────────┬────────┘    └────────┬─────────┘    └──────────────────┘
                 │                      │
                 └──────────┬───────────┘
                            ▼
              ┌──────────────────────────┐
              │  Tester (avd test ...)   │
              │  per-extractor samples   │
              │  pytest-style fixtures   │
              └──────────────────────────┘
                            │
                            ▼
              ┌──────────────────────────┐
              │  Output + Reporting      │
              │  file://download/...     │
              │  logs/run-<ts>.jsonl     │
              │  rich summary table      │
              └──────────────────────────┘
```

### Horizontal cross-cutting concerns

```
┌──────────────────────────────────────────────────────────────────────┐
│  Cross-Cutting Services (used by every agent)                       │
│                                                                      │
│  • Config (pydantic-settings, .env + TOML)                          │
│  • Logging (structlog → JSONL in logs/, rich console mirror)        │
│  • Resilience: tenacity retries + pybreaker circuit breaker         │
│  • HTTP: httpx.AsyncClient (HTTP/2, connection pool, proxy switch)  │
│  • Concurrency: asyncio.Semaphore per host + ProcessPoolExecutor    │
│  • State: SQLite (jobs table) + per-job .state.json (resumable)    │
│  • Dead-Letter Queue: logs/dlq.jsonl (replayable)                  │
└──────────────────────────────────────────────────────────────────────┘
```

---

## 3. Agent Roles & Interfaces

Each agent is a Python class implementing a `Protocol` (PEP 544). This gives us structural typing — a duck-typed contract without inheritance noise — and makes every agent trivially mockable in pytest.

### 3.1 Orchestrator

```python
# src/agents/orchestrator.py
from typing import Protocol, runtime_checkable
from pathlib import Path

class DownloadResult(BaseModel):
    url: str
    platform: str
    status: Literal["ok", "partial", "failed"]
    artifact_path: Path | None
    metadata: dict            # normalized: title, duration_s, uploader, view_count
    extractor_chain: list[str]  # e.g. ["yt-dlp", "direct-api", "html-scrape"]
    attempts: int
    verifier_report: dict | None
    truth_report: dict | None
    error: str | None

@runtime_checkable
class Orchestrator(Protocol):
    async def download(self, url: str, *, dest: Path, opts: dict) -> DownloadResult: ...
    async def batch(self, urls: list[str], *, dest: Path, opts: dict) -> list[DownloadResult]: ...
    def supported(self) -> list[str]: ...   # returns ["tiktok","instagram",...]
```

**Concrete implementation:** `OrchestratorAgent`. It owns the `ExtractorRegistry`, the per-host circuit breakers, and the asyncio scheduler.

### 3.2 Verifier

```python
# src/agents/verifier.py
class VerifierReport(BaseModel):
    artifact_path: Path
    exists: bool
    size_bytes: int
    mime_type: str | None            # from `file --mime-type` or magic
    has_video_stream: bool
    has_audio_stream: bool
    duration_s: float | None
    codec_video: str | None          # e.g. "h264"
    codec_audio: str | None          # e.g. "aac"
    container: str | None            # e.g. "mp4"
    integrity_ok: bool               # ffmpeg -v error -f null decode test
    issues: list[str]               # human-readable problems

@runtime_checkable
class Verifier(Protocol):
    async def verify(self, artifact: Path, *, expected_meta: dict | None = None) -> VerifierReport: ...
```

**Concrete implementation:** `FfprobeVerifier`. Shells out to `ffprobe -v quiet -print_format json -show_format -show_streams` and runs an additional `ffmpeg -v error -f null -` decode pass for integrity.

### 3.3 Truth Agent

```python
# src/agents/truth.py
class TruthReport(BaseModel):
    url: str
    platform: str
    source_meta: dict        # what the platform's page/API says
    downloaded_meta: dict   # what the file says (via Verifier + yt-dlp info)
    matches: dict[str, bool]  # {"title": True, "duration": True, "author": False, ...}
    confidence: float       # 0.0-1.0
    verdict: Literal["verified", "suspicious", "unverifiable"]

@runtime_checkable
class TruthAgent(Protocol):
    async def cross_check(self, url: str, downloaded_meta: dict) -> TruthReport: ...
```

**Concrete implementation:** `TruthAgent`. Per-platform "source fetchers" hit the platform's public oEmbed / public web page / API endpoint, normalize metadata, and compare fuzzy (Levenshtein on title, ±2 s on duration, exact match on author id when possible).

### 3.4 Tester

```python
# src/agents/tester.py
class TestReport(BaseModel):
    platform: str
    sample_url: str
    extractor_used: str
    downloaded: bool
    verified: bool
    truth_checked: bool
    duration_s: float
    error: str | None

@runtime_checkable
class Tester(Protocol):
    async def run(self, platforms: list[str] | None = None, *, smoke: bool = True) -> list[TestReport]: ...
    def samples(self) -> dict[str, list[str]]: ...  # platform -> sample URLs
```

**Concrete implementation:** `SelfTester`. Loads `tests/fixtures/sample_urls.json` and runs the full pipeline on each. Reuses the Orchestrator and Verifier under the hood.

---

## 4. Extractor Plugin Pattern

Borrowed directly from yt-dlp's own extractor pattern: each platform has a `class XxxExtractor` with a class attribute listing the URL patterns it accepts, a class attribute declaring its priority, and a method that performs the actual work. yt-dlp's own architecture proves this scales to >1,000 sites.

```python
# src/extractors/base.py
from typing import Protocol, runtime_checkable
from pathlib import Path

class ExtractorMeta(BaseModel):
    name: str                       # "tiktok", "instagram", "yt-dlp-generic"
    priority: int = 100             # lower = tried first
    url_patterns: list[str]         # regex patterns; empty = catch-all
    platforms: list[str]            # ["tiktok"] or [] for cross-cutting
    requires_network: bool = True

class ExtractOutcome(BaseModel):
    ok: bool
    artifact_path: Path | None
    metadata: dict                  # normalized schema (see §6)
    extractor_name: str
    error: str | None = None
    raw_info: dict | None = None    # raw yt-dlp info_dict for debugging

@runtime_checkable
class Extractor(Protocol):
    meta: ExtractorMeta
    async def extract(self, url: str, *, dest: Path, opts: dict) -> ExtractOutcome: ...
```

### 4.1 Concrete extractor families

| Family             | Implementation                                  | Use                                              |
|--------------------|-------------------------------------------------|--------------------------------------------------|
| `YtdlExtractor`    | Wraps `yt_dlp.YoutubeDL` as a Python library    | Primary for most URLs (TikTok, IG, Reddit, X)   |
| `GalleryDlExtractor`| Shells out to `gallery-dl`                     | Fallback for image-heavy or playlist platforms  |
| `DirectApiExtractor`| Custom httpx calls to platform API endpoints  | When yt-dlp extractor is broken or rate-limited |
| `HtmlScrapeExtractor`| BeautifulSoup4 / parsel over the public page  | Last-resort fallback; reads `<meta>` og:video tags |
| `MirrorExtractor`  | Re-runs `YtdlExtractor` against a known mirror  | For 403/rate-limited sources                     |

### 4.2 Registry and routing

```python
# src/extractors/registry.py
class ExtractorRegistry:
    def __init__(self) -> None:
        self._extractors: list[Extractor] = []

    def register(self, ext: Extractor) -> None:
        self._extractors.append(ext)
        self._extractors.sort(key=lambda e: e.meta.priority)

    def candidates_for(self, url: str, platform: str | None = None) -> list[Extractor]:
        # 1. Filter by URL pattern match
        matched = [e for e in self._extractors if any(p.match(url) for p in e.meta.compiled_patterns)]
        # 2. If platform specified, prefer extractors tagged for that platform
        if platform:
            platform_first = [e for e in matched if platform in e.meta.platforms]
            platform_first += [e for e in matched if not e.meta.platforms]  # cross-cutting
            return platform_first
        return matched or self._fallback_generic()
```

This is the "best-effort first, fallback chain second" pattern. Candidates are tried in order; the first to return `ok=True` wins.

---

## 5. Fallback Chain Pattern

This is the heart of the system. The orchestrator builds an ordered list of candidate extractors per URL, then iterates with retry/backoff/circuit-breaker semantics.

### 5.1 The canonical fallback chain

```
┌──────────────────────────────────────────────────────────────────────────────┐
│ Fallback Chain (per URL)                                                    │
│                                                                              │
│  1. yt-dlp (primary)         ◄── tries built-in extractor for platform     │
│      ▼ on failure / 403 / no_streams                                          │
│  2. yt-dlp with opts         ◄── different UA, cookies, --no-playlist      │
│      ▼ on failure                                                             │
│  3. gallery-dl               ◄── alternative engine                         │
│      ▼ on failure                                                             │
│  4. Direct API extractor     ◄── platform public API (oEmbed/JSON-LD)      │
│      ▼ on failure                                                             │
│  5. HTML scrape extractor   ◄── parse og:video meta tags, fetch <source>   │
│      ▼ on failure                                                             │
│  6. Mirror / proxy retry     ◄── try yt-dlp through known-good mirror      │
│      ▼ on failure                                                             │
│  7. Dead-Letter Queue        ◄── write to logs/dlq.jsonl for later replay   │
└──────────────────────────────────────────────────────────────────────────────┘
```

### 5.2 Chain implementation

```python
# src/orchestrator/chain.py
from tenacity import AsyncRetrying, stop_after_attempt, wait_exponential_jitter, retry_if_exception_type

class FallbackChain:
    def __init__(self, registry: ExtractorRegistry, opts: dict) -> None:
        self.registry = registry
        self.opts = opts

    async def run(self, url: str, dest: Path) -> ExtractOutcome:
        candidates = self.registry.candidates_for(url, platform=detect_platform(url))
        last_outcome: ExtractOutcome | None = None

        for i, ext in enumerate(candidates):
            try:
                async for attempt in AsyncRetrying(
                    stop=stop_after_attempt(3),
                    wait=wait_exponential_jitter(initial=1, max=30, jitter=2),
                    retry=retry_if_exception_type((httpx.HTTPError, asyncio.TimeoutError)),
                    reraise=True,
                ):
                    with attempt:
                        outcome = await ext.extract(url, dest=dest, opts=self.opts)
                        if outcome.ok:
                            outcome.extractor_name = ext.meta.name
                            return outcome
                        last_outcome = outcome
                        # Don't retry if the URL is genuinely 404 / private
                        if outcome.error and "404" in outcome.error:
                            break
            except (httpx.HTTPError, asyncio.TimeoutError) as e:
                last_outcome = ExtractOutcome(ok=False, artifact_path=None,
                                               metadata={}, extractor_name=ext.meta.name,
                                               error=f"retries_exhausted: {e}")
                continue

        # All extractors failed → DLQ
        await self._dead_letter(url, dest, last_outcome)
        return last_outcome or ExtractOutcome(ok=False, ...)
```

### 5.3 Scenario-specific fallback rules

#### A. yt-dlp fails for a URL

| Cause                       | Action                                                        |
|----------------------------|---------------------------------------------------------------|
| Extractor not found         | Skip to step 4 (Direct API)                                  |
| `DownloadError: HTTP 403`   | Try alternative User-Agent + Referer headers; try with cookies; try mirror CDN; try `--no-playlist` |
| `DownloadError: no video formats found` | Try Direct API; try HTML scrape for `og:video` |
| `UnsupportedError`          | Move to gallery-dl, then HTML scrape                         |
| Geo-block                   | Try mirror or proxy if `proxy_url` configured; else DLQ     |
| Login required              | Mark unverifiable; DLQ with `reason=login_required`          |

#### B. API endpoint is rate-limited (HTTP 429 or heuristic)

```python
# Strategy:
# 1. Respect Retry-After header if present (httpx exposes it)
# 2. Exponential backoff with jitter (tenacity wait_exponential_jitter)
# 3. After 3 retries, switch User-Agent (rotate from pool)
# 4. After 6 retries, switch endpoint (e.g. web vs API)
# 5. After 9 retries, switch proxy (if available)
# 6. Per-host circuit breaker trips → that host gets a 5-min cooldown
```

Implemented with `tenacity` + `pybreaker.CircuitBreaker`:

```python
from pybreaker import AsyncCircuitBreaker

host_breakers: dict[str, AsyncCircuitBreaker] = defaultdict(
    lambda: AsyncCircuitBreaker(fail_max=5, reset_timeout=300)
)

async def call_with_breaker(host: str, fn, *args, **kwargs):
    async with host_breakers[host].context:
        return await fn(*args, **kwargs)
```

#### C. Final m3u8/mp4 returns 403

Per yt-dlp community pattern (confirmed via search: "HTTP 403: update yt-dlp first, try --no-playlist, cookie refresh"):

```
1. Try yt-dlp with --no-playlist (often fixes 403 on segment URLs)
2. Retry with different User-Agent (mobile UA often passes)
3. Retry with explicit Referer = page URL
4. Retry with cookies (refresh via yt-dlp --cookies-from-browser)
5. Try alternative CDN mirror (per-platform mirror list)
6. Try Direct API extractor (some platforms serve mp4 directly)
7. Try HTML scrape (fetch og:video, direct-fetch that URL with browser-like headers)
8. If all fail → DLQ
```

### 5.4 Dead-Letter Queue

```jsonl
# logs/dlq.jsonl  — one line per failed URL, replayable with `avd replay dlq.jsonl`
{"ts":"2026-02-12T08:01:14Z","url":"https://...","platform":"tiktok",
 "last_extractor":"direct-api","last_error":"HTTP 429","attempts":9,
 "context":{"ua_pool_index":3,"proxy_used":null,"cookies_used":false}}
```

The DLQ is a JSONL file (chosen over SQLite for replayability and grep-ability). The CLI provides `avd replay <dlq>` to re-run failed URLs after a fix.

---

## 6. State Machine for a Single Download

A single URL passes through these states. Each transition is logged and persisted to the SQLite jobs table, so an interrupted run can be resumed.

```
                          ┌──────────────┐
            ─────────────►│   PENDING    │
                          └──────┬───────┘
                                 │ orchestrator picks up
                                 ▼
                          ┌──────────────┐
                          │   ROUTING    │  ◄── URL pattern matched, candidate list built
                          └──────┬───────┘
                                 │
                                 ▼
                          ┌──────────────┐
                          │  EXTRACTING  │  ◄── fallback chain iterating
                          └──────┬───────┘
                      ┌──────────┴──────────┐
                      ▼                     ▼
                ┌──────────┐          ┌──────────┐
                │ DOWNLOAD │          │ EXTRACT_ │
                │   _OK    │          │  FAILED  │
                └────┬─────┘          └────┬─────┘
                     │                     │
                     ▼                     ▼
                ┌──────────┐          ┌──────────┐
                │ VERIFYING│          │   DLQ'ED  │  (terminal)
                └────┬─────┘          └──────────┘
              ┌───────┴────────┐
              ▼                ▼
        ┌──────────┐     ┌──────────┐
        │ VERIFIED │     │ VERIFY_  │
        │   _OK    │     │  FAILED  │  → delete artifact, → DLQ
        └────┬─────┘     └──────────┘
             │
             ▼
        ┌──────────┐
        │ TRUTH_   │
        │  CHECK   │
        └────┬─────┘
        ┌────┴────────┐
        ▼             ▼
   ┌─────────┐   ┌──────────┐
   │  DONE   │   │ TRUTH_   │
   │ (ok)    │   │ SUSPIC.  │  (warn but keep artifact)
   └─────────┘   └──────────┘
```

### State persistence schema (SQLite)

```sql
CREATE TABLE jobs (
    id           TEXT PRIMARY KEY,    -- uuid4 hex
    url          TEXT NOT NULL,
    platform    TEXT,
    state        TEXT NOT NULL,        -- one of above
    extractor    TEXT,                 -- last extractor tried
    artifact     TEXT,                 -- path or NULL
    attempts     INTEGER DEFAULT 0,
    created_at   TEXT NOT NULL,
    updated_at   TEXT NOT NULL,
    error        TEXT,
    meta_json    TEXT                  -- normalized metadata snapshot
);
CREATE INDEX idx_jobs_state ON jobs(state);
CREATE INDEX idx_jobs_url ON jobs(url);
```

Resume logic: on `avd download --resume <job_id>`, load the row, restart from the state's "entry action" (e.g. VERIFYING re-runs verify, EXTRACTING re-runs chain).

---

## 7. Data Flow

End-to-end for a single URL, e.g. `https://www.tiktok.com/@user/video/123`:

```
User invokes:   avd download https://www.tiktok.com/@user/video/123
   │
   ▼
[CLI Layer (Typer)]  ── parses args, loads config, opens SQLite, starts Rich progress
   │
   ▼
[Orchestrator.download(url, dest, opts)]
   │
   ├─ detect_platform(url)            → "tiktok"
   ├─ registry.candidates_for(url)   → [YtdlExtractor, DirectApiTikTok, HtmlScrape]
   │
   ▼
[FallbackChain.run]
   │
   ├─ attempt 1: YtdlExtractor.extract(url)
   │     └─ yt-dlp (as lib) returns info_dict + downloads to dest/<id>.mp4
   │     └─ outcome.ok = True
   │
   ▼
[Verifier.verify(artifact_path, expected_meta=info_dict)]
   │
   ├─ os.path.getsize   → 4.2 MB (> 0 ✓)
   ├─ file --mime-type  → video/mp4 ✓
   ├─ ffprobe JSON      → streams: 1 video (h264), 1 audio (aac), duration=18.4s ✓
   ├─ ffmpeg decode     → no errors ✓
   └─ report.integrity_ok = True
   │
   ▼
[TruthAgent.cross_check(url, downloaded_meta)]
   │
   ├─ TikTokSourceFetcher.fetch(url) → {title:"...", author:"@user", duration_s:18.4, ...}
   ├─ compare:
   │     title:      Levenshtein ratio 0.96 ≥ 0.85 ✓
   │     duration:   |18.4 - 18.4| < 2s ✓
   │     author:     "@user" == "@user" ✓
   └─ verdict = "verified", confidence = 0.94
   │
   ▼
[Orchestrator writes DownloadResult]
   │
   ├─ SQLite jobs row → state="DONE"
   ├─ logs/run-<ts>.jsonl append
   └─ Rich summary table printed to console

Output on disk:
   download/tiktok/123-<sha1-8>.mp4
   download/tiktok/123-<sha1-8>.meta.json   (normalized metadata sidecar)
   logs/run-20260212-080114.jsonl
   logs/jobs.db                              (SQLite)
```

---

## 8. Error Handling Matrix

Each row is an error class; each column is a handler. "⇒ DLQ" means the job is moved to the dead-letter queue for manual or scheduled replay.

| Error class                          | Detected by              | Retry? | Fallback action                                              | Terminal? |
|--------------------------------------|--------------------------|--------|--------------------------------------------------------------|-----------|
| Network timeout / DNS                | httpx.TimeoutException   | yes ×3 | Backoff; switch UA; switch proxy if available                | no        |
| HTTP 429 Too Many Requests           | status code              | yes ×3 | Honor Retry-After; backoff; switch UA; switch endpoint       | no        |
| HTTP 403 Forbidden                   | status code              | yes ×2 | Try `--no-playlist`, Referer, cookies, mirror CDN, then DLQ | no → DLQ  |
| HTTP 404 Not Found                   | status code              | no     | Mark `unverifiable`; ⇒ DLQ                                   | yes       |
| HTTP 5xx                             | status code              | yes ×3 | Backoff; retry                                               | no        |
| SSL/TLS error                         | httpx.ConnectError       | yes ×2 | Retry with `verify=False` flag (opt-in); else DLQ            | no → DLQ  |
| Extractor not supported              | yt-dlp UnsupportedError  | no     | Move to next extractor in chain                              | no        |
| No video formats found               | yt-dlp DownloadError     | no     | Move to Direct API / HTML scrape                              | no        |
| Geo-blocked                          | yt-dlp DownloadError     | no     | Try proxy / mirror if configured; else ⇒ DLQ                 | no → DLQ  |
| Login required                       | yt-dlp LoginRequired     | no     | Mark unverifiable; ⇒ DLQ with reason                         | yes       |
| Captcha challenge                     | HTML scrape detect       | no     | ⇒ DLQ                                                        | yes       |
| ffprobe reports 0 streams            | Verifier                 | no     | Delete artifact; restart chain at next extractor             | no        |
| ffprobe decode errors                | Verifier (ffmpeg -f null)| no     | Delete artifact; restart chain at next extractor             | no        |
| File size 0 / truncated              | Verifier                 | no     | Delete artifact; restart chain at next extractor             | no        |
| Truth mismatch (title radically off) | TruthAgent               | no     | Keep artifact; warn; mark `truth=suspicious` in DB           | no        |
| Disk full / write error              | OS (OSError)             | no     | Abort batch; persist state for resume                        | yes       |
| Circuit breaker open (host)          | pybreaker                | no     | Skip extractors for this host; try mirrors / API only        | no        |
| KeyboardInterrupt                    | Python                   | no     | Persist current state; mark PENDING for resume               | yes       |

### Error → outcome mapping

- **Retryable + recoverable** → tenacity retries, then continues chain.
- **Retryable + unrecoverable** (after retries) → fallback to next extractor.
- **Non-retryable + recoverable** (e.g. extractor unsupported) → next extractor immediately.
- **Non-retryable + unrecoverable** (404, login required, captcha) → terminal, DLQ.

---

## 9. Testing Strategy

Three layers, inspired by the "testing trophy" pattern (more integration, fewer e2e).

### 9.1 Unit tests (fast, no network)

```python
# tests/unit/test_router.py
def test_router_tiktok_url_picks_ytdl_first(registry):
    cands = registry.candidates_for("https://www.tiktok.com/@u/video/1")
    assert cands[0].meta.name == "yt-dlp"
    assert "direct-api-tiktok" in [c.meta.name for c in cands]
```

- Mock the extractor classes; assert routing logic, fallback ordering, state transitions, DLQ writes.
- Target: <2 s, >80% line coverage on `src/orchestrator/` and `src/extractors/base.py`.

### 9.2 Integration tests (network, no real download)

Use **VCR.py-style cassettes** (or `respx` for httpx) to mock platform API responses. Verify the Verifier against real ffprobe on tiny fixture videos (committed to `tests/fixtures/`).

```python
# tests/integration/test_verifier.py
async def test_verifier_passes_on_valid_clip(valid_clip):
    report = await FfprobeVerifier().verify(valid_clip)
    assert report.has_video_stream and report.has_audio_stream
    assert report.integrity_ok
```

### 9.3 End-to-end tests (real network, real download) — the Tester agent

The Tester agent **is** the e2e layer. It downloads from a curated, slowly-rotating list of public sample URLs per platform:

```json
// tests/fixtures/sample_urls.json
{
  "tiktok":     ["https://www.tiktok.com/@tiktok/video/7106594312232456107"],
  "instagram":  ["https://www.instagram.com/reel/Cabcdef.../"],
  "douyin":     ["https://www.douyin.com/video/7106594312232456107"],
  "rednote":    ["https://www.xiaohongshu.com/explore/abc123"],
  "reddit":     ["https://www.reddit.com/r/.../comments/.../"],
  "x":          ["https://x.com/user/status/123"]
}
```

- Run via `avd test [--smoke | --full]`.
- `--smoke`: one URL per platform, short timeout (15 s), expect at least 4/6 to pass.
- `--full`: all sample URLs, longer timeout (60 s), generates a per-platform report.
- CI-friendly: skips network if `AVD_OFFLINE=1`, falls back to unit + integration only.

### 9.4 Property tests

- Verifier on synthetic truncated/garbage files should always fail (using `hypothesis`).
- FallbackChain should never reach `DONE` state if `Verifier` returned `integrity_ok=False`.

### 9.5 CI matrix

| Step | Trigger        | Network | What runs                       |
|------|----------------|---------|---------------------------------|
| L1   | every push     | off     | unit + integration + lint        |
| L2   | nightly        | on      | smoke test via `avd test --smoke`|
| L3   | weekly         | on      | full `avd test --full` + report  |

---

## 10. Async & Concurrency Model

### 10.1 Per-host semaphore

```python
# Limit to 3 concurrent connections per host (TikTok, IG, etc.)
host_semaphores: dict[str, asyncio.Semaphore] = defaultdict(
    lambda: asyncio.Semaphore(3)
)

async def with_host_limit(host: str, coro):
    async with host_semaphores[host]:
        return await coro
```

### 10.2 Process pool for CPU-bound work

`ffprobe` / `ffmpeg` calls are CPU-bound and best run in a process pool:

```python
from concurrent.futures import ProcessPoolExecutor

ffmpeg_pool = ProcessPoolExecutor(max_workers=2)

async def run_ffprobe(path: Path) -> dict:
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(ffmpeg_pool, _ffprobe_sync, path)
```

### 10.3 Batch mode

`avd download file.txt` (one URL per line) → orchestrator schedules all URLs through a global `asyncio.Semaphore(N)` (default `N = 4`), per-host semaphores inside, with `asyncio.gather(return_exceptions=True)` so one bad URL doesn't abort the batch.

### 10.4 yt-dlp as a library (no subprocess)

yt-dlp's `YoutubeDL` class is importable and supports `download(urls)` and `extract_info(url)`. Using it as a library avoids subprocess overhead and gives us Python-level access to info_dict. The catch: yt-dlp's `download()` is **blocking I/O**, so it must be wrapped:

```python
async def _ytdl_extract(url: str, opts: dict) -> dict:
    return await asyncio.to_thread(_ytdl_blocking, url, opts)
```

---

## 11. Logging & State Management

### 11.1 Structured logging with `structlog`

- Console: Rich-rendered, human-readable, color-coded by level.
- File: JSONL in `logs/run-<ISO8601>.jsonl`, one event per line, machine-parseable.
- Every log event carries: `job_id`, `url`, `platform`, `extractor`, `state`, `attempt`.

### 11.2 Per-job state file (resumability)

In addition to the SQLite `jobs` table, each running job writes a small `.state.json` next to its artifact:

```json
{
  "job_id": "...",
  "url": "...",
  "platform": "tiktok",
  "state": "VERIFYING",
  "extractor_used": "yt-dlp",
  "artifact": "download/tiktok/123-abc.mp4",
  "attempts": 1,
  "started_at": "2026-02-12T08:01:14Z",
  "updated_at": "2026-02-12T08:01:21Z"
}
```

On resume, `avd download --resume <job_id>` reads this and resumes from the recorded state.

### 11.3 Run summary

At end of batch, print a Rich table:

```
┌────────────┬───────────┬──────────┬──────────┬──────────┬─────────┐
│ URL        │ Platform  │ Extractor│ Verifier │ Truth    │ Size    │
├────────────┼───────────┼──────────┼──────────┼──────────┼─────────┤
│ tiktok/@u  │ tiktok    │ yt-dlp   │ ✓        │ verified │ 4.2 MB  │
│ ig/reel/.. │ instagram │ yt-dlp   │ ✓        │ verified │ 6.1 MB  │
│ x.com/...  │ x         │ gallery  │ ✓        │ suspic.  │ 8.8 MB  │
│ reddit/... │ reddit    │ yt-dlp   │ ✗        │ skipped  │ 0 bytes │ → DLQ
└────────────┴───────────┴──────────┴──────────┴──────────┴─────────┘
```

---

## 12. Recommended Libraries (with versions)

Versions are pinned to what is currently installed in the cloud Linux env (Python 3.12.14) plus additions to add to `requirements.txt`.

### Already installed (verified)

| Library              | Version    | Purpose                                              |
|----------------------|------------|------------------------------------------------------|
| `python`             | 3.12.14    | Runtime (≥ 3.10 required)                           |
| `ffmpeg`/`ffprobe`  | 7.1.5      | Validation + integrity decode                        |
| `httpx`              | 0.28.1     | Async HTTP client (HTTP/2, pool, proxy support)     |
| `aiohttp`            | 3.13.3     | Streaming downloads / async chunks (alt to httpx)   |
| `click`              | 8.1.8      | Low-level CLI primitives (Typer dependency)         |
| `typer`              | 0.23.1     | CLI framework with type-hinted commands              |
| `rich`               | 14.3.3     | Progress bars, tables, console rendering            |
| `pydantic`           | 2.12.5     | Models, config validation, settings                  |
| `pydantic-settings`  | 2.13.1     | Env-driven config (`.env`, `Settings` class)         |
| `pytest`             | 9.0.2      | Test runner                                          |
| `pytest-asyncio`     | 1.3.0      | Async test support                                   |
| `pytest-cov`         | 7.0.0      | Coverage                                              |
| `pybreaker`          | 1.4.1      | Circuit breaker per host                             |

### To add to `requirements.txt`

| Library              | Pin          | Purpose                                              |
|----------------------|--------------|------------------------------------------------------|
| `yt-dlp`             | `>=2025.10.0`| Primary extraction engine (as Python lib)            |
| `gallery-dl`         | `>=1.29.0`   | Fallback extractor for image/video platforms         |
| `tenacity`           | `>=9.0.0`    | Retry / exponential backoff with jitter              |
| `structlog`          | `>=24.4.0`   | Structured JSONL logging                             |
| `respx`              | `>=0.22.0`   | Mock httpx in integration tests                      |
| `beautifulsoup4`    | `>=4.12.0`   | HTML scraping fallback extractor                     |
| `lxml`               | `>=5.3.0`    | Fast HTML parser backend for bs4                     |
| `python-magic`       | `>=0.4.27`   | MIME-type detection (libmagic binding)               |
| `hypothesis`         | `>=6.115.0`  | Property-based tests for Verifier / fallback logic    |
| `Levenshtein`        | `>=0.25.0`   | Fuzzy title matching in Truth agent                  |
| `aiosqlite`          | `>=0.20.0`   | Async SQLite for jobs table                          |

Suggested `requirements.txt`:

```
yt-dlp>=2025.10.0
gallery-dl>=1.29.0
tenacity>=9.0.0
httpx[http2]>=0.28.1
aiohttp>=3.13.3
pybreaker>=1.4.1
structlog>=24.4.0
rich>=14.3.3
typer>=0.23.1
pydantic>=2.12.5
pydantic-settings>=2.13.1
beautifulsoup4>=4.12.0
lxml>=5.3.0
python-magic>=0.4.27
Levenshtein>=0.25.0
aiosqlite>=0.20.0
# dev
pytest>=9.0.2
pytest-asyncio>=1.3.0
pytest-cov>=7.0.0
respx>=0.22.0
hypothesis>=6.115.0
```

---

## 13. Directory Layout

```
agent-video-downloader/
├── docs/
│   └── architecture.md            ← this file
├── src/
│   ├── agents/                    ← the 4 agent modules
│   │   ├── orchestrator.py
│   │   ├── verifier.py
│   │   ├── truth.py
│   │   └── tester.py
│   ├── extractors/                ← pluggable extractors
│   │   ├── base.py                ← Protocol + ExtractorMeta
│   │   ├── registry.py
│   │   ├── ytdlp.py
│   │   ├── gallery_dl.py
│   │   ├── direct_api/
│   │   │   ├── base.py
│   │   │   ├── tiktok.py
│   │   │   ├── instagram.py
│   │   │   └── ...
│   │   └── html_scrape.py
│   ├── orchestrator/              ← chain + state machine
│   │   ├── chain.py
│   │   ├── state.py
│   │   └── dlq.py
│   ├── utils/                     ← cross-cutting
│   │   ├── config.py
│   │   ├── logging.py
│   │   ├── http.py                ← httpx client w/ UA pool + proxy
│   │   ├── ffprobe.py
│   │   └── circuit.py             ← pybreaker per-host wrappers
│   └── cli.py                     ← Typer entry point
├── tests/
│   ├── fixtures/
│   │   ├── sample_urls.json
│   │   └── clips/                 ← tiny valid/invalid mp4s
│   ├── unit/
│   ├── integration/
│   └── e2e/
├── scripts/
│   └── bootstrap.sh              ← install ffmpeg, yt-dlp
├── download/                     ← output root
├── logs/                         ← JSONL logs + jobs.db + dlq.jsonl
├── pyproject.toml
└── requirements.txt
```

---

## 14. CLI Surface (Typer commands)

```
avd download <url|file>        Download one URL or a file of URLs
    --dest DIR                 (default: ./download)
    --resume <job_id>          Resume an interrupted job
    --concurrency N            (default: 4)
    --proxy URL                Route through a proxy
    --no-truth                 Skip the truth cross-check
    --no-verify                Skip the verifier (dangerous)
    --extractor NAME           Force a specific extractor
    --dry-run                  Plan only; print the fallback chain

avd verify <file>              Standalone: verify a previously-downloaded file
avd truth <url> <file>         Standalone: cross-check metadata of existing file
avd test [--smoke|--full]      Run the Tester agent
avd replay <dlq.jsonl>         Re-attempt every URL in a dead-letter file
avd jobs list                  List jobs in the SQLite store
avd jobs show <job_id>         Show one job's state + history
avd config show|path           Inspect resolved config
```

---

## 15. Summary of the Recommended Architecture

- **Pattern:** Custom LangGraph-inspired async state machine. No LLM, no CrewAI/AutoGen overhead.
- **Agents:** Four `Protocol`-typed classes (`Orchestrator`, `Verifier`, `TruthAgent`, `Tester`) — each mockable, each testable in isolation.
- **Extractors:** yt-dlp's plugin pattern (`ExtractorMeta` + `Extractor` Protocol + `ExtractorRegistry`). Five families: `YtdlExtractor` (primary), `GalleryDlExtractor`, `DirectApiExtractor` (per-platform), `HtmlScrapeExtractor`, `MirrorExtractor`.
- **Fallback chain:** Ordered candidate list, tenacity retries inside each step, pybreaker per host, dead-letter queue as terminal failure sink.
- **State:** SQLite `jobs` table + per-job `.state.json` sidecar → fully resumable.
- **Concurrency:** asyncio per host with `Semaphore(3)`, global `Semaphore(4)` for batches, `ProcessPoolExecutor(2)` for ffprobe/ffmpeg.
- **Validation:** ffprobe stream + integrity decode (`ffmpeg -v error -f null -`).
- **Truth:** Per-platform "source fetcher" that hits the platform's public oEmbed / page / API, normalizes metadata, and fuzzy-matches against the downloaded artifact's metadata.
- **CLI:** Typer (typed, sub-commands) + Rich (progress, summary tables).

This satisfies all stated constraints: pure Python, single-machine, no Node, no LLM, Python 3.10+.
