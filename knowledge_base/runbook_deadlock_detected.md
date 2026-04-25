# Runbook: Database Deadlock Detected

## Alert Pattern
- Spike in `deadlock detected` errors in PostgreSQL/MySQL logs
- Transactions failing with SQLSTATE `40P01` (Postgres) or `1213` (MySQL)
- Endpoint latency tail growing while throughput drops
- One or more sessions stuck in `Lock` wait state for minutes
- Application logs show retry attempts on the same query

## Common Root Causes
1. **Inconsistent lock ordering**: two transactions take the same row-locks in different order
2. **Long-running transaction**: an admin / batch job holds locks while OLTP traffic competes
3. **Missing index**: query escalates to a full table scan, locks far more rows than needed
4. **ORM N+1 with read-then-write**: ORM reads N rows, then writes back in a different order
5. **Hot-row contention**: a single row (e.g. `accounts.balance`) is updated by many tenants

## Diagnosis Steps
1. Pull recent deadlocks: `SELECT * FROM pg_stat_activity WHERE wait_event_type = 'Lock';`
2. Show the deadlock detail: `SELECT * FROM pg_locks WHERE NOT granted;`
3. MySQL equivalent: `SHOW ENGINE INNODB STATUS \G` (look for "LATEST DETECTED DEADLOCK")
4. Check long-running transactions: `SELECT pid, now()-xact_start AS dur, query FROM pg_stat_activity ORDER BY dur DESC NULLS LAST LIMIT 10;`
5. Trace which queries are involved in the cycle from the engine status output

## Remediation
1. **Immediate**: kill the long-running transaction blocking others: `SELECT pg_terminate_backend(<pid>);`
2. **Order locks consistently**: enforce a canonical ordering (e.g. always `account_id ASC`)
3. **Reduce isolation**: drop from `SERIALIZABLE` to `READ COMMITTED` if business semantics allow
4. **Add the missing index**: `CREATE INDEX CONCURRENTLY ...` on the column the deadlock query filters on
5. **Use `SELECT ... FOR UPDATE SKIP LOCKED`**: lets workers process queue rows without contention
6. **Add application-level retry**: deadlocks are transient; retry once with jitter

## Rollback
- Revert isolation-level changes if business invariants were violated
- Drop the new index if it caused unexpected write-amplification

## Similar Past Incidents
- INC-2024-094: order processor and refund worker took inventory locks in opposite order, 3% of orders stuck
- INC-2024-105: nightly analytics job held a 40-minute transaction on `users`, blocked all signups
- INC-2023-145: hot row on `tenant_settings.api_quota` deadlocked under concurrent updates from 200 tenants
