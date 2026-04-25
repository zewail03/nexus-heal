# Runbook: DNS Resolution Failure

## Alert Pattern
- Spike in `NXDOMAIN` or `SERVFAIL` responses in resolver logs
- Connection attempts failing with "name or service not known"
- Coredns / kube-dns pods returning 5xx
- Service-to-service calls failing intermittently with sub-second timeouts
- DNS lookup latency p99 > 500 ms (normally < 20 ms)

## Common Root Causes
1. **Upstream resolver outage**: Public resolver (8.8.8.8, 1.1.1.1) or VPC-attached resolver degraded
2. **Coredns / kube-dns pod crash**: in-cluster DNS replicas unhealthy, all queries failing
3. **DNS cache poisoning / stale records**: TTL-expired records returning old IPs
4. **Misconfigured search domains**: ndots/search list causing every query to fan out N times
5. **Rate limiting at the resolver**: high QPS from one pod triggers per-IP throttle

## Diagnosis Steps
1. Check resolver health: `kubectl get pods -n kube-system -l k8s-app=kube-dns`
2. Check coredns logs: `kubectl logs -n kube-system -l k8s-app=kube-dns --tail=100`
3. Test from inside a pod: `kubectl exec <pod> -- dig +short api.example.com`
4. Compare TTLs and answer time: `dig api.example.com` (look at `Query time`)
5. Check `/etc/resolv.conf` inside the affected pod for ndots / search-list bloat
6. Inspect DNS metrics dashboard for per-resolver QPS

## Remediation
1. **Restart unhealthy DNS pods**: `kubectl rollout restart deployment/coredns -n kube-system`
2. **Bypass cluster DNS temporarily**: pin pod's `dnsConfig.nameservers` to `1.1.1.1`
3. **Reduce ndots**: set `dnsConfig.options[].name=ndots, value=1` in pod spec
4. **Scale resolvers**: `kubectl scale deployment/coredns --replicas=4 -n kube-system`
5. **Switch DNS provider**: update VPC DHCP option set to a different resolver

## Rollback
- Revert dnsConfig changes once cluster DNS is healthy
- Remove temporary ndots override after measuring baseline

## Similar Past Incidents
- INC-2024-051: coredns OOMKilled at 2 replicas during traffic burst, 4× DNS error rate for 8 minutes
- INC-2024-063: ndots=5 caused every external lookup to make 5 internal requests, exhausting the resolver
- INC-2023-118: AWS Route 53 Resolver throttled a single high-QPS pod, looked like a global DNS outage
