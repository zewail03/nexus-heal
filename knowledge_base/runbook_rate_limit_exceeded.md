# Runbook: Rate Limit Exceeded

## Alert Pattern
- Spike in HTTP 429 (Too Many Requests) responses from upstream APIs
- `Retry-After` headers appearing in dependency responses
- Internal queue depth growing because retries are stacking
- Customer-facing 5xx caused by a single throttled downstream
- API provider dashboard showing usage near the plan ceiling

## Common Root Causes
1. **Traffic spike past plan limit**: legitimate traffic exceeded the tier's RPM/RPD
2. **Retry storm**: failed requests being retried aggressively, doubling effective load
3. **Single noisy client**: one tenant or one batch job consuming the shared budget
4. **Upstream policy change**: provider lowered limits without notice
5. **Incorrect token reuse**: same API key used by N services, all sharing one quota

## Diagnosis Steps
1. Check 429 rate per upstream: APM dashboard or `grep "status=429" access.log | wc -l`
2. Inspect `Retry-After` headers: `curl -I <upstream>` to see current cooldown
3. Identify hot client: `awk '{print $client_id}' access.log | sort | uniq -c | sort -rn | head`
4. Check provider dashboard for per-key consumption
5. Look for retry loops: `grep "Retrying" app.log | tail -50`

## Remediation
1. **Immediate**: enable circuit breaker on the upstream so we stop hammering it
2. **Add jitter**: change retry policy to exponential backoff with jitter
3. **Per-tenant rate limit**: cap each tenant's outbound calls to the upstream
4. **Request a quota increase**: open a ticket with the provider with current usage data
5. **Cache responses**: if data is read-mostly, add a short TTL cache to reduce calls
6. **Split keys**: provision separate API keys per service to isolate budgets

## Rollback
- Disable circuit breaker once upstream returns to nominal
- Remove temporary cache entries if responses are now stale

## Similar Past Incidents
- INC-2024-072: Stripe webhook retries created a feedback loop, peaked at 8000 RPM (limit 1000)
- INC-2024-088: marketing batch job ran on the same OpenAI key as the customer-facing service
- INC-2023-130: GitHub API silently lowered the unauthenticated limit, broke our CI runners
