# Runbook: Database Connection Failure

## Alert Pattern
- Connection pool exhausted — all connections in use
- "Too many connections" error from database server
- Application returning 503 or timeout errors on DB-dependent endpoints
- Connection refused or timeout on database port (3306/5432)

## Common Root Causes
1. **Connection pool exhaustion**: Application not releasing connections (leaked connections)
2. **Database overload**: Too many concurrent queries saturating the DB server
3. **Network issue**: Firewall rule change, security group misconfiguration, or DNS failure
4. **Database crash**: MySQL/PostgreSQL process crashed or was OOM-killed
5. **Max connections reached**: Database `max_connections` setting too low for traffic

## Diagnosis Steps
1. Check database status: `systemctl status postgresql` or `mysqladmin status`
2. Check active connections: `SELECT count(*) FROM pg_stat_activity;`
3. Check connection pool metrics in application dashboard
4. Test connectivity: `pg_isready -h <host> -p 5432` or `mysqladmin ping`
5. Review database logs: `/var/log/postgresql/` or `/var/log/mysql/`
6. Check network: `telnet <db-host> 5432`

## Remediation
1. **Immediate**: Restart application to release leaked connections
2. **Kill idle connections**: `SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE state = 'idle' AND query_start < now() - interval '10 minutes';`
3. **Increase pool size**: Update connection pool configuration (e.g., HikariCP, pgBouncer)
4. **Increase max_connections**: `ALTER SYSTEM SET max_connections = 200; SELECT pg_reload_conf();`
5. **Add connection pooler**: Deploy PgBouncer or ProxySQL as middleware

## Rollback
- Revert connection pool changes in application config
- Restart database if configuration changes cause issues: `systemctl restart postgresql`

## Similar Past Incidents
- INC-2024-019: Connection leak in ORM caused pool exhaustion during peak hours
- INC-2024-055: Database failover left application pointing to old primary
- INC-2023-098: Security group change blocked application from reaching RDS
