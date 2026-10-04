# SKILLS.md — Per-Agent Skill Spec Sheets

> **The capability inventory.** Each agent has a skill sheet: what it can do, what it cannot do, what triggers it, what inputs it accepts, what outputs it produces, and how to invoke it. This is the document an orchestrator reads to decide which agent to call.

> **Status:** ✅ v1.2.0 PyPI-published, 2026-10-03. https://pypi.org/project/agent-video-downloader/

---

## Skill sheet format

Each agent has 7 sections:

1. **Identity** — name, version, file path
2. **Capabilities** — what it can do (bullet list)
3. **Non-capabilities** — what it explicitly does NOT do
4. **Triggers** — when the orchestrator should call it
5. **Inputs** — function signature + schema
6. **Outputs** — return type + schema
7. **Invocation examples** — code samples

---

## Agent 1: Orchestrator

### Identity
- **Name:** `Orchestrator`
- **Version:** 1.0.0
- **File:** `src/avd/orchestrator.py`
- **Implements:** `avd.agents.Orchestrator` Protocol (see `AGENTS.md` §1)

### Capabilities
- Accept a single URL or a batch of URLs.
- Normalize URLs (strip tracking params, expand short links via HEAD-follow chain).
- Route to per-platform extractor registry by URL pattern.
- Drive the fallback chain in priority order.
- Invoke the Verifier after each successful extraction.
- Invoke the Truth Agent after the Verifier passes.
- Persist job state to SQLite (`~/.avd/jobs.sqlite`) for resume.
- Write DLQ entries to `logs/dlq.jsonl` on terminal failure.
- Replay DLQ entries after root-cause fix.
- Honor per-host circuit breakers (skip a host that's returning 5xx).
- Honor per-host semaphores (max 3 in-flight to one host).

### Non-capabilities
- Does NOT decide which extractor to use based on "smarts" — selection is by URL pattern + priority, deterministic.
- Does NOT call LLMs. No AI in the runtime loop.
- Does NOT handle YouTube (use `yt-dlp` directly, or the user's `ytagent` repo).
- Does NOT store cookies, passwords, or OAuth refresh tokens beyond the runtime of one job.
- Does NOT persist downloaded video bytes in any database — only metadata.

### Triggers
- User invokes `avd download <url>` or `avd batch <file>` on the CLI.
- User invokes `avd mcp` and sends an `extract_*` JSON-RPC request.
- Another Python program imports `from avd.orchestrator import Orchestrator` and calls `.download()`.

### Inputs
```python
async def download(self, url: str, *, dest: Path, opts: dict | None = None) -> DownloadResult: ...

async def batch(self, urls: list[str], *, dest: Path, opts: dict | None = None) -> list[DownloadResult]: ...

async def resume(self, job_id: str) -> DownloadResult: ...

async def replay(self, dlq_entry_id: str) -> DownloadResult: ...
```

**`opts` schema:**
```json
{
  "concurrency": 3,                  // batch only
  "force": false,                    // re-download even if file exists
  "no_verify": false,               // skip Verifier (NOT recommended)
  "no_truth": false,                 // skip Truth Agent
  "proxy": "socks5://127.0.0.1:1080", // per-call proxy override
  "user_agent": "..."                // per-call UA override
}
```

### Outputs
`DownloadResult` (see `AGENTS.md` §5 for full schema). Key fields:
- `status`: `"ok" | "empty" | "failed"`
- `reason`: short string code (e.g., `"no_extractor_match"`, `"datacenter_ip_walled"`, `"all_extractors_exhausted"`)
- `artifact_path`: `Path | None`
- `extractor_chain`: `list[str]` — every extractor tried, in order
- `slots_tried`: `list[SlotAttempt]` — per-extractor outcome + failure signal
- `verifier_report`: full VerifierReport if Verifier ran
- `truth_report`: full TruthReport if Truth Agent ran

### Invocation examples
```python
# Python
from avd.orchestrator import Orchestrator
result = await Orchestrator().download("<tiktok-url>", dest=Path("./download"))
```

```bash
# CLI
avd download '<tiktok-url>' --dest ./download
avd batch urls.txt --dest ./download --concurrency 3
avd resume 550e8400-e29b-41d4-a716-446655440000
avd replay dlq-20261003-001
```

```json
// MCP
{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"extract_tiktok","arguments":{"url":"<tiktok-url>","dest":"./download"}}}
```

---

## Agent 2: Verifier

### Identity
- **Name:** `Verifier`
- **Version:** 1.0.0
- **File:** `src/avd/verifier.py`
- **Implements:** `avd.agents.Verifier` Protocol (see `AGENTS.md` §2)

### Capabilities
- Confirm a file exists at a path.
- Check file size against a minimum threshold (default 1 MB).
- Detect file type via magic bytes (MP4 / WebM / MP3 / JPEG / PNG).
- Run `ffprobe -show_format -show_streams` and parse JSON output.
- Confirm duration > 0.
- Confirm at least one stream exists (video or audio).
- Probe MP4 `moov` atom presence at a sane offset (defends against truncated writes).
- Compare against expected metadata (duration ±2 s, codec match preferred).
- Return a structured report (never raise).

### Non-capabilities
- Does NOT re-download a failed file (caller's job).
- Does NOT call the source platform (that's the Truth Agent's job).
- Does NOT validate content correctness (e.g., is this the right video?) — only integrity.
- Does NOT need network access (purely local file checks).

### Triggers
- Orchestrator calls `Verifier.verify(artifact_path, expected_meta=...)` after a successful extraction.
- User invokes `avd verify <path>` on the CLI.
- Tester calls Verifier as part of end-to-end test runs.

### Inputs
```python
async def verify(self, artifact: Path, *, expected_meta: dict | None = None) -> VerifierReport: ...
```

**`expected_meta` schema:**
```json
{
  "duration_s": 12.5,
  "codec_video": "h264",
  "codec_audio": "aac",
  "size_bytes_min": 500000
}
```
All fields optional.

### Outputs
`VerifierReport` (see `AGENTS.md` §2 for full schema). Key fields:
- `exists`: bool
- `size_bytes`: int
- `mime_type`: str | None (e.g., `"video/mp4"`)
- `has_video_stream`: bool
- `has_audio_stream`: bool
- `duration_s`: float | None
- `integrity_ok`: bool — aggregate verdict
- `issues`: `list[str]` — short codes (e.g., `["E_SIZE_TOO_SMALL", "E_MOOV_MISSING"]`)

### Invocation examples
```python
from avd.verifier import Verifier
report = await Verifier().verify(Path("./download/tiktok/123.mp4"))
print(report.integrity_ok, report.issues)
```

```bash
avd verify ./download/tiktok/123.mp4
```

---

## Agent 3: Truth Agent

### Identity
- **Name:** `TruthAgent`
- **Version:** 1.0.0
- **File:** `src/avd/truth_agent.py`
- **Implements:** `avd.agents.TruthAgent` Protocol (see `AGENTS.md` §3)

### Capabilities
- Per-platform source-of-truth fetchers:
  - TikTok: `TikTokOEmbedFetcher` (`www.tiktok.com/oembed?url=...`)
  - Twitter/X: `TwitterSyndicationFetcher` (`cdn.syndication.twimg.com/tweet-result?id=...&token=x`)
  - Reddit: `RedditRSSFetcher` (`www.reddit.com/r/<sub>/.rss`)
  - Instagram: `InstagramOGFetcher` (OG tags with `facebookexternalhit` UA)
  - Rednote: `XHSHTMLFetcher` (JSON-LD + og: tags from explore page)
  - Douyin: `DouyinOGFetcher` (best-effort og: tags from share URL)
- Fuzzy title matching (Levenshtein ratio ≥ 0.7).
- Author ID exact match (case-insensitive).
- Duration match (±2 s).
- Thumbnail host match.
- Media count match.
- Return `verdict`: `"verified" | "suspicious" | "unverifiable"`.

### Non-capabilities
- Does NOT use the same extractor that produced the download — fetches source independently (prevents circular reasoning).
- Does NOT fail the download on `unverifiable` — that's an honest negative.
- Does NOT make sense of subjective content (e.g., "is this video appropriate?") — only metadata cross-check.

### Triggers
- Orchestrator calls `TruthAgent.cross_check(url, downloaded_meta=...)` after the Verifier passes.
- User invokes `avd truth <url> --meta-json path/to/manifest.json` on the CLI.

### Inputs
```python
async def cross_check(self, url: str, downloaded_meta: dict) -> TruthReport: ...
```

**`downloaded_meta` schema:**
```json
{
  "title": "...",
  "author": "<author_handle>",
  "duration_s": 12.5,
  "thumbnail_url": "https://...",
  "media_count": 1
}
```

### Outputs
`TruthReport` (see `AGENTS.md` §3 for full schema). Key fields:
- `source_meta`: `dict` — what the platform said
- `downloaded_meta`: `dict` — what the extractor said
- `matches`: `dict[str, bool]` — field-by-field
- `confidence`: `float` (0.0–1.0)
- `verdict`: `"verified" | "suspicious" | "unverifiable"`

### Invocation examples
```python
from avd.truth_agent import TruthAgent
report = await TruthAgent().cross_check(
    "<tiktok-url>",
    downloaded_meta={"title": "...", "author": "<author_handle>", "duration_s": 12.5}
)
print(report.verdict, report.confidence)
```

---

## Agent 4: Tester

### Identity
- **Name:** `Tester`
- **Version:** 1.0.0
- **File:** `src/avd/tester.py`
- **Implements:** `avd.agents.Tester` Protocol (see `AGENTS.md` §4)

### Capabilities
- Load curated `tests/sample_urls.json`.
- Run `Orchestrator.download()` for each URL.
- Compose `TestReport` per URL with pass/fail status.
- Print a `rich` table to stderr.
- Write JSON results to `tests/results/<timestamp>.json`.
- Support `--smoke` (one URL per platform, ~30 s) and `--full` (all URLs, ~5 min) modes.
- Support `--platform` filter (e.g., `--platform tiktok --platform twitter`).
- Exit code: 0 if smoke threshold met, 1 otherwise.

### Non-capabilities
- Does NOT generate new test URLs on the fly — uses curated list only.
- Does NOT modify the system under test — pure read.
- Does NOT run in parallel within one platform (serial per-platform to be polite).
- Does NOT test the Verifier in isolation — that's `tests/test_agents.py`.

### Triggers
- User invokes `avd test` on the CLI.
- CI runs `avd test --smoke` on every push.
- User runs `scripts/selftest.sh` after install.

### Inputs
```python
async def run(self, platforms: list[str] | None = None, *, smoke: bool = True) -> list[TestReport]: ...
def samples(self) -> dict[str, list[str]]: ...
```

### Outputs
`list[TestReport]` (see `AGENTS.md` §4 for full schema). Plus:
- stderr: rich table with platform / sample URL / extractor used / downloaded / verified / truth verdict / duration / error.
- File: `tests/results/<timestamp>.json` — full JSON dump.
- Exit code: 0/1.

### Invocation examples
```python
from avd.tester import Tester
reports = await Tester().run(platforms=["tiktok", "twitter"], smoke=True)
for r in reports:
    print(r.platform, r.downloaded, r.verified, r.truth_verdict)
```

```bash
avd test --smoke
avd test --full --platform tiktok --platform twitter
```

---

## Inter-agent dispatch table

When the Orchestrator receives a URL, it uses this table to decide which sub-agents to invoke:

| Step | Orchestrator calls | Condition |
|---|---|---|
| 1 | `ExtractorRegistry.candidates(url)` | always |
| 2 | `extractor.extract(url, dest, opts)` for each candidate in priority order | if list non-empty |
| 3 | `Verifier.verify(artifact, expected_meta=...)` | if extractor returned `ok=True` |
| 4 | `TruthAgent.cross_check(url, downloaded_meta=...)` | if Verifier `integrity_ok=True` |
| 5 | persist `DownloadResult` to SQLite | always |
| 6 | write DLQ entry to `logs/dlq.jsonl` | if all extractors exhausted |

---

## Agent dependency graph

```
                    ┌─────────────┐
                    │ Orchestrator│
                    └──────┬──────┘
                           │
              ┌────────────┼────────────┐
              │            │            │
              ▼            ▼            ▼
        ┌──────────┐ ┌──────────┐ ┌──────────┐
        │Extractor │ │ Verifier │ │   Truth  │
        │ Registry │ │          │ │  Agent   │
        └────┬─────┘ └──────────┘ └──────────┘
             │
             │
   ┌─────────┼─────────┬──────────┬──────────┬──────────┐
   │         │         │          │          │          │
   ▼         ▼         ▼          ▼          ▼          ▼
 tiktok   twitter   reddit     instagram   rednote    douyin
```

The Tester is **not** invoked by the Orchestrator — it's invoked by the user/CI to test the Orchestrator itself.

---

## Skill versioning policy

Each agent's `__version__` is bumped when:
- **Major**: its Protocol signature changes (callers must update).
- **Minor**: a new capability is added (e.g., Truth Agent gains a new platform fetcher).
- **Patch**: bug fix or endpoint matrix update.

The Orchestrator checks agent versions on startup:
```python
assert Verifier.__version__ >= "1.0.0"
assert TruthAgent.__version__ >= "1.0.0"
```

A version mismatch raises `RuntimeError("Agent version mismatch: ...")` — fail-fast, no silent breakage.

---

*Each agent's skill sheet is the contract. The Orchestrator reads this file to know who to call and what to pass them.*
