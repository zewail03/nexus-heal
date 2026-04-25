# Runbook: WebSocket Disconnect Storm

## Alert Pattern
- Spike in `WebSocket close code 1006` (abnormal closure) on the LB / app
- Active connection count drops by > 50 % within a minute
- All clients reconnect at once, creating a thundering herd
- CPU on the WebSocket gateway saturated by reconnect handshake load
- Redis/pubsub channel showing duplicate message delivery during the herd

## Common Root Causes
1. **LB idle-timeout shorter than the keepalive interval**: connections silently dropped after N seconds
2. **WebSocket gateway pod restarted**: rolling deploy killed N pods, all their clients reconnected
3. **Network blip on the client side**: a CDN or ISP route flapped, all affected clients reconnected
4. **Memory pressure**: gateway hit a memory limit and force-closed connections
5. **TLS session ticket rotation**: clients couldn't resume, did full handshakes simultaneously

## Diagnosis Steps
1. Plot WebSocket connection count over the last hour
2. Check LB access logs for the timestamp of the drop, look at status codes
3. Cross-reference with deployment timeline: any rollout in the window?
4. Check pod restarts: `kubectl get pods -l app=ws-gateway --sort-by=.status.containerStatuses[0].restartCount`
5. Check memory usage at the time: `kubectl top pod` or Prometheus `container_memory_usage_bytes`
6. Look at LB idle-timeout vs application keepalive interval — must be `app < lb`

## Remediation
1. **Increase LB idle timeout**: must be 1.5–2× the application keepalive interval
2. **Stagger reconnect on the client side**: backoff with jitter (e.g., random 0–5 s)
3. **Pre-warm the pool** before a deploy: gradually shift connections to the new pods
4. **Add sticky sessions** so a reconnect lands on the same pod where state is cached
5. **Scale gateway preemptively** before rolling deploys: HPA + 2× current replicas for the deploy window
6. **Use connection draining** on pod shutdown: send a graceful close with `1001 Going Away` and a `Retry-After`-style hint

## Rollback
- Revert sticky sessions if they cause uneven load distribution
- Remove pre-warming once the deploy completes

## Similar Past Incidents
- INC-2024-205: ALB idle timeout = 60 s, app keepalive = 65 s; every connection dropped in < 2 minutes
- INC-2024-220: rolling deploy killed all 8 ws-gateway pods in 30 s; 200 k clients reconnected in a thundering herd
- INC-2023-238: TLS session-ticket key rotation caused full handshakes, gateway CPU hit 100 % for 4 minutes
