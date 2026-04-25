# Runbook: Cache Invalidation Failure

## Alert Pattern
- Stale data being served to users (UI showing prices / counts that no longer match the DB)
- Cache hit ratio is healthy (so the problem isn't cache misses, it's stale hits)
- Customer reports of "I refreshed and it's still wrong"
- Cache invalidation event count near zero in metrics dashboard
- Background invalidator job stopped or crashing

## Common Root Causes
1. **Invalidation pub/sub channel down**: Redis pub/sub disconnect, invalidations dropped silently
2. **Race between write and invalidation**: invalidation fires before the DB commit, then the read repopulates the cache with old value
3. **Per-key TTL too long**: cache holds stale value for 24h before natural expiry
4. **Wrong cache key**: invalidator targets `users:42` but reads use `user:42`
5. **CDN edge purge throttled**: bulk purge rate-limited, only some edges actually invalidated
6. **Cache and DB in different regions**: invalidation queue lagging cross-region

## Diagnosis Steps
1. Pick one stale entry, fetch from cache and DB: `redis-cli GET user:42` vs `psql -c "SELECT * FROM users WHERE id=42"`
2. Check invalidator job liveness: `kubectl get pods -l app=cache-invalidator`
3. Inspect the pub/sub stream: `redis-cli PSUBSCRIBE 'cache:invalidate:*'`
4. Check invalidation lag: `(now - max(invalidation_timestamp))` should be seconds, not minutes
5. Look for race-condition log lines: "set cache after invalidation" pattern
6. Verify cache key consistency: grep both writers and readers for the key format

## Remediation
1. **Manual purge of the bad key**: `redis-cli DEL user:42`
2. **Restart the invalidator** if it's stuck: `kubectl rollout restart deployment/cache-invalidator`
3. **Reduce TTL on user-visible keys**: drop from 24h to 5m as a safety net
4. **Adopt write-through caching**: writer updates the cache directly instead of relying on invalidation
5. **Use cache versioning**: append a version stamp; bumping the version invalidates without explicit DEL
6. **Bulk flush of the affected namespace**: `redis-cli --scan --pattern 'user:*' | xargs redis-cli DEL`

## Rollback
- Restore the previous TTL only after the underlying invalidator bug is fixed
- Re-warm the cache from the DB before flushing in production

## Similar Past Incidents
- INC-2024-336: invalidator pod crash for 2 hours; checkout prices were stale, customers paid old amounts
- INC-2024-352: DB write committed AFTER the invalidation event fired; readers repopulated cache with old row
- INC-2023-371: writer used `users:42`, reader used `user:42` (singular); invalidation never matched the actual key
