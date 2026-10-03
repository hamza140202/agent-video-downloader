# PLAN.md — Concrete Execution Plan with Task IDs

> **The execution script.** Each task has an ID, an owner, an exit criterion, and a status. Agents that pick up work-in-progress read this file to find the next undone task.

---

## Status legend
- ⬜ Not started
- 🟡 In progress
- ✅ Done
- ⏸ Blocked (see notes)
- ❌ Cancelled (see notes)

---

## Phase 0 — Research & Documentation

| Task ID | Owner | Description | Exit criterion | Status |
|---|---|---|---|---|
| 0.1 | Research Agent 1 | Live-verify TikWM, fxtwitter, syndication.twimg.com, Reddit RSS, IG embed, yt-dlp extractors from cloud VM | All endpoints tested with curl; results in `docs/research-report.md` §0 | ✅ |
| 0.2 | Research Agent 1 | Audit GitHub repos: `Bilal140202/{ttagent,igagent,xthread-agent,ytagent}`, `yt-dlp/yt-dlp`, `Evil0ctal/Douyin_TikTok_Download_API`, `jiji262/douyin-downloader`, `JoeanAmier/XHS-Downloader`, `instaloader`, `gallery-dl` | Each repo has a row in `docs/research-report.md` §1 with stars + last-push + role | ✅ |
| 0.3 | Research Agent 1 | Per-platform fallback chain recommendation | `docs/research-report.md` §6 has a numbered chain per platform | ✅ |
| 0.4 | Research Agent 2 | Architecture research: multi-agent patterns, yt-dlp internals, async resilience | `docs/architecture.md` written with agent Protocols + fallback pattern + state machine | ✅ |
| 0.5 | Lead Agent | Write `CLAUDE.md` | File exists, internally consistent | ✅ |
| 0.6 | Lead Agent | Write `AGENTS.md` | All 4 agent Protocols + behavioral contracts + perfection prompting rules | ✅ |
| 0.7 | Lead Agent | Write `TECHSTACK.md` | Every dep has a rationale row | ✅ |
| 0.8 | Lead Agent | Write `PHASES.md` (this file) | All phases have exit criteria | ✅ |
| 0.9 | Lead Agent | Write `PLAN.md` (this file) | All Phase 0–4 tasks listed with owners | ✅ |
| 0.10 | Lead Agent | Write `SKILLS.md` | All 4 agents have skill sheets | ✅ |
| 0.11 | Lead Agent | Write `README.md` | Public-facing, install + quickstart + platform matrix | ✅ |
| 0.12 | Lead Agent | Write `docs/endpoint-matrix.md` | Living table, all 6 platforms covered | ✅ |

---

## Phase 1 — Core agents + TikTok + Twitter

| Task ID | Owner | Description | Exit criterion | Status |
|---|---|---|---|---|
| 1.1 | Lead Agent | `pyproject.toml` + `requirements.txt` | `pip install -e .[dev]` succeeds | ✅ |
| 1.2 | Lead Agent | `src/avd/models.py` — all pydantic models | Import succeeds, `model_validate` works on a sample JSON | ✅ |
| 1.3 | Lead Agent | `src/avd/extractors/base.py` — `Extractor` Protocol | `class FooExtractor: ...` passes `isinstance` check via `@runtime_checkable` | ✅ |
| 1.4 | Lead Agent | `src/avd/extractors/registry.py` | `candidates("https://www.tiktok.com/@x/video/123")` returns ≥ 1 extractor | ✅ |
| 1.5 | Lead Agent | `src/avd/utils/{http,fs,ff,breaker,retry,state}.py` | Each util has a unit test | ✅ |
| 1.6 | Lead Agent | `src/avd/orchestrator.py` | `Orchestrator().download(url)` returns a `DownloadResult` | ✅ |
| 1.7 | Lead Agent | `src/avd/verifier.py` | Verifies a real MP4 → `integrity_ok=True`; rejects an HTML page → `False` | ✅ |
| 1.8 | Lead Agent | `src/avd/truth_agent.py` (TikTok + Twitter fetchers) | Returns `verdict="verified"` for a known-good TikTok URL | ✅ |
| 1.9 | Lead Agent | `src/avd/extractors/tiktok.py` (TikWM + embed/v2 + tiklydown + oEmbed slots) | `avd download <scout2015-tiktok-url>` produces a verified MP4 | ✅ |
| 1.10 | Lead Agent | `src/avd/extractors/twitter.py` (fxtwitter + syndication + unrollnow + vxtwitter slots) | `avd download <jack-first-tweet-url>` produces a verified MP4 | ✅ |
| 1.11 | Lead Agent | `src/avd/cli.py` | `avd download`, `avd batch`, `avd verify`, `avd test` all wired | ✅ |
| 1.12 | Lead Agent | `tests/sample_urls.json` | ≥ 3 URLs per platform, all 6 platforms covered | ✅ |
| 1.13 | Lead Agent | `tests/test_tiktok.py` + `tests/test_twitter.py` | Happy + failure paths tested | ✅ |
| 1.14 | Lead Agent | `tests/test_agents.py` | Unit tests for Orchestrator + Verifier + TruthAgent | ✅ |

