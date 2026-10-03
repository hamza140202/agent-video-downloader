# Contributors

This project acknowledges the following contributors. Attribution is research-grade — listed contributors provided architectural patterns, code review, design feedback, or infrastructure that materially shaped the project.

## Author / Maintainer

- **ansaribilal1402** (PyPI: `ansaribilal1402`)
  - Project lead, primary author, PyPI publisher
  - Designed and implemented the multi-agent architecture (Orchestrator + Verifier + Truth Agent + Tester)
  - Authored all six platform extractors with their per-platform fallback chains
  - Designed and built the `avd agent-setup` and `avd agent-instructions` commands for one-command install
  - Published v1.2.0 to PyPI on 2026-10-03

## Research Sources

The following open-source projects (maintained by their respective authors) were studied as primary research sources during the audit phase. Their READMEs, per-platform endpoint matrices, and architectural patterns were transferred into this project's codebase. The attribution is intellectual — these projects are not imported, installed, or vendored; their patterns are reflected in this project's design.

- **Bilal140202/ytagent** (YouTube reference, doctrine source)
  - Contributed the 6-layer Verifier pattern (size, magic bytes, ffprobe, duration, streams, moov atom)
  - Contributed the tiered bypass doctrine (Tier 1: direct mirrors → Tier 2: SOCKS5 proxy farm → Tier 3: federated frontends → Tier 4: GitHub Actions remote download farm)
  - Contributed the "slots, not brands" replaceable-slot principle
  - Contributed the MCP wrapper pattern (JSON-RPC 2.0 over stdio, honest empties are not errors)
  - Contributed the Truth Agent cross-reference pattern (simplified in this project to advisory-only per-call)
  - See `docs/research-blog.md` §3.1 for detailed per-pattern attribution

- **Bilal140202/ttagent** (TikTok reference)
  - Contributed the 4-slot TikTok decode chain (TikWM → embed/v2 → tiklydown → oEmbed)
  - Contributed the honest-empty-as-structured-outcome pattern (`status: "empty"`, not exception)
  - See `docs/research-blog.md` §3.1 for detailed attribution

- **Bilal140202/igagent** (Instagram reference)
  - **Critical contribution**: documented the `facebookexternalhit/1.1` User-Agent bypass for Instagram's datacenter-IP wall — this was the single most important architectural transfer in the project
  - Contributed the `no_video_url_exposed` honest-negative distinction (different from `datacenter_ip_walled`)
  - See `docs/research-blog.md` §3.1 for detailed attribution

- **Bilal140202/xthread-agent** (Twitter/X reference)
  - Contributed the fxtwitter → vxtwitter decoder chain
  - Contributed the thread walker (unrollnow → threadreaderapp) with `replying_to_status` filtering
  - Contributed the living endpoint matrix format (status / failure signal / last-verified date / vantage point) — adopted verbatim as `docs/endpoint-matrix.md`
  - Contributed the weekly re-verification protocol
  - See `docs/research-blog.md` §3.1 for detailed attribution

## How to Contribute

Contributions are welcome. Please:

1. File an issue first to discuss the change you want to make
2. Fork the repo, create a feature branch
3. Add or update tests for your change (smoke + unit tests are mandatory; integration tests for new endpoints)
4. Update `docs/endpoint-matrix.md` if you add or verify a new endpoint
5. Submit a pull request with the `metadata.extractor_chain` and `metadata.slots_tried` from a test run attached

For AI agent contributors (Claude, Cursor, Cline, GLM, GPT, etc.): read `CLAUDE.md` first, then `AGENTS.md`, then `docs/architecture.md`. Run `avd agent-instructions` for the 8-step usage guide.

## License

MIT. See [LICENSE](LICENSE).
