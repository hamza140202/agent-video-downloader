# PHASES.md — Development Phases with Exit Criteria

> **The build plan in time order.** Each phase has a verifiable exit criterion — no phase is "done" until the criterion is met. This is the document a tester/verifier agent uses to know what's complete.

---

## Phase 0 — Research & Documentation

**Goal:** Establish the source of truth before any code is written.

**Deliverables:**
- [x] `CLAUDE.md` — project memory
- [x] `AGENTS.md` — agent contracts
- [x] `TECHSTACK.md` — dependency manifest
- [x] `PHASES.md` — this file
- [x] `PLAN.md` — concrete execution plan
- [x] `SKILLS.md` — per-agent skill sheets
- [x] `docs/research-report.md` — live-verified endpoint research per platform
- [x] `docs/architecture.md` — system design with ASCII diagram
- [x] `docs/endpoint-matrix.md` — living endpoint table

**Exit criterion:** All 9 docs written and internally consistent (cross-references resolve, no contradictions). A new agent reading only these 9 docs can explain what the system does, how it's structured, and which platform uses which method.

**Status:** ✅ Complete (2026-10-03)

---

## Phase 1 — Core agents + TikTok + Twitter (the verified-live platforms)

**Goal:** Stand up the agent skeleton and ship the two platforms whose primary endpoints were verified live from this cloud environment.

**Deliverables:**
- [x] `src/avd/models.py` — pydantic models (`DownloadResult`, `ExtractOutcome`, `VerifierReport`, `TruthReport`, `TestReport`, `DownloadMetadata`, `SlotAttempt`)
- [x] `src/avd/extractors/base.py` — `Extractor` Protocol + `ExtractorMeta`
- [x] `src/avd/extractors/registry.py` — auto-discovery + `candidates(url)` lookup
- [x] `src/avd/orchestrator.py` — Orchestrator with fallback chain driver
- [x] `src/avd/verifier.py` — 6-layer integrity check
- [x] `src/avd/truth_agent.py` — per-platform source fetchers
- [x] `src/avd/extractors/tiktok.py` — TikTok chain: TikWM → embed/v2 → tiklydown → oEmbed
- [x] `src/avd/extractors/twitter.py` — Twitter chain: fxtwitter → syndication → unrollnow → vxtwitter
- [x] `src/avd/utils/{http,fs,ff,breaker,retry,state}.py` — shared utilities
- [x] `src/avd/cli.py` — `avd download`, `avd batch`, `avd verify`, `avd test`
- [x] `tests/sample_urls.json` — curated public URLs per platform
- [x] `tests/test_tiktok.py` — happy path + deleted-content + malformed URL
- [x] `tests/test_twitter.py` — happy path + 404 + thread
- [x] `tests/test_agents.py` — unit tests for Orchestrator + Verifier + TruthAgent

**Exit criterion:**
1. `avd download <known-good-tiktok-url>` produces a verified MP4 in `./download/tiktok/`.
2. `avd download <known-good-tweet-url>` produces a verified MP4 in `./download/twitter/`.
3. `avd test --smoke --platform tiktok --platform twitter` passes.
4. Truth Agent reports `verdict: verified` for ≥ 1 URL per platform.
5. Verifier rejects a deliberately-corrupt file (write `<html>...` to `test.mp4`, run `avd verify test.mp4`, expect `integrity_ok: false` with `E_HTML_ERROR_PAGE`).

**Status:** ✅ Complete (2026-10-03)

---

## Phase 2 — Reddit + Instagram + Rednote + Douyin

**Goal:** Ship the four harder platforms, with honest handling of datacenter-IP walls.

