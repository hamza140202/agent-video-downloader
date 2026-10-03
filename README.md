# agent-video-downloader (avd)

> **yt-dlp for agents.** A cloud-CLI multi-agent video downloader for **TikTok, Instagram, Douyin, Rednote (Xiaohongshu), Reddit, X.com (Twitter)** — built for AI agents (Claude, GLM, Cursor, Cline) that need to fetch video bytes in long-running task workflows, with no browser, no cookies, no login.

[![CI](https://github.com/Bilal140202/agent-video-downloader/actions/workflows/ci.yml/badge.svg)](https://github.com/Bilal140202/agent-video-downloader/actions)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)

---

## Why?

`yt-dlp` is broken from datacenter IPs for TikTok, Twitter, Reddit, and Instagram (verified live 2026-10-03). Cloud CLI agents (Claude Code, GLM CLI, Cursor, Cline) that need to download videos for tasks like transcription, OCR, content analysis, or archival have no reliable path. This project fixes that with **direct-API fallback chains** that work from cloud IPs without login.

- ✅ TikTok via TikWM mirror API (verified live)
- ✅ Twitter/X via FixTweet API (verified live)
- ⚠️ Reddit via OAuth2 (free script app, throwaway account)
- ⚠️ Instagram best-effort (embed/captioned + og:image + third-party mirrors)
- ⚠️ Rednote/Xiaohongshu best-effort (XHS-Downloader binary or HTML scrape)
- ⚠️ Douyin documented as out-of-scope without self-hosted DTK sidecar

Honest negatives are first-class — `status: empty, reason: datacenter_ip_walled` is a valid result, not an error.

---

## Install

```bash
# System deps (ffmpeg for verification)
sudo apt install -y ffmpeg

# From source (development)
git clone https://github.com/Bilal140202/agent-video-downloader.git
cd agent-video-downloader
pip install -e .[dev]

# Verify
avd --version
avd test --smoke
```

---

## Quickstart

```bash
# Download one video
avd download 'https://www.tiktok.com/@scout2015/video/6718335390845095173' --dest ./download

# Batch (one URL per line)
avd batch urls.txt --dest ./download --concurrency 3

# Verify a previously downloaded file
avd verify ./download/tiktok/6718335390845095173.mp4

# Self-test
avd test --smoke
avd test --full --platform tiktok --platform twitter

# MCP server (stdio JSON-RPC 2.0)
avd mcp
```

---

## Platform support matrix

| Platform | Primary method | Status from cloud IP | Honesty |
|---|---|---|---|
| **TikTok** | `tikwm.com/api/?url=…&hd=1` | ✅ Verified live 2026-10-03 | Full HD video + music + cover |
| **Twitter/X** | `api.fxtwitter.com/status/<id>` | ✅ Verified live 2026-10-03 | All mp4 variants + photos |
| **Reddit** | `yt-dlp Reddit` + OAuth2 | ⚠️ Requires throwaway OAuth app | `oauth_required` if not configured |
| **Instagram** | `embed/captioned/` (facebookexternalhit UA) + og:image + mirrors | ⚠️ Best-effort from datacenter | `datacenter_ip_walled` honest empty if blocked |
| **Rednote** | `XHS-Downloader` binary / yt-dlp XiaoHongShu / HTML scrape | ⚠️ Best-effort, low-res without cookie | `xsec_token_missing` honest empty |
| **Douyin** | `yt-dlp Douyin` + anonymous cookies / DTK sidecar | ❌ Walled without Docker sidecar | `datacenter_ip_walled` honest empty |

---

## Configuration

All config via env vars (or `.env` file):

| Var | Default | Description |
|---|---|---|
| `AVD_DOWNLOAD_DIR` | `./download` | Default download destination |
| `AVD_DB_PATH` | `~/.avd/jobs.sqlite` | SQLite jobs table for resume |
| `AVD_LOG_LEVEL` | `INFO` | `DEBUG` / `INFO` / `WARNING` / `ERROR` |
| `AVD_REDDIT_CLIENT_ID` | — | Reddit OAuth script-app client ID |
| `AVD_REDDIT_CLIENT_SECRET` | — | Reddit OAuth script-app client secret |
| `AVD_REDDIT_USERNAME` | — | Throwaway Reddit username (script-app flow) |
| `AVD_REDDIT_PASSWORD` | — | Throwaway Reddit password (script-app flow) |
| `AVD_DOUYIN_DTK_URL` | — | Self-hosted DTK API base URL (e.g., `http://localhost:8000`) |
| `AVD_PROXY` | — | SOCKS5/HTTP proxy URL for all requests |
| `AVD_USER_AGENT` | `Mozilla/5.0 ...` | Default User-Agent |

---

## Architecture

Four Python agents (NOT LLM-backed — deterministic):

- **Orchestrator** — owns the extractor registry, drives the fallback chain, persists job state.
- **Verifier** — 6-layer file integrity check (size, magic bytes, ffprobe, duration, streams, moov atom).
- **Truth Agent** — cross-references downloaded metadata against the source platform (oEmbed, syndication, RSS, OG tags).
- **Tester** — runs end-to-end on `tests/sample_urls.json`.

```
URL → Orchestrator → [TikTok|Twitter|Reddit|IG|Rednote|Douyin] extractors (fallback chain)
                  → Verifier (ffprobe + magic bytes)
                  → Truth Agent (source cross-check)
                  → verified MP4 + manifest.json
```

Full design: [`docs/architecture.md`](docs/architecture.md).
Full research: [`docs/research-report.md`](docs/research-report.md).

---

## Documentation

- [`CLAUDE.md`](CLAUDE.md) — project memory (read first)
- [`AGENTS.md`](AGENTS.md) — agent contracts & perfection prompting
- [`TECHSTACK.md`](TECHSTACK.md) — every dependency, every version, why
- [`PHASES.md`](PHASES.md) — development phases with exit criteria
- [`PLAN.md`](PLAN.md) — concrete execution plan with task IDs
- [`SKILLS.md`](SKILLS.md) — per-agent skill spec sheets
- [`docs/research-report.md`](docs/research-report.md) — live-verified endpoint research
- [`docs/architecture.md`](docs/architecture.md) — system design
- [`docs/endpoint-matrix.md`](docs/endpoint-matrix.md) — living endpoint table

---

## License

MIT. See [LICENSE](LICENSE).
