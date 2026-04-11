# Runbook: SSL Certificate Expired

## Alert Pattern
- SSL/TLS certificate expiration warning (< 30 days or already expired)
- Users seeing "Your connection is not private" browser warnings
- HTTPS handshake failures in load balancer logs
- API clients receiving SSL verification errors
- Certificate chain incomplete or invalid

## Common Root Causes
1. **Missed renewal**: Auto-renewal failed or was never configured
2. **Cert manager failure**: cert-manager or Let's Encrypt integration broken
3. **Wrong certificate deployed**: Renewed cert not applied to load balancer / ingress
4. **Intermediate CA expired**: Certificate chain uses an expired intermediate authority
5. **Manual process**: Certificate was provisioned manually and renewal was forgotten

## Diagnosis Steps
1. Check certificate expiry: `echo | openssl s_client -connect <host>:443 2>/dev/null | openssl x509 -noout -dates`
2. Check certificate chain: `echo | openssl s_client -connect <host>:443 -showcerts`
3. Check cert-manager (Kubernetes): `kubectl get certificates -A`
4. Check Let's Encrypt logs: `certbot certificates`
5. Verify certificate matches domain: `openssl x509 -noout -subject -in cert.pem`

## Remediation
1. **Immediate (Let's Encrypt)**: `certbot renew --force-renewal`
2. **Immediate (manual)**: Upload new certificate to load balancer / CDN
3. **Kubernetes**: `kubectl delete secret <tls-secret> && kubectl apply -f certificate.yaml`
4. **Fix auto-renewal**: Ensure cron job or cert-manager is configured:
   - `crontab -e` → `0 0 1 * * certbot renew --quiet`
5. **Intermediate fix**: Download and install correct CA chain bundle

## Rollback
- If wrong cert was deployed: restore previous certificate from backup
- Re-apply old TLS secret in Kubernetes: `kubectl apply -f old-tls-secret.yaml`

## Similar Past Incidents
- INC-2024-015: Let's Encrypt rate limit hit, renewal failed silently for 2 weeks
- INC-2024-038: Wildcard cert renewed but not deployed to 3 of 5 load balancers
- INC-2023-101: Intermediate CA expired, breaking cert chain on older Android devices
