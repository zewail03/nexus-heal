# Runbook: Service Mesh Circuit Breaker Open

## Alert Pattern
- Istio / Linkerd / Envoy reporting `upstream_rq_pending_overflow` or `cluster_circuit_breakers_open`
- Application logs: "circuit breaker open for upstream X"
- Sudden 503s for a specific downstream while others are fine
- Connection-pool saturation metrics (`outlier_detection.ejections_active` > 0)
- Half-open state oscillating: probe succeeds, more traffic flows, then re-trips

## Common Root Causes
1. **Downstream is genuinely degraded**: slow responses tripping the breaker correctly
2. **Connection-pool size too small**: legitimate traffic exceeds `max_connections`
3. **Outlier detection too aggressive**: `consecutive_5xx=2` opens for transient blips
4. **Cold-start surge after deploy**: new pods slow to warm up, all get ejected
5. **Bad health probe path**: probe endpoint always returns 503, ejecting healthy pods

## Diagnosis Steps
1. Check breaker status: `istioctl proxy-config cluster <pod> | grep <upstream>`
2. Look at the overflow counter: `envoy.cluster_manager.cluster.outbound|...||upstream.upstream_rq_pending_overflow`
3. Check ejection events: `kubectl logs <pod> -c istio-proxy | grep -i ejected`
4. Inspect the upstream's actual latency / error rate during the same window
5. Verify the health probe path returns the right status: `kubectl exec <upstream-pod> -- curl -I localhost:<port>/healthz`
6. Check `DestinationRule` for `connectionPool` and `outlierDetection` settings

## Remediation
1. **Tune connection pool up**: increase `connectionPool.tcp.maxConnections` and `http.http2MaxRequests`
2. **Loosen outlier detection**: `consecutive5xxErrors: 5` (was 2), `interval: 60s`, `baseEjectionTime: 30s`
3. **Add `warmupDurationSecs`**: smooth load shift to new pods after deploy
4. **Fix the health probe**: ensure it actually reflects readiness, not just process-up
5. **Restart upstream pods**: if they're in a stuck state, `kubectl rollout restart`
6. **Increase upstream replica count**: if breaker keeps opening because of capacity, scale up

## Rollback
- Revert outlier-detection loosening once the underlying flake is fixed (looser breaker = slower failure detection)
- Restore previous pool sizes if the new size caused memory pressure on the proxy sidecars

## Similar Past Incidents
- INC-2024-388: maxConnections=10 on a high-QPS service, breaker opened constantly under normal load
- INC-2024-400: deploy of payment-service had 30s warmup, outlier detection ejected all new pods on first request
- INC-2023-422: health probe queried the DB, DB was slow, every pod was marked unhealthy and ejected
