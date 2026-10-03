# TECHSTACK.md — Every Library, Every Version, Why

> **The dependency manifest.** Every line in `requirements.txt` and `pyproject.toml` is justified here. If a library is in the install graph, it has a rationale below. No orphan dependencies.

> **Status:** ✅ v1.2.0 PyPI-published, 2026-10-03. https://pypi.org/project/agent-video-downloader/

---

## 0. Python runtime

| Requirement | Version | Why |
|---|---|---|
| Python | `>=3.10` | `match` statements, `typing.Protocol` defaults, `X | None` syntax. Tested on 3.12.14. |

**Why not 3.11+ only?** 3.10 is the lowest version with `Protocol` runtime_checkable + `TypeAlias` + `ParamSpec` — enough for our agent interfaces. 3.12 is preferred for `@override` decorator and perf.

---

## 1. Core dependencies (production)

| Library | Pin | Purpose | Why this and not the alternative |
|---|---|---|---|
| `httpx` | `>=0.27,<1.0` | Async HTTP client | HTTP/2 support, connection pooling, native async, proxy support. **Alternative considered:** `aiohttp` (no HTTP/2 by default, weaker type hints), `requests` (sync-only). |
| `aiofiles` | `>=23.0` | Async file I/O | Streaming downloads to disk without blocking the event loop. **Alternative:** bare `open()` blocks the loop on large files. |
| `pydantic` | `>=2.7,<3.0` | Data models, validation | All inter-agent payloads are pydantic models — fail-fast on schema drift. **Alternative:** `dataclasses` (no JSON schema generation, weaker validation). |
| `pydantic-settings` | `>=2.3` | Env-driven config | Reads `AVD_*` env vars for runtime config (download dir, log level, proxy URL). |
| `tenacity` | `>=8.5,<10.0` | Retry / backoff | Exponential backoff with jitter for all HTTP calls. **Alternative:** `httpx` retry transport (less flexible, no per-policy composition). |
| `pybreaker` | `>=1.3,<2.0` | Per-host circuit breaker | Stops hammering a host that's returning 5xx. **Alternative:** hand-rolled (we tried — too many edge cases). |
| `rich` | `>=13.0,<14.0` | CLI UX, tables, progress bars | Pretty tables for `avd test`, progress bars for batch. **Alternative:** `tqdm` (less featureful). |
| `click` | `>=8.1,<9.0` | CLI framework | Mature, stable, well-documented. **Alternative considered:** `typer` (built on click, more magic, less control). |
| `python-magic` | `>=0.4.27` | MIME type detection | Verifier uses it as a fallback when magic bytes are ambiguous. **Alternative:** `mimetypes` stdlib (extension-based only, useless for `.part` files). |
| `structlog` | `>=24.0` | Structured JSON logging | All logs are JSONL — machine-readable for downstream agents. **Alternative:** stdlib `logging` (less ergonomic structured output). |
| `aiosqlite` | `>=0.20` | Async SQLite | Orchestrator's job state DB. **Alternative:** `sqlite3` stdlib (sync, blocks event loop). |
| `beautifulsoup4` | `>=4.12` | HTML parsing | Used by Instagram OG fetcher, Rednote HTML scrape, Twitter thread walker. **Alternative:** `lxml` (faster but C-bound, harder to install). We use both: BS4 with `lxml` parser. |
| `lxml` | `>=5.2` | Fast HTML parser | BS4 backend. **Alternative:** `html.parser` stdlib (slower, no XPath). |
| `Levenshtein` | `>=0.25` | Fuzzy string matching | Truth Agent title comparison. **Alternative:** `python-Levenshtein` (same C lib, older API), `rapidfuzz` (heavier). |

---

## 2. Extractor dependencies (per-platform)

### Shared (all platforms)
| Library | Pin | Used by |
|---|---|---|
| `yt-dlp` | `>=2025.10.0` | Used as a Python library (not shelled out). Each extractor may invoke `yt_dlp.YoutubeDL(opts).extract_info(url, download=True)` as one slot in its fallback chain. |

### TikTok
| Library | Pin | Used by |
|---|---|---|
| (none beyond shared) | — | TikTok extractor uses raw `httpx` against `www.tikwm.com/api/` and `www.tiktok.com/embed/v2/`. No TikTok-specific library needed. |

