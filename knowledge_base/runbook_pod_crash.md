# Runbook: Pod Crash (CrashLoopBackOff)

## Alert Pattern
- Kubernetes pod in CrashLoopBackOff state
- Pod restarting repeatedly (restart count climbing)
- Container exit code non-zero (137 = OOMKilled, 1 = application error)
- Service availability degraded due to unhealthy pods
- ReadinessProbe or LivenessProbe failures

## Common Root Causes
1. **Application error**: Unhandled exception during startup (missing config, bad migration)
2. **OOMKilled (exit 137)**: Container exceeding memory limits
3. **Missing dependencies**: Required service, secret, or configmap not available
4. **Bad configuration**: Environment variable misconfigured or missing
5. **Health check failure**: Liveness probe too aggressive, killing healthy but slow pods

## Diagnosis Steps
1. Check pod status: `kubectl get pods -n <namespace>`
2. Check pod events: `kubectl describe pod <pod-name> -n <namespace>`
3. Check logs: `kubectl logs <pod-name> -n <namespace> --previous` (previous crash logs)
4. Check exit code: `kubectl get pod <pod-name> -o jsonpath='{.status.containerStatuses[0].lastState.terminated.exitCode}'`
5. Check resource usage: `kubectl top pod <pod-name>`
6. Check configmaps/secrets: `kubectl get configmap,secret -n <namespace>`

## Remediation
1. **Application error**: Fix the code and redeploy
2. **OOMKilled**: Increase memory limits in deployment spec:
   ```yaml
   resources:
     limits:
       memory: "512Mi"  # Increase this
   ```
3. **Missing config**: Create missing configmap/secret: `kubectl create configmap <name> --from-literal=key=value`
4. **Liveness probe**: Increase `initialDelaySeconds` and `timeoutSeconds`
5. **Rollback**: `kubectl rollout undo deployment/<name> -n <namespace>`

## Rollback
- Roll back to previous version: `kubectl rollout undo deployment/<name>`
- Check rollout history: `kubectl rollout history deployment/<name>`

## Similar Past Incidents
- INC-2024-025: New deployment missing DATABASE_URL secret, crashed on startup
- INC-2024-042: Memory limit too low for Java service (256Mi vs 512Mi needed)
- INC-2023-095: Liveness probe hitting /health before app finished startup (10s delay needed)
