# Runbook: Clock Drift

## Alert Pattern
- NTP sync alerts firing: `chrony sources` shows offset > 100 ms
- JWT validation failures with "token not yet valid" or "expired"
- TOTP / 2FA codes rejected even when entered correctly
- Distributed traces showing negative span durations
- Kafka consumer offsets jumping backwards
- TLS handshake failures: "certificate not yet valid"

## Common Root Causes
1. **chronyd / ntpd stopped**: NTP service died and was not restarted
2. **Firewall blocking NTP**: outbound UDP/123 blocked after a network policy change
3. **Virtualization clock skew**: VM host's clock drifted, guest inherited it
4. **Misconfigured timezone**: not drift, but commonly mistaken for it (logs in wrong TZ)
5. **NTP server unreachable**: pool.ntp.org rate-limiting one IP, no fallback configured

## Diagnosis Steps
1. Check sync status: `chronyc tracking` (look at `System time` and `Last offset`)
2. List sources: `chronyc sources -v`
3. Check service: `systemctl status chronyd`
4. Compare clocks across hosts: `for h in host1 host2 host3; do ssh $h date +%s.%N; done`
5. Check for NTP traffic: `tcpdump -ni any port 123` (should see traffic every ~32s)
6. Check JWT-affected services: look for `iat` / `exp` in logs vs current time

## Remediation
1. **Immediate**: force a one-time sync: `sudo chronyd -q 'server pool.ntp.org iburst'`
2. **Restart the NTP daemon**: `sudo systemctl restart chronyd`
3. **Add a backup NTP source**: edit `/etc/chrony.conf` to include `time.cloudflare.com` and `time.google.com`
4. **Open NTP egress in firewall**: allow UDP/123 outbound (NTP) and UDP/319/320 (PTP) if used
5. **Use the cloud provider's NTP**: AWS `169.254.169.123`, GCP `metadata.google.internal`
6. **Force JWT re-issuance**: invalidate cached tokens after the clock corrects

## Rollback
- Revert firewall changes if the previous block was intentional and a different fix is preferred
- Remove backup NTP entries if causing source-selection oscillation

## Similar Past Incidents
- INC-2024-014: chronyd OOMKilled on a memory-pressured node, 7-minute drift invalidated all JWTs
- INC-2024-079: new SCP blocked egress UDP/123, every host slowly diverged over 6 hours
- INC-2023-091: VMware host clock jumped 2 minutes during snapshot, killed all in-flight sessions