### Instagram
| Library | Pin | Used by |
|---|---|---|
| (none beyond shared) | — | Instagram extractor uses raw `httpx` against `instagram.com/p/<code>/embed/captioned/` with `facebookexternalhit` UA + BS4 for HTML scraping. |

### Douyin
| Library | Pin | Used by |
|---|---|---|
| (none beyond shared) | — | Douyin is documented as out-of-scope for the no-Docker cloud-only constraint. The extractor attempts `yt-dlp Douyin` with self-minted cookies (slot 1), and if that fails, returns `status: empty, reason: datacenter_ip_walled` honestly. A documented "bring your own DTK sidecar" path is in `docs/architecture.md`. |

### Rednote (Xiaohongshu)
| Library | Pin | Used by |
|---|---|---|
| (none beyond shared) | — | Rednote extractor shells out to the vendored `xhs-downloader` binary if present, else falls back to direct HTML scrape + og:video tags via BS4. |

### Reddit
| Library | Pin | Used by |
|---|---|---|
| (none beyond shared) | — | Reddit extractor uses `httpx` with HTTP Basic auth for OAuth2 token, then `oauth.reddit.com` for the post JSON. RSS fallback is `feedparser` (below). |
| `feedparser` | `>=6.0` | Parse `*.rss` Atom feed (slot 3). |

### Twitter / X
| Library | Pin | Used by |
|---|---|---|
| (none beyond shared) | — | Twitter extractor uses raw `httpx` against `api.fxtwitter.com/status/<id>` (primary), `cdn.syndication.twimg.com/tweet-result` (slot 2), `unrollnow.com` (slot 3, BS4 for HTML). |

---

## 3. Dev / test dependencies

| Library | Pin | Purpose |
|---|---|---|
| `pytest` | `>=8.0,<10.0` | Test runner. |
| `pytest-asyncio` | `>=0.23` | Async test support. |
| `pytest-cov` | `>=5.0` | Coverage reports. |
| `pytest-mock` | `>=3.12` | `mocker` fixture for mocking `httpx`. |
| `respx` | `>=0.21` | Mock `httpx` transport for integration tests. |
| `hypothesis` | `>=6.100` | Property-based tests for URL normalization, magic-byte detection. |
| `freezegun` | `>=1.5` | Freeze time for deterministic date-based tests. |

---

## 4. Optional dependencies (opt-in features)

| Library | Pin | Purpose | Why optional |
|---|---|---|---|
| `playwright` | `>=1.40` | Last-resort browser fallback for Douyin | Heavy install (~300 MB), only needed if user explicitly enables browser automation. Not in default `pip install`. |
| `socksio` | `>=1.0` | SOCKS5 proxy support via httpx | Only needed if user configures `AVD_PROXY=socks5://...`. |
| `uvicorn` + `fastapi` | `>=0.30 / >=0.110` | Optional HTTP API mode (`avd serve`) | Most users use the CLI/MCP; the HTTP API is for teams that want a shared instance. |
| `mcp` | `>=1.0` | MCP SDK for the stdio server | The MCP server can also be implemented in pure stdlib (JSON-RPC 2.0 over stdin/stdout), so this is optional. We use the official SDK for spec compliance. |

---

## 5. System tools (must be on PATH)

| Tool | Min version | Used by | Install |
|---|---|---|---|
| `ffmpeg` | `4.4+` (we run 7.1.5) | Verifier (moov atom probe, integrity decode) | `apt install ffmpeg` or `brew install ffmpeg` |
| `ffprobe` | (comes with ffmpeg) | Verifier (probe streams, duration, codec) | same |
| `curl` | any | Scripts (`scripts/install.sh`, `scripts/selftest.sh`) | preinstalled on most systems |
| `git` | any | Versioning, GitHub push | preinstalled |

---

## 6. Why no Docker / Playwright by default?

**Docker:** The user's environment is a cloud CLI agent — Docker may or may not be available. The default install path is `pip install -e .` with no containers. The `Evil0ctal/Douyin_TikTok_Download_API` Docker sidecar is documented as an opt-in for Douyin support; users who need it run `docker compose up -d` separately and point `AVD_DOUYIN_DTK_URL` at it.

