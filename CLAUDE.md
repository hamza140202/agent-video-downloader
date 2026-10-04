# CLAUDE.md — Project Memory for AI Agents

> **One source of truth for any AI agent (Claude, GLM, GPT, etc.) that touches this codebase.**
> Read this file first, before reading any other doc or writing any code.

---

## 0. Identity

**Project name:** `agent-video-downloader` (codename `avd`)
**PyPI:** https://pypi.org/project/agent-video-downloader/
**Repo:** https://github.com/hamza140202/agent-video-downloader
**Version:** 1.2.0 (PyPI-published, 2026-10-03)
**Codename:** `avd` — used in CLI entry point, package name, log files.
**Purpose:** A `yt-dlp`-for-agents: a single CLI / Python library that downloads videos from **TikTok, Instagram, Douyin, Rednote (Xiaohongshu), Reddit, X.com (Twitter)** — designed for **cloud-only, headless, no-browser, no-cookie, no-login** environments. Built to be invoked by AI agents (Claude, GLM, Cursor, Cline, etc.) as part of larger task workflows.

**Status:** ✅ **Production-ready, PyPI-published, final stage.** 6/6 platforms download real video bytes (real-world batch test: 21/24 = 87.5% success, 1.2 GB downloaded via `avd` itself).

**Guiding philosophy:** *"It is possible to build."* No wandering, no questions. The CLI environment does not have browser cookies, login sessions, or residential IPs — and that is a fact, not a problem. The system figures out, gracefully.

---

## 1. Operating environment (HARD constraints)

This codebase assumes the runtime is a **cloud Linux VM** with:

| What | Has | Does NOT have |
|---|---|---|
| OS | Linux x86_64 (Ubuntu/Debian) | GUI / desktop / browser |
| Network | Outbound HTTPS, datacenter IP class | Residential IP, SOCKS5 by default |
| Auth | None | User login sessions, browser cookies, OAuth refresh tokens (unless explicitly configured by user) |
| Tools | `python3.10+`, `pip`, `curl`, `wget`, `ffmpeg`/`ffprobe`, `git` | Docker (unless user opts in), Playwright/Chromium (unless user opts in) |
| Filesystem | `/home/z/my-project/` (read-write) | System directories |
| Time | Unbounded (long-running batch jobs OK) | Real-time user interaction |

**Constraint acceptance doctrine:** When a platform (e.g., Instagram, Douyin) is hard-blocked from datacenter IPs without login, the system reports `downloadable: false, reason: datacenter_ip_walled` — **honestly**, not as an error. Honest negatives are first-class results.

---

## 2. What this project IS and IS NOT

### IS

- A **multi-agent orchestrator** that routes URLs through fallback chains and verifies downloads.
- A **plugin-pattern extractor registry** — new platforms / new methods slot in without restructuring.
- A **Python library** (`avd`) importable from other agent code.
- A **CLI** (`avd download <url>`, `avd batch <file>`, `avd verify <path>`, `avd test`).
- An **MCP server** (stdio, JSON-RPC 2.0) for direct use by MCP-aware agents.
- A **proof-of-work system** — every download is verified by ffprobe, magic-byte check, and (where possible) cross-checked against the source platform's metadata.

### IS NOT

