# Runbook: Disk Full

## Alert Pattern
- Disk usage exceeds 90% on a mounted volume
- "No space left on device" errors in application logs
- Write operations failing across services
- Inode exhaustion (disk shows space but cannot create files)

## Common Root Causes
1. **Log file growth**: Application or system logs not rotated, growing unbounded
2. **Temporary files**: `/tmp` filled with stale temp files or build artifacts
3. **Database growth**: Data directory consuming disk without archival policy
4. **Docker images**: Unused Docker images and containers filling `/var/lib/docker`
5. **Core dumps**: Repeated crashes generating large core dump files

## Diagnosis Steps
1. Check disk usage: `df -h` for space, `df -i` for inodes
2. Find large files: `du -sh /* | sort -rh | head -20`
3. Find large directories: `du -sh /var/log/* | sort -rh | head -10`
4. Check for deleted-but-open files: `lsof +L1`
5. Check Docker: `docker system df`

## Remediation
1. **Immediate**: Clear old logs: `find /var/log -name "*.gz" -mtime +7 -delete`
2. **Truncate active log**: `truncate -s 0 /var/log/application/app.log` (if safe)
3. **Clean Docker**: `docker system prune -a --volumes`
4. **Clean temp files**: `find /tmp -type f -mtime +3 -delete`
5. **Set up log rotation**: Configure `logrotate` with size-based rotation
6. **Expand volume**: Resize EBS/disk volume if needed

## Rollback
- If files were incorrectly deleted: restore from backup
- If volume was resized: cannot easily shrink, but it's a safe operation

## Similar Past Incidents
- INC-2024-008: PostgreSQL WAL files filled /data volume to 100%
- INC-2024-033: Debug logging left enabled in production filled disk in 4 hours
- INC-2023-076: Docker build cache grew to 80GB on CI runner
