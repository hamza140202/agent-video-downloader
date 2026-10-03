# Living endpoint matrix — re-verified weekly.
# Status: ✅ verified live | ⚠️ best-effort | ❌ broken from datacenter IP | ❓ untested

| Platform | Endpoint | Role | Status | Last verified | Vantage | Failure signal |
|---|---|---|---|---|---|---|
| TikTok | `www.tikwm.com/api/?url=…&hd=1` | decode | ✅ | 2026-10-03 | datacenter | `{"code":-1}` |
| TikTok | `www.tiktok.com/embed/v2/<id>` | decode fallback | ⚠️ | 2026-10-03 | datacenter | shell-only response |
| TikTok | `api.tiklydown.eu.org/api/download?url=…` | decode fallback | ❓ | — | datacenter | — |
| TikTok | `www.tiktok.com/oembed?url=…` | metadata only | ✅ | 2026-10-03 | datacenter | HTTP 404 |
| TikTok | `*.tiktokcdn-us.com` | deliver | ✅ | 2026-10-03 | datacenter | 403 |
| TikTok | `*.tikwm.com` (mirror media) | deliver | ✅ | 2026-10-03 | datacenter | URL expires in minutes |
| Twitter/X | `api.fxtwitter.com/status/<id>` | decode | ✅ | 2026-10-03 | datacenter | `{"code":404}` |
| Twitter/X | `cdn.syndication.twimg.com/tweet-result?id=…&token=x` | decode + sanity | ✅ | 2026-10-03 | datacenter | empty payload |
| Twitter/X | `unrollnow.com/status/<id>` | thread walk | ⚠️ | 2026-10-03 | datacenter | 404 |
| Twitter/X | `api.vxtwitter.com/Twitter/status/<id>` | decode fallback | ❌ | 2026-10-03 | datacenter | Cloudflare challenge |
| Twitter/X | `video.twimg.com/…mp4` | deliver | ✅ | 2026-10-03 | datacenter | 403 |
| Twitter/X | `pbs.twimg.com/…jpg` | deliver | ✅ | 2026-10-03 | datacenter | 403 |
| Reddit | `oauth.reddit.com/comments/<id>.json` | decode (OAuth) | ✅ | 2026-10-03 | datacenter | 401 (no token) |
| Reddit | `www.reddit.com/comments/<id>.json` | decode (no auth) | ❌ | 2026-10-03 | datacenter | 403 / blocked HTML |
| Reddit | `www.reddit.com/r/<sub>/.rss` | metadata only | ✅ | 2026-10-03 | datacenter | empty feed |
| Reddit | `v.redd.it/<hash>/DASH_1080.mp4` | deliver | ❌ | 2026-10-03 | datacenter | 403 |
| Reddit | `preview.redd.it/…jpg` | deliver (image) | ✅ | 2026-10-03 | datacenter | 403 |
| Instagram | `i.instagram.com/api/v1/media/<id>/info/` | decode (no auth) | ❌ | 2026-10-03 | datacenter | 403 login_required |
| Instagram | `www.instagram.com/p/<code>/embed/captioned/` (UA: facebookexternalhit) | decode | ⚠️ | 2026-10-03 | datacenter | `contextJSON:null` |
| Instagram | `www.instagram.com/p/<code>/` (UA: facebookexternalhit) | og:image only | ⚠️ | 2026-10-03 | datacenter | empty shell |
| Instagram | `ddinstagram.com/p/<code>` | mirror | ⚠️ | 2026-10-03 | datacenter | 404 |
| Instagram | `*.cdninstagram.com` / `*.fbcdn.net` | deliver | ✅ | 2026-10-03 | datacenter | 403 (when URL stale) |
| Rednote | `www.xiaohongshu.com/explore/<id>?xsec_token=…` | decode | ⚠️ | 2026-10-03 | datacenter | needs xsec_token |
| Rednote | `xhslink.com/<code>` | short link | ✅ | 2026-10-03 | datacenter | 301 to explore |
| Rednote | `sns-video.xhscdn.com/…mp4` | deliver | ✅ | 2026-10-03 | datacenter | 403 |
| Douyin | `www.douyin.com/video/<id>` | decode | ❌ | 2026-10-03 | datacenter | verification wall |
| Douyin | self-hosted `Evil0ctal/Douyin_TikTok_Download_API` v5 | decode (Docker) | ❓ | — | self-hosted | — |
| Douyin | `*.douyinvod.com` | deliver | ✅ | 2026-10-03 | datacenter | 403 |

---

## Re-verification protocol

Run this weekly (or when a download starts failing):

```bash
# 1. TikTok
curl -sLA 'Mozilla/5.0' 'https://www.tikwm.com/api/?url=https%3A%2F%2Fwww.tiktok.com%2F%40scout2015%2Fvideo%2F6718335390845095173&hd=1' | head -c 200

# 2. Twitter
curl -sLA 'Mozilla/5.0' 'https://api.fxtwitter.com/status/20' | head -c 200

# 3. Twitter sanity
curl -sLA 'Mozilla/5.0' 'https://cdn.syndication.twimg.com/tweet-result?id=20&token=x' | head -c 200

# 4. Reddit RSS
curl -sLA 'python:avd:1.0.0 (by /u/avd_bot)' 'https://www.reddit.com/r/aww/.rss' | head -c 200

# 5. Instagram embed
curl -sLA 'facebookexternalhit/1.1' 'https://www.instagram.com/p/CxYz1234567/embed/captioned/' | head -c 200

# 6. Douyin (will fail — documented)
curl -sLA 'Mozilla/5.0' 'https://www.douyin.com/video/7126745726494821640' | head -c 200
```

Update the `Status` and `Last verified` columns from the curl outputs. Flips are facts.
