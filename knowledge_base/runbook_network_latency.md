# Runbook: Network Latency

## Alert Pattern
- Response times exceed SLA thresholds (e.g., p99 > 2s)
- Increased packet loss between services
- TCP retransmissions rising
- DNS resolution slow or intermittent
- Cross-region or cross-AZ latency spikes

## Common Root Causes
1. **Network congestion**: Bandwidth saturation on links between services
2. **DNS issues**: Slow or failing DNS resolution causing connection delays
3. **Misconfigured routing**: Suboptimal routing tables sending traffic through slow paths
4. **Noisy neighbor**: Shared infrastructure resource contention (cloud environments)
5. **MTU mismatch**: Packet fragmentation causing retransmissions

## Diagnosis Steps
1. Measure latency: `ping <target>` and `mtr <target>` for hop-by-hop analysis
2. Check DNS: `dig <domain>` — look at query time
3. Check TCP metrics: `ss -ti` for retransmissions
4. Check bandwidth: `iftop` or `nload` for interface throughput
5. Check for packet loss: `ping -c 100 <target>` — look at loss percentage
6. Check routes: `traceroute <target>`

## Remediation
1. **DNS caching**: Enable local DNS cache (e.g., `systemd-resolved`, `dnsmasq`)
2. **Optimize routing**: Use service mesh or configure direct peering
3. **Increase bandwidth**: Upgrade network tier or enable enhanced networking
4. **CDN / caching**: Move static content to CDN to reduce origin load
5. **Connection pooling**: Reuse TCP connections to avoid handshake latency

## Rollback
- Revert DNS configuration: `systemctl restart systemd-resolved`
- Revert routing changes: `ip route del` to remove added routes

## Similar Past Incidents
- INC-2024-022: DNS TTL set to 0 caused every request to resolve DNS fresh
- INC-2024-041: Cross-AZ traffic spike after service was redeployed to single AZ
- INC-2023-089: MTU mismatch between VPN tunnel and VPC caused 30% packet loss
