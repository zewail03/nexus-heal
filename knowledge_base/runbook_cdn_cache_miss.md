# Runbook: CDN Cache-Hit Ratio Collapse

## Alert Pattern
- CloudFront / Fastly / Cloudflare cache-hit ratio drops from > 90 % to < 60 %
- Origin server bandwidth spikes 5–10×
- Origin response latency degrading because of the load
- 504 timeouts from the CDN
- Rising costs on the CDN bill (origin egress is paid per GB)

## Common Root Causes
1. **Cache-key change**: a header was added to the cache key, fragmenting the cache
2. **Bypass header sent by mistake**: `Cache-Control: no-store` accidentally on a hot path
3. **TTL set too low**: deploy reduced TTL from 1 day to 1 minute
4. **Vary header explosion**: `Vary: User-Agent` creates millions of cache entries
5. **Purge storm**: a bulk purge invalidated everything in one shot
6. **Origin returning Set-Cookie**: many CDNs disable caching when Set-Cookie is present

## Diagnosis Steps
1. Look at hit ratio per popular path: CloudFront `cache-hit` field in real-time logs
2. Compare today vs last week: did anything change in the response headers?
3. `curl -I https://cdn.example.com/path` to inspect `Age`, `Cache-Control`, `Vary`, `Set-Cookie`
4. Check recent deploys for header / TTL changes
5. Compare origin egress bandwidth before / after the drop
6. Look for `Vary` value cardinality in the access log

## Remediation
1. **Revert the header change**: restore the previous `Cache-Control` / `Vary` configuration
2. **Strip cookies** for static / public paths at the CDN edge
3. **Increase TTL**: `Cache-Control: public, max-age=86400, s-maxage=86400`
4. **Use a stable cache key**: at the CDN, normalise the URL (strip tracking params) before keying
5. **Pre-warm the cache**: hit a list of top URLs from the CDN itself to repopulate
6. **Throttle origin**: rate-limit origin to protect it while the cache rebuilds

## Rollback
- Revert TTL increases if stale content is being served past its acceptable window
- Restore the original `Vary` if a feature actually needed it

## Similar Past Incidents
- INC-2024-241: someone added `Vary: Authorization` for an A/B test, exploded cache to 80 M entries
- INC-2024-258: deploy set `Cache-Control: no-store` globally to debug staging, shipped to prod by mistake
- INC-2023-264: marketing emitted cookies on `/` for analytics, killed the homepage cache hit ratio
