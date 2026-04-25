# Runbook: Database Replication Lag

## Alert Pattern
- `pg_stat_replication.replay_lag` > 30 s on a Postgres replica
- MySQL `Seconds_Behind_Master` > 60 s
- Read-replica returning stale data ("user just signed up but their profile 404s")
- WAL / binlog disk on the primary growing because the replica isn't acknowledging
- Replica unable to catch up: lag growing monotonically

## Common Root Causes
1. **Primary write spike**: bulk import / migration creating WAL faster than replica can apply
2. **Replica IO bound**: storage on the replica is slower than on the primary
3. **Single-threaded apply (MySQL row-based replication)**: replica can't parallelize a heavy write workload
4. **Long-running query on the replica**: blocks WAL apply because of MVCC conflicts
5. **Network bandwidth between primary and replica**: insufficient for the change rate
6. **Replication slot was abandoned**: WAL accumulated indefinitely, replica started after a long pause

## Diagnosis Steps
1. Check current lag: `SELECT now() - pg_last_xact_replay_timestamp() AS lag;` on the replica
2. Check what's blocking apply: `SELECT * FROM pg_stat_activity WHERE wait_event_type = 'Lock';`
3. Inspect IO on the replica: `iostat -xm 1 5`
4. Check WAL generation rate on the primary: `SELECT pg_wal_lsn_diff(pg_current_wal_lsn(), '0/0');` over time
5. For MySQL: `SHOW SLAVE STATUS \G` — `Seconds_Behind_Master`, `Slave_SQL_Running_State`
6. Check replication slot status: `SELECT slot_name, active, restart_lsn FROM pg_replication_slots;`

## Remediation
1. **Cancel long-running replica queries**: `SELECT pg_terminate_backend(<pid>);`
2. **Pause the bulk write on the primary** if it's an admin job: it can resume after replica catches up
3. **Upgrade replica IO**: provision higher IOPS on its volume (gp3 / io2)
4. **Enable parallel apply** (MySQL): `SET GLOBAL slave_parallel_workers = 8`
5. **Add a second replica** to spread read traffic, reduce contention with apply
6. **Drop the abandoned slot**: `SELECT pg_drop_replication_slot('<slot>')` (if you don't need it)

## Rollback
- Re-create the replication slot if it turned out to be needed
- Reduce parallel-apply workers if they cause out-of-order issues with non-deterministic statements

## Similar Past Incidents
- INC-2024-487: nightly archive job rewrote a 200 GB table; replicas lagged 4 hours, read traffic served stale data
- INC-2024-501: someone forgot to drop a replication slot for a decommissioned replica, primary's WAL grew to 2 TB
- INC-2023-528: replica volume burst credits exhausted, lag grew faster than apply could catch up for 3 hours