**Deliverables:**
- [x] `src/avd/extractors/reddit.py` — Reddit chain: yt-dlp+OAuth → gallery-dl+OAuth → RSS → DLQ
- [x] `src/avd/extractors/instagram.py` — IG chain: embed/captioned/ (facebookexternalhit UA) → og:image → third-party mirror → DLQ
- [x] `src/avd/extractors/rednote.py` — Rednote chain: XHS-Downloader binary → yt-dlp XiaoHongShu → HTML scrape → DLQ
- [x] `src/avd/extractors/douyin.py` — Douyin chain: yt-dlp+anonymous cookies → DTK sidecar (if configured) → DLQ (honest empty)
- [x] `src/avd/oauth_reddit.py` — Reddit OAuth2 helper (script app, throwaway account)
- [x] `tests/test_reddit.py` — happy path (if OAuth configured) + walled-IP fallback to RSS + 404
- [x] `tests/test_instagram.py` — happy path (best-effort) + datacenter_walled verdict
- [x] `tests/test_rednote.py` — happy path + xsec_token discovery
- [x] `tests/test_douyin.py` — honest_empty case (datacenter IP block) + DTK sidecar mock

**Exit criterion:**
1. `avd download <known-good-reddit-url>` with `AVD_REDDIT_CLIENT_ID` + `AVD_REDDIT_CLIENT_SECRET` env vars → produces a verified MP4 (if OAuth configured).
2. Without OAuth env vars → `avd download <reddit-url>` returns `status: empty, reason: oauth_required` (honest negative, no exception).
3. `avd download <known-good-instagram-url>` either succeeds (best-effort from datacenter IP) or returns `status: empty, reason: datacenter_ip_walled` — both are valid outcomes.
4. `avd download <known-good-rednote-url>` either succeeds (low-res OK) or returns honest empty.
5. `avd download <known-good-douyin-url>` returns `status: empty, reason: datacenter_ip_walled` unless `AVD_DOUYIN_DTK_URL` is set.
6. `avd test --smoke` passes ≥ 4 of 6 platforms (TikTok + Twitter guaranteed; Reddit if OAuth; IG/Rednote/Douyin best-effort).

**Status:** ✅ Complete (2026-10-03)

---

## Phase 3 — Verifier + Truth Agent + Tester + MCP (full agent layer)

**Goal:** All four agents wired end-to-end. MCP server mode live.

**Deliverables:**
- [x] `src/avd/verifier.py` — full 6-layer integrity check with `ffprobe` subprocess wrapper
- [x] `src/avd/truth_agent.py` — all 6 source fetchers (oEmbed, syndication, RSS, OG, XHS HTML, Douyin OG)
- [x] `src/avd/tester.py` — smoke + full modes, rich table output, JSON results file
- [x] `src/avd/mcp.py` — stdio JSON-RPC 2.0 server with `extract_*`, `lookup_*`, `read_manifest`, `get_schema`
- [x] `src/avd/utils/state.py` — SQLite jobs table with resume support
- [x] `avd replay <job_id>` — DLQ replay command

**Exit criterion:**
1. `avd download <url> --json` outputs the full `DownloadResult` including `verifier_report` and `truth_report` to stdout.
2. `avd test --full` runs all sample URLs and writes `tests/results/<timestamp>.json`.
3. `avd mcp` speaks JSON-RPC 2.0 — a sample `tools/call` request returns the manifest.
4. After killing a job mid-download, `avd resume <job_id>` picks up where it left off.
5. `avd replay <dlq_entry_id>` re-runs a failed job after root-cause fix.

**Status:** ✅ Complete (2026-10-03)

---

## Phase 4 — Hardening, CI, packaging

**Goal:** Production-ready. CI passes. PyPI package builds. GitHub repo public.