**Playwright:** Heavy (~300 MB Chromium download), CI-unfriendly, and the platform UAs hate headless Chromium. Used **only** as a documented last-resort for Douyin verification-wall bypass, behind an opt-in install (`pip install -e .[browser]`).

---

## 7. Why no LangChain / CrewAI / AutoGen?

Those frameworks orchestrate **LLM-backed agents**. Our "agents" are deterministic Python classes that implement `typing.Protocol`. There is no LLM in the runtime loop. The Orchestrator does not "decide" which extractor to use — it picks by URL pattern + priority, deterministically. Adding an LLM orchestration layer would add latency, cost, and non-determinism to a system that should be reproducible from a `jobs.sqlite` row.

The "Truth Agent" name is a homage to `ytagent`'s naming convention, not an LLM.

---

## 8. Dependency graph (visual)

```
avd
├── httpx ─────────── (HTTP, async, HTTP/2)
│   └── socksio (opt) ─ (SOCKS5 proxy)
├── aiofiles ──────── (async file I/O for streaming)
├── pydantic ──────── (all data models)
│   └── pydantic-settings ─ (env config)
├── tenacity ──────── (retry policies)
├── pybreaker ─────── (per-host circuit breaker)
├── rich ──────────── (CLI UX)
├── click ─────────── (CLI framework)
├── python-magic ──── (MIME detection)
├── structlog ─────── (JSONL logging)
├── aiosqlite ─────── (jobs DB)
├── beautifulsoup4 ── (HTML parsing)
│   └── lxml ──────── (parser backend)
├── Levenshtein ───── (fuzzy title match)
├── yt-dlp ────────── (extractor slot, used as Python lib)
├── feedparser ────── (Reddit RSS fallback)
└── (optional) playwright ─ (Douyin browser fallback)
```

---

## 9. Versioning & compatibility policy

- **Major version** bumps when an agent Protocol signature changes (callers must update).
- **Minor version** bumps when a new platform/extractor is added.
- **Patch version** bumps for bug fixes and endpoint matrix updates.

`pyproject.toml` declares:
```toml
[project]
name = "agent-video-downloader"
version = "1.0.0"
requires-python = ">=3.10"
dependencies = [...]   # see §1

[project.optional-dependencies]
browser = ["playwright>=1.40"]
http = ["uvicorn>=0.30", "fastapi>=0.110"]
mcp = ["mcp>=1.0"]
dev = ["pytest>=8.0", "pytest-asyncio>=0.23", ...]   # see §3
```

---

## 10. Dependency review checklist (for adding a new lib)

Before adding a new dependency, answer all of these:

1. **License**: must be MIT, Apache-2.0, BSD, or ISC. No GPL/AGPL (project is MIT).
2. **Maintenance**: last commit < 6 months ago, ≥ 100 GitHub stars OR clear single-maintainer stability.
3. **Pure Python preferred**: C extensions are OK only if they ship manylinux wheels for x86_64 (we don't want to build from source on every CI run).
4. **No transitive bloat**: install footprint must be < 50 MB (excluding yt-dlp + playwright opt-in).
5. **Justified**: write the rationale in this file (`TECHSTACK.md`) before adding to `pyproject.toml`.

---

## 11. Pinned versions (`requirements.txt` for reproducible installs)

```
httpx>=0.27,<1.0
aiofiles>=23.0
pydantic>=2.7,<3.0
pydantic-settings>=2.3
tenacity>=8.5,<10.0
pybreaker>=1.3,<2.0
rich>=13.0,<14.0
click>=8.1,<9.0
python-magic>=0.4.27
structlog>=24.0
aiosqlite>=0.20
beautifulsoup4>=4.12
lxml>=5.2
Levenshtein>=0.25
yt-dlp>=2025.10.0
feedparser>=6.0
# dev
pytest>=8.0,<10.0
pytest-asyncio>=0.23
pytest-cov>=5.0
pytest-mock>=3.12
respx>=0.21
hypothesis>=6.100
freezegun>=1.5
# optional
# playwright>=1.40
# socksio>=1.0
# uvicorn>=0.30
# fastapi>=0.110
# mcp>=1.0
```

---

*Every line above has a reason. If a reason is wrong, the line is wrong — fix both.*
