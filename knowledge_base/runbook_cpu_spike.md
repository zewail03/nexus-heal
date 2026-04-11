# Runbook: CPU Spike

## Alert Pattern
- CPU usage exceeds 90% for more than 5 minutes
- Load average significantly above number of CPU cores
- Process-level CPU consumption abnormally high
- OOM killer may be active alongside CPU saturation

## Common Root Causes
1. **Runaway process**: A single process consuming excessive CPU (infinite loop, inefficient algorithm)
2. **Traffic spike**: Sudden increase in request volume overwhelming the service
3. **Resource contention**: Too many CPU-bound tasks scheduled on the same host
4. **Cryptomining malware**: Unauthorized process consuming CPU resources
5. **Garbage collection storms**: JVM or runtime GC consuming excessive CPU

## Diagnosis Steps
1. Run `top -o %CPU` or `htop` to identify the top CPU-consuming process
2. Check `uptime` for load averages — compare to CPU count (`nproc`)
3. Review application logs for error loops or retry storms
4. Check `dmesg` for OOM killer activity
5. Inspect cron jobs: `crontab -l` and `/etc/cron.d/`

## Remediation
1. **Immediate**: Identify and kill the runaway process: `kill -9 <PID>`
2. **Scale horizontally**: Add more instances behind the load balancer
3. **Rate limit**: Apply rate limiting if caused by traffic spike
4. **Tune application**: Profile the code, fix hot loops, optimize algorithms
5. **Increase resources**: Vertically scale the instance if under-provisioned

## Rollback
- If a deployment caused the spike: `kubectl rollout undo deployment/<name>`
- If process was killed: restart the service: `systemctl restart <service>`

## Similar Past Incidents
- INC-2024-031: API gateway CPU spike due to regex backtracking in URL parser
- INC-2024-047: Batch job scheduled during peak hours caused 98% CPU
- INC-2023-112: Memory leak caused excessive GC, manifesting as CPU spike
