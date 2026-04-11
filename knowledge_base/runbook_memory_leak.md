# Runbook: Memory Leak

## Alert Pattern
- Memory usage steadily increasing over time (sawtooth or linear growth)
- OOM (Out of Memory) killer invoked — processes killed by kernel
- Application becoming unresponsive before being OOM-killed
- Swap usage increasing alongside RAM
- Container hitting memory limits and being restarted (OOMKilled status)

## Common Root Causes
1. **Application memory leak**: Objects allocated but never freed (missing cleanup, growing caches)
2. **Connection leak**: Database or HTTP connections opened but never closed
3. **Event listener leak**: Event handlers registered but never removed
4. **Buffer accumulation**: Buffers or queues growing without bounds
5. **JVM heap misconfiguration**: Heap size set too low, causing frequent GC but eventual OOM

## Diagnosis Steps
1. Check memory usage: `free -h` and `vmstat 1 5`
2. Find memory-hungry processes: `ps aux --sort=-%mem | head -20`
3. Check OOM killer: `dmesg | grep -i "oom\|killed"`
4. Check container memory: `kubectl top pods` or `docker stats`
5. Application profiling: Use language-specific tools (e.g., `jmap` for Java, `tracemalloc` for Python)
6. Check swap: `swapon --show` and `free -h`

## Remediation
1. **Immediate**: Restart the leaking service: `systemctl restart <service>`
2. **Kubernetes**: Delete and let the pod restart: `kubectl delete pod <pod-name>`
3. **Set memory limits**: Configure container memory limits to prevent host-level impact
4. **Fix the leak**: Profile the application, find the allocation site, add proper cleanup
5. **Add monitoring**: Set up alerts for memory growth rate, not just absolute thresholds

## Rollback
- If caused by recent deployment: `kubectl rollout undo deployment/<name>`
- If service restart causes issues: check dependent services and restart them too

## Similar Past Incidents
- INC-2024-027: Python service leaking database cursors — 2GB growth per hour
- INC-2024-044: Node.js event listener leak in WebSocket handler
- INC-2023-091: Java heap dump showed 500MB of cached but expired session objects