- A YouTube downloader (use `yt-dlp` directly, or the user's separate `ytagent` repo).
- A browser automation tool. Playwright/Selenium is a **last-resort, opt-in** extractor only.
- A paid-API consumer. No TikHub, no Cobalt SaaS, no RapidAPI. Self-hosted instances of open-source projects are acceptable.
- A login-credential manager. The system never asks the user for passwords. If OAuth is required (Reddit), the user provides a `client_id`/`client_secret` from a throwaway script app — never their personal account.

---

## 3. Architecture at a glance

```
                  ┌─────────────────────────────────────────────────────┐
                  │                     CLI / MCP                        │
                  │       avd download <url> | avd batch | avd test      │
                  └──────────────────────┬──────────────────────────────┘
                                         │
                          ┌──────────────▼───────────────┐
                          │        Orchestrator         │
                          │  - URL → platform routing    │
                          │  - Fallback chain driver     │
                          │  - Per-host circuit breaker  │
                          │  - SQLite jobs table         │
                          └──────┬──────────┬───────────┘
                                 │          │
                  ┌──────────────▼──┐    ┌──▼───────────────┐
                  │   Extractor     │    │   Truth Agent    │
                  │   Registry      │    │  cross-checks    │
                  │  (per-platform  │    │  downloaded meta │
                  │   fallback      │    │  vs source meta  │
                  │   chain)        │    └──▲───────────────┘
                  └──────┬──────────┘       │
                         │                  │
                ┌────────▼────────┐         │
                │   Verifier      │─────────┘
                │ - ffprobe       │
                │ - magic bytes   │
                │ - size > 0      │
                │ - audio+video   │
                │ - moov atom     │
                └─────────────────┘
                         │
                ┌────────▼────────┐
                │   Tester        │
                │ sample_urls.json│
                │ smoke / full    │
                └─────────────────┘
```

Full architectural spec: see [`docs/architecture.md`](docs/architecture.md).
Full research findings: see [`docs/research-report.md`](docs/research-report.md).

---

## 4. Agents (Python modules, not LLM agents)

The four agents are **plain Python classes** that implement `typing.Protocol` interfaces. They are NOT backed by LLMs — they are deterministic, testable, replayable.

| Agent | File | Role |
|---|---|---|
| `Orchestrator` | `src/agents/orchestrator.py` | Owns the extractor registry, drives the fallback chain, persists job state. |
| `Verifier` | `src/agents/verifier.py` | Shells out to `ffprobe`/`ffmpeg`, checks magic bytes, validates streams. |
| `TruthAgent` | `src/agents/truth_agent.py` | Fetches source-platform metadata (oEmbed, public APIs, RSS) and cross-references against the downloaded artifact. |
| `Tester` | `src/agents/tester.py` | Runs end-to-end on `tests/sample_urls.json`, supports `--smoke` and `--full` modes. |

Each agent is documented in [`AGENTS.md`](AGENTS.md) with its full Protocol signature and contract.

---

## 5. Extractor plugin contract

Every platform-specific decoder implements this interface (see `src/extractors/base.py`):

```python
class Extractor(Protocol):
    meta: ExtractorMeta
    async def extract(self, url: str, *, dest: Path, opts: dict) -> ExtractOutcome: ...
```

`ExtractorMeta` declares the extractor's `name`, `priority` (lower = tried first), `url_patterns` (regex list), `platforms` (e.g. `["tiktok"]`), and `requires_network`.

The Orchestrator picks all extractors whose `url_patterns` match the input URL, sorts by `priority`, and tries them in order until one returns `ok: True`. Failures (exception, `ok: False`, or verifier-rejected artifact) trigger the next extractor in the chain. The terminal failure sink is a JSONL dead-letter queue at `logs/dlq.jsonl`, replayable with `avd replay <job_id>`.

The fallback chain per platform (verified live 2026-10-03) is documented in [`docs/research-report.md`](docs/research-report.md) §6.

---

## 6. File & directory layout

```
agent-video-downloader/
├── CLAUDE.md              ← this file — read first
├── AGENTS.md              ← agent contracts & prompts (perfection prompting)
├── TECHSTACK.md           ← every library, every version, why
├── PHASES.md             ← 4-phase dev plan with exit criteria
├── PLAN.md               ← concrete execution plan with owners
├── SKILLS.md             ← per-agent skill definitions
├── README.md             ← public-facing README
├── pyproject.toml         ← package metadata + dependencies
├── requirements.txt       ← pinned deps for pip install
├── .gitignore
├── src/
│   ├── avd/
│   │   ├── __init__.py
│   │   ├── cli.py                ← Click/Typer entry point
│   │   ├── config.py            ← env-driven config (pydantic-settings)
│   │   ├── models.py            ← pydantic data models (DownloadResult, etc.)
│   │   ├── orchestrator.py      ← Orchestrator agent
│   │   ├── verifier.py          ← Verifier agent
│   │   ├── truth_agent.py       ← TruthAgent
│   │   ├── tester.py            ← Tester
│   │   ├── extractors/
│   │   │   ├── base.py          ← Protocol + ExtractorMeta
│   │   │   ├── registry.py      ← auto-discovery + per-URL candidate list
│   │   │   ├── tiktok.py        ← TikTok fallback chain
│   │   │   ├── instagram.py     ← Instagram fallback chain
│   │   │   ├── douyin.py        ← Douyin fallback chain
│   │   │   ├── rednote.py       ← Xiaohongshu fallback chain
│   │   │   ├── reddit.py        ← Reddit fallback chain
│   │   │   └── twitter.py       ← Twitter/X fallback chain
│   │   ├── utils/
│   │   │   ├── http.py          ← shared httpx async client
│   │   │   ├── ff.py            ← ffprobe/ffmpeg wrappers
│   │   │   ├── fs.py            ← atomic .part → os.replace, magic bytes
│   │   │   ├── retry.py          ← tenacity policies
│   │   │   ├── breaker.py       ← per-host circuit breaker
│   │   │   └── state.py         ← SQLite jobs table
│   │   └── mcp.py               ← MCP stdio server
│   └── tests/
│       ├── conftest.py
│       ├── sample_urls.json
│       ├── test_tiktok.py
│       ├── test_twitter.py
│       ├── test_reddit.py
│       ├── test_instagram.py
│       ├── test_rednote.py
│       ├── test_douyin.py
│       └── test_agents.py
├── docs/
│   ├── architecture.md
│   ├── research-report.md
│   └── endpoint-matrix.md      ← living table of verified endpoints
├── download/                   ← output artifacts (videos, manifests)
├── logs/
│   ├── avd.jsonl               ← structured log
│   └── dlq.jsonl               ← dead-letter queue
└── scripts/
    ├── install.sh
    └── selftest.sh
```

---

## 7. Quickstart (for an agent that just landed in this repo)

**From PyPI (recommended for end-users):**
```bash
pip install agent-video-downloader
avd agent-setup
```

**From source (recommended for developers):**
```bash
git clone https://github.com/hamza140202/agent-video-downloader
cd agent-video-downloader
pip install -e .[dev]
avd agent-setup
```

**Verify + use:**
```bash
avd --version
avd --help
avd agent-instructions   # 8-step usage guide for AI agents
avd test --smoke         # one URL per platform, ~30s
avd download 'https://www.tiktok.com/@anyuser/video/<numeric-id>' --dest ./download
avd batch urls.txt --dest ./download --concurrency 3
avd verify ./download/tiktok/<numeric-id>.mp4
avd jobs
avd replay <job_id>
avd mcp                   # stdio JSON-RPC 2.0 server
```

---

## 8. Source of truth documents (in priority order)

When in doubt, read these in order:

1. **`CLAUDE.md`** (this file) — identity, constraints, file map.
2. **`AGENTS.md`** — agent contracts and prompts.
3. **`docs/architecture.md`** — system design, data flow, error matrix.
4. **`docs/research-report.md`** — what works, what doesn't, why (live-verified 2026-10-03).
5. **`docs/endpoint-matrix.md`** — living table of every public endpoint's status.
6. **`TECHSTACK.md`** — every dependency, version, rationale.
7. **`PHASES.md`** — what's done, what's next, exit criteria.
8. **`PLAN.md`** — concrete execution plan with task IDs.
9. **`SKILLS.md`** — per-agent skill spec sheets.

---

## 9. Coding doctrine (non-negotiable)

1. **Honest negatives are first-class.** `status: "empty"` is a valid result, not an exception.
2. **Logs on stderr, data on stdout.** Always pipe-safe.
3. **Atomic writes only.** Stream to `.part`, verify, `os.replace`. Never leave a half-written artifact.
4. **Provenance trace on every result.** `metadata.extractor_chain`, `metadata.slots_tried`, `metadata.verifier_report`, `metadata.truth_report`.
5. **Politeness is a hard constraint.** Bounded retries, 0.6 s decode sleeps, response caps. Free surfaces must not be abused.
6. **Magic bytes gate every artifact.** MP4 `ftyp`, MP3 `ID3`, JPEG `\xff\xd8`, PNG `\x89PNG`. No file is reported downloaded until its bytes prove its type.
7. **CDN allowlist.** Bytes are only fetched from a known set of CDN hostnames per platform (see `docs/endpoint-matrix.md`). Unknown hostnames are rejected by default.
8. **No silent fallback.** Every extractor swap is logged with the failure signal that triggered it.
9. **stdlib-only where possible.** `httpx`/`pydantic`/`rich` are acceptable; everything else must justify its weight.
10. **Tests are first-class.** Every extractor has happy-path and failure-path tests. `avd test --smoke` is part of CI.

---

## 10. Current build state

| Phase | Status | See |
|---|---|---|
| Phase 0 — Research & docs | ✅ Complete | this file, `docs/` |
| Phase 1 — Core agents + TikTok + Twitter | ✅ Complete | `src/avd/extractors/{tiktok,twitter}.py` |
| Phase 2 — Reddit + Instagram + Rednote + Douyin | ✅ Complete | `src/avd/extractors/{reddit,instagram,rednote,douyin}.py` |
| Phase 3 — Verifier + Truth + Tester + MCP | ✅ Complete | `src/avd/{verifier,truth_agent,tester,mcp}.py` |
| Phase 4 — Hardening, CI, packaging | ✅ Complete | `pyproject.toml`, `scripts/selftest.sh` |
| Phase 5 — PyPI publish + one-command install | ✅ Complete (v1.2.0) | https://pypi.org/project/agent-video-downloader/1.2.0/ |
| Phase 6 — Real-world batch test | ✅ Complete | `download/batch/` (1.2 GB, 21/24 videos) |

**Final status:** ✅ **Production-ready, PyPI-published, final stage.**

- 6/6 platforms download real video bytes from datacenter IPs without login
- 30/30 unit tests pass
- 21/24 real-world videos downloaded (1.2 GB total) — 87.5% batch success rate
- Published on PyPI: `pip install agent-video-downloader`
- One-command install: `avd agent-setup` auto-clones XHS-Downloader + installs deps
- Step-by-step agent guide: `avd agent-instructions`

Live status: see `logs/avd.jsonl` for the most recent run.
Test results: see `tests/results/` for the last `avd test --smoke` output.

---

## 11. How to extend (add a new platform or a new method)

1. **Add an extractor** in `src/avd/extractors/<platform>.py` that implements the `Extractor` protocol.
2. **Register it** in `src/avd/extractors/registry.py` — auto-discovery handles the rest.
3. **Add sample URLs** in `tests/sample_urls.json` under the new platform key.
4. **Write tests** in `src/tests/test_<platform>.py` — at minimum: one happy path, one deleted-content, one auth-walled, one malformed URL.
5. **Update `docs/endpoint-matrix.md`** with the new endpoint(s) you depend on, with verification date and vantage point.
6. **Bump version** in `pyproject.toml` and add a changelog entry.

The fallback chain for your platform should be declared in priority order inside the file — the registry just collects them.

---

## 12. Failure mode reference (for agents debugging a broken run)

| Symptom | Likely cause | Fix |
|---|---|---|
| `status: empty, reason: deleted_or_private` | Source content was removed. | None — honest negative. |
| `status: empty, reason: datacenter_ip_walled` | Platform blocks datacenter IPs without login (Instagram, Douyin, Reddit JSON). | Configure SOCKS5 proxy or self-hosted Cobalt/DTK sidecar. |
| `status: failed, error: E_SHORTLINK_DEAD` | Short URL (`vm.tiktok.com/...`, `xhslink.com/...`) no longer resolves. | None — content gone. |
| `status: failed, error: E_CIRCUIT_OPEN` | Per-host circuit breaker tripped after N failures. | Wait for cooldown (default 5 min) or run `avd reset-breaker <host>`. |
| `verifier_report.integrity_ok: false` | Downloaded file failed ffprobe / magic-byte / moov atom check. | Re-run; if persists, the extractor returned a non-video artifact — bug. |
| `truth_report.verdict: suspicious` | Downloaded metadata doesn't match source (title/duration/author mismatch). | Re-fetch from source; if mismatch persists, may be wrong-video artifact. |
| `extractor_chain: []` | No extractor matched the URL. | Check URL pattern; add extractor in registry. |
| DLQ entry appears | All extractors in chain failed. | `avd replay <job_id>` after fixing the root cause. |

---

## 13. Contact & licensing

- License: MIT (see `LICENSE`).
- **PyPI:** https://pypi.org/project/agent-video-downloader/
- **Repo (primary):** https://github.com/hamza140202/agent-video-downloader
- **Author:** ansaribilal1402 (PyPI), Bilal140202 (GitHub primary account)
- Issues: file on GitHub, with the `metadata.extractor_chain` and `metadata.slots_tried` from your run's manifest attached.
- Install: `pip install agent-video-downloader && avd agent-setup`

---

*This file is the entry point. Everything else flows from here.*