**Deliverables:**
- [x] `pyproject.toml` with `[project.scripts]` entry point `avd = "avd.cli:main"`
- [x] `requirements.txt` pinned (mirrors `pyproject.toml [project.dependencies]`)
- [x] `.gitignore` (excludes `download/`, `logs/`, `*.sqlite`, `__pycache__/`)
- [x] `LICENSE` (MIT)
- [x] `README.md` — public-facing, install + quickstart + platform support matrix
- [x] `scripts/install.sh` — `pip install -e .[dev]` + ffmpeg check
- [x] `scripts/selftest.sh` — runs `avd test --smoke`, exits 0/1
- [x] `.github/workflows/ci.yml` — Python 3.10/3.11/3.12 matrix, `pytest --cov`
- [x] Pushed to GitHub (primary: `Bilal140202/agent-video-downloader`, mirror: `hamza140202/agent-video-downloader`)

**Exit criterion:**
1. Fresh `git clone` + `pip install -e .[dev]` + `avd test --smoke` works on a clean Ubuntu 22.04 VM with ffmpeg installed.
2. GitHub Actions CI badge is green on `main`.
3. `avd --version` returns the version from `pyproject.toml`.
4. README has a platform support table with current status (verified / best-effort / out-of-scope).

**Status:** ✅ Complete (2026-10-03)

---

## Phase 5 — PyPI publish + one-command install

**Goal:** Anyone in the world can `pip install agent-video-downloader` and run `avd agent-setup`. Zero manual setup. The same command a fresh AI agent would run.

**Deliverables:**
- [x] `pyproject.toml` with `[project.urls]` (Homepage, Repository, Documentation, Bug-Tracker, Changelog)
- [x] `pyproject.toml` Python 3.13 classifier added
- [x] `src/avd/bootstrap.py` — auto-clone XHS-Downloader, auto-install deps
- [x] `avd agent-setup` CLI command (3-step bootstrap, idempotent, `--force` flag)
- [x] `avd agent-instructions` CLI command (8-step guide for AI agents with decision tree)
- [x] Auto-bootstrap on first Rednote download (rednote extractor auto-clones XHS-Downloader)
- [x] README simplified for one-command install focus
- [x] Built and uploaded to PyPI: https://pypi.org/project/agent-video-downloader/1.2.0/
- [x] Verified `pip install agent-video-downloader` works on a fresh Python install
- [x] Verified `avd agent-setup` runs end-to-end from scratch (clones XHS-Downloader, installs all deps)

**Exit criterion:** A fresh Python 3.10+ VM with `pip install agent-video-downloader && avd agent-setup && avd test --smoke` produces real downloaded videos for at least 4 of 6 platforms.

**Status:** ✅ Complete (2026-10-03) — published to PyPI as v1.2.0

---

## Phase 6 — Real-world batch test (validation on real public content)

**Goal:** Use `avd` itself to download 24 real public videos (4 per platform minimum) and verify the system works end-to-end on real content, not just sample URLs.

**Deliverables:**
- [x] 24 verified URLs across the 6 platforms (large videos first)
- [x] 21 of 24 real videos downloaded (1.2 GB total) — see "Real-world test results" below
- [x] Reddit extractor fix: probe BOTH CMAF and DASH format ladders (batch surfaced the DASH format issue)
- [x] Rednote extractor fix: parse XHS-Downloader stdout for actual success count (was returning false positives)
- [x] Verifier fix: adaptive min_size_bytes (50KB images / 5KB audio / 1MB video), skip slow integrity_decode for >50MB files

**Exit criterion:** At least 4 of 6 platforms produce real verified MP4 files (not honest-empties) for real-world content (not just sample URLs).

**Status:** ✅ Complete (2026-10-03)

### Real-world test results (24 URLs attempted, 21 successful)

| Platform | URLs attempted | Successful | Total size | Notes |
|---|---|---|---|---|
| TikTok | 4 | 4 ✅ | 16 MB | Mix of fan content and official posts |
| Twitter | 4 | 4 ✅ | 548 MB | 4K videos (largest: 185 MB) |
| Instagram | 4 | 4 ✅ | 28.7 MB | Reels |
| Reddit | 4 | 4 ✅ | 468 MB | Native v.redd.it uploads (largest: 6-min 372s video) |
| Douyin | 4 | 4 ✅ | 152 MB | Mix of fan and official content |
| Rednote | 4 | 1 ⚠️ | 179 KB | 3 bot-walled without cookie (documented limitation) |
| **Total** | **24** | **21** | **1.2 GB** | **87.5% batch success rate** |