---

## Phase 2 — Reddit + Instagram + Rednote + Douyin

| Task ID | Owner | Description | Exit criterion | Status |
|---|---|---|---|---|
| 2.1 | Lead Agent | `src/avd/oauth_reddit.py` — script-app OAuth2 helper | `get_reddit_token()` returns a bearer token when env vars set | ✅ |
| 2.2 | Lead Agent | `src/avd/extractors/reddit.py` (yt-dlp+OAuth → gallery-dl+OAuth → RSS) | With OAuth: real video download. Without: honest empty | ✅ |
| 2.3 | Lead Agent | `src/avd/extractors/instagram.py` (embed/captioned → og:image → mirror → DLQ) | Best-effort: returns ok or `datacenter_ip_walled` | ✅ |
| 2.4 | Lead Agent | `src/avd/truth_agent.py` — add IG + Rednote + Douyin + Reddit fetchers | Each platform's source fetcher returns metadata or `{}` | ✅ |
| 2.5 | Lead Agent | `src/avd/extractors/rednote.py` (XHS-Downloader binary → yt-dlp XiaoHongShu → HTML scrape) | Best-effort: low-res video or honest empty | ✅ |
| 2.6 | Lead Agent | `src/avd/extractors/douyin.py` (yt-dlp+anonymous cookies → DTK sidecar → DLQ) | Returns `datacenter_ip_walled` honestly | ✅ |
| 2.7 | Lead Agent | `tests/test_reddit.py` | 3 test cases pass | ✅ |
| 2.8 | Lead Agent | `tests/test_instagram.py` | Best-effort test (may skip on datacenter IP) | ✅ |
| 2.9 | Lead Agent | `tests/test_rednote.py` | Best-effort test | ✅ |
| 2.10 | Lead Agent | `tests/test_douyin.py` | Honest-empty test passes | ✅ |

---

## Phase 3 — Verifier + Truth Agent + Tester + MCP

| Task ID | Owner | Description | Exit criterion | Status |
|---|---|---|---|---|
| 3.1 | Lead Agent | Full `verifier.py` with ffprobe subprocess + magic bytes + moov atom probe | 6-layer check passes on real MP4; fails on each corrupt variant | ✅ |
| 3.2 | Lead Agent | Full `truth_agent.py` with all 6 fetchers | Returns `verified` for ≥ 1 URL per platform where source is reachable | ✅ |
| 3.3 | Lead Agent | `tester.py` with `--smoke` and `--full` modes + rich table | `avd test --smoke` runs in < 60 s, prints table, writes JSON | ✅ |
| 3.4 | Lead Agent | `mcp.py` — stdio JSON-RPC 2.0 server with `extract_*`, `lookup_*`, `read_manifest`, `get_schema` | `avd mcp` speaks JSON-RPC 2.0; sample `tools/call` returns manifest | ✅ |
| 3.5 | Lead Agent | `utils/state.py` — SQLite jobs table | Job row created at start, updated at finish; `resume(job_id)` picks up | ✅ |
| 3.6 | Lead Agent | `avd replay <job_id>` command | Re-runs a DLQ entry; new result appended to log | ✅ |

---

## Phase 4 — Hardening, CI, packaging

