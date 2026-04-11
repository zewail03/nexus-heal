# Runbook: API Timeout

## Alert Pattern
- API response times exceeding timeout thresholds (> 30s)
- HTTP 504 Gateway Timeout errors from load balancer
- Client-side timeout errors increasing
- Upstream service health checks failing
- Request queue depth growing

## Common Root Causes
1. **Slow database queries**: Missing index or full table scan on large table
2. **Downstream dependency slow**: External API or microservice responding slowly
3. **Thread pool exhaustion**: All worker threads busy, new requests queued
4. **Resource starvation**: CPU or memory pressure causing slow processing
5. **Deadlock**: Database or application-level deadlock blocking requests

## Diagnosis Steps
1. Check application response times: review APM dashboard or logs
2. Check database slow queries: `SELECT * FROM pg_stat_activity WHERE state = 'active' AND query_start < now() - interval '10 seconds';`
3. Check upstream dependencies: `curl -w "%{time_total}" -o /dev/null -s <upstream-url>`
4. Check thread pools: application metrics for active/idle/queued threads
5. Check for deadlocks: `SELECT * FROM pg_locks WHERE NOT granted;`
6. Check load balancer: review 504 count and backend health

## Remediation
1. **Immediate**: Increase timeout thresholds temporarily (buys time)
2. **Database**: Add missing indexes: `CREATE INDEX CONCURRENTLY idx_name ON table(column);`
3. **Kill long queries**: `SELECT pg_cancel_backend(<pid>);`
4. **Scale out**: Add more application instances to handle the load
5. **Circuit breaker**: Enable circuit breaker for slow downstream services
6. **Optimize queries**: Rewrite N+1 queries, add caching for frequent lookups

## Rollback
- Revert timeout changes in load balancer config
- Drop newly created indexes if they cause write performance issues
- Disable circuit breaker if it's incorrectly tripping

## Similar Past Incidents
- INC-2024-012: Missing index on users table caused 45s query times during peak
- INC-2024-036: Payment provider API degraded, causing cascading timeouts
- INC-2023-085: Connection pool leak caused thread pool exhaustion on checkout service