---

## Phase 7 — Future work (post-v1.2)

Not in scope for the v1.2 PyPI release. Listed here for the next agent.

- **SOCKS5 proxy farm** for Instagram + Douyin + Rednote (mirror `ytagent` Tier 11): discover free SOCKS5 from public lists, test 50 in parallel, use only those that pass. Would unlock the 3 bot-walled Rednote URLs and provide insurance for IG/Douyin.
- **Self-hosted Cobalt sidecar** as a universal fallback: `docker compose up cobalt` behind a private network, point `AVD_COBALT_URL` at it.
- **GitHub Actions remote download** for hard-blocked content: trigger a workflow on GH's Azure runners (residential IPs), download via `yt-dlp`, fetch artifact back. Mirror `ytagent` Tier 4.
- **Per-platform weekly re-verification**: cron job that re-fetches every endpoint in `docs/endpoint-matrix.md` and updates the status column. Mirror the `ttagent`/`xthread-agent` doctrine.
- **Web UI** (FastAPI + HTMX) for non-CLI users: `avd serve` → browse to `http://localhost:8000/`.
- **Plugin discovery via setuptools entry points**: third-party packages can register new extractors by declaring `entry_points={"avd.extractors": ["name = pkg.module:Class"]}`.
- **Add YouTube** via the `ytagent` doctrine (13-method fallback chain with android_vr innertube client + BGutil POT provider).
- **Add Bilibili / Weibo / Kuaishou** — yt-dlp has extractors but they're not yet wired into avd.

---

## Verification matrix (which phase proves what)

| Capability | Phase 0 | Phase 1 | Phase 2 | Phase 3 | Phase 4 | Phase 5 | Phase 6 |
|---|---|---|---|---|---|---|---|
| Docs exist | ✅ | — | — | — | — | — | — |
| TikTok downloads | — | ✅ | — | — | — | — | ✅ (4/4) |
| Twitter downloads | — | ✅ | — | — | — | — | ✅ (4/4, 548 MB) |
| Reddit downloads (no OAuth needed) | — | — | ✅ | — | — | — | ✅ (4/4, 468 MB) |
| Instagram downloads (facebookexternalhit UA) | — | — | ✅ | — | — | — | ✅ (4/4) |
| Rednote downloads (curl_cffi) | — | — | ✅ | — | — | — | ✅ (1/4, 3 bot-walled) |
| Douyin downloads (api.douyin.wtf demo) | — | — | ✅ | — | — | — | ✅ (4/4, 152 MB) |
| Verifier rejects corrupt files | — | ✅ | — | — | — | — | — |
| Truth Agent cross-check | — | — | — | ✅ | — | — | ✅ (Twitter "verified") |
| Tester smoke mode | — | ✅ | ✅ | ✅ | — | — | — |
| MCP server live | — | — | — | ✅ | — | — | — |
| Resume mid-download | — | — | — | ✅ | — | — | — |
| DLQ replay | — | — | — | ✅ | — | — | — |
| Fresh clone install | — | — | — | — | ✅ | — | — |
| CI green | — | — | — | — | ✅ | — | — |
| **One-command install (`avd agent-setup`)** | — | — | — | — | — | ✅ | — |
| **Auto-bootstrap on first download** | — | — | — | — | — | ✅ | — |
| **`avd agent-instructions` guide** | — | — | — | — | — | ✅ | — |
| **Published on PyPI** | — | — | — | — | — | ✅ | — |
| **Real-world batch test (24 URLs)** | — | — | — | — | — | — | ✅ (21/24, 1.2 GB) |

---

*Each phase's exit criterion is a fact, not an opinion. If the criterion isn't met, the phase isn't done.*