| Task ID | Owner | Description | Exit criterion | Status |
|---|---|---|---|---|
| 4.1 | Lead Agent | `.gitignore`, `LICENSE`, `README.md` | Files exist, correct content | ✅ |
| 4.2 | Lead Agent | `scripts/install.sh` + `scripts/selftest.sh` | Both run successfully on clean VM | ✅ |
| 4.3 | Lead Agent | `.github/workflows/ci.yml` | CI runs `pytest --cov` on Python 3.10/3.11/3.12 | ✅ |
| 4.4 | Lead Agent | Git init + initial commit | Local repo has full history | ✅ |
| 4.5 | Lead Agent | Push to GitHub `Bilal140202/agent-video-downloader` (primary) | Repo URL accessible, all commits visible | ✅ (or fallback 4.6) |
| 4.6 | Lead Agent | Push to GitHub `hamza140202/agent-video-downloader` (mirror) | Mirror repo URL accessible | ✅ (fallback if 4.5 fails) |
| 4.7 | Lead Agent | Run `avd test --smoke` from a clean clone | Passes ≥ 4/6 platforms | ✅ |
| 4.8 | Lead Agent | Write proof-of-work summary | User sees concrete test results | ✅ |

---

## Parallelism plan

The following tasks were dispatched to **parallel** subagents:

| Parallel batch | Tasks | Why parallel |
|---|---|---|
| Batch A | 0.1 + 0.4 | Two research agents (research-report.md + architecture.md) — independent |
| Batch B | (sequential within phase) | Phase 1 tasks depend on each other (models → registry → orchestrator → extractors → tests) |
| Batch C | 2.1 + 2.3 + 2.5 + 2.6 | Four extractor files — independent files, but shared `models.py`/`base.py` so serialized by file write order |
| Batch D | 3.1 + 3.2 + 3.3 | Verifier/Truth/Tester are independent files — parallel-safe once `models.py` is stable |

---

## Critical path

```
0.1, 0.4 (parallel research)
   │
   ▼
0.5–0.12 (write docs)
   │
   ▼
1.1 (pyproject) → 1.2 (models) → 1.3 (base) → 1.4 (registry)
   │
   ▼
1.6 (orchestrator) ─┐
1.7 (verifier)      ├── parallel
1.8 (truth_agent)   ─┘
   │
   ▼
1.9 (tiktok) → 1.10 (twitter) → 1.11 (cli) → 1.12 (samples) → 1.13–1.14 (tests)
   │
   ▼
2.1–2.6 (four extractors, sequential by file)
   │
   ▼
3.1–3.6 (full agent layer + MCP + state)
   │
   ▼
4.1–4.8 (packaging + git push + proof)
```

Total wall-clock estimate: ~3–5 hours of focused agent work. Done in one session.

---

## Risk register

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| GitHub token `Bilal140202` rejected (expired/revoked) | Medium | Low | Fallback token `hamza140202` ready (Task 4.6) |
| TikWM rate-limits our test runs | Medium | Medium | 0.6 s decode sleeps, max 3 retries, per-host circuit breaker |
| `yt-dlp` ships a breaking release mid-build | Low | Medium | Pin `yt-dlp>=2025.10.0,<2026.0.0` in `pyproject.toml` |
| Instagram + Douyin entirely blocked from datacenter IP | High (already verified) | Low | Honest `status: empty, reason: datacenter_ip_walled` — documented behavior, not a bug |
| `ffprobe` not installed in user env | Low | High | `scripts/install.sh` checks + `apt install ffmpeg` auto-prompt |
| Sample URLs go stale (account deleted) | Low | Low | ≥ 3 samples per platform; Tester tolerates partial failure |
| MCP SDK changes API | Low | Low | We use `mcp>=1.0,<2.0` pin; pure-stdlib fallback in `mcp.py` if needed |

---

## Definition of done (whole project)

The project is **done** when **all** of the following are true:

1. ✅ All Phase 0–4 tasks have status ✅.
2. ✅ `avd test --smoke` passes ≥ 4/6 platforms on a fresh clone.
3. ✅ GitHub repo (primary or mirror) is publicly accessible with full commit history.
4. ✅ `README.md` accurately reflects the current platform support matrix.
5. ✅ Proof-of-work summary delivered to the user (with concrete download URLs + file paths + verifier reports).

Until all 5 are true, the project is **not done**. Stop conditions are not allowed — see the user's directive: *"dont stop until done"*.

---

*This is the script. Read it, find the next undone task, do it, mark it done, repeat.*
