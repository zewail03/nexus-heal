# Runbook: Authentication Failure

## Alert Pattern
- Spike in HTTP 401/403 responses
- Login success rate dropping below threshold
- JWT token validation failures increasing
- OAuth/OIDC provider connectivity issues
- Brute force detection triggered (high volume of failed login attempts)

## Common Root Causes
1. **Expired secrets**: JWT signing key, API keys, or OAuth client secret rotated without updating services
2. **Identity provider outage**: Auth0, Okta, or internal IdP is down or degraded
3. **Clock skew**: Server time drift causing JWT "not yet valid" or "expired" errors
4. **Misconfigured RBAC**: Role-based access control rules changed, blocking legitimate users
5. **Brute force attack**: Automated credential stuffing or password spraying

## Diagnosis Steps
1. Check auth service logs: look for specific error messages (expired token, invalid signature)
2. Check identity provider status page (Auth0, Okta, etc.)
3. Verify server time: `date` and `ntpstat` — check for clock drift
4. Check JWT secrets: verify the signing key matches across services
5. Check rate limiting: review WAF or application rate limiter logs
6. Check recent RBAC changes: `kubectl get clusterrolebindings` or review IAM policies

## Remediation
1. **Expired secrets**: Rotate and deploy new secrets: `kubectl create secret generic auth-secret --from-literal=jwt-key=<new-key>`
2. **IdP outage**: Enable fallback authentication or cached token validation
3. **Clock skew**: Sync time: `sudo ntpdate pool.ntp.org` or restart `chronyd`
4. **RBAC fix**: Revert role changes or add missing permissions
5. **Brute force**: Block attacking IPs via WAF: add IP to blocklist
6. **Token refresh**: Force re-authentication for affected users

## Rollback
- Restore previous JWT signing key if new key causes issues
- Revert RBAC policy changes: `kubectl apply -f previous-rbac.yaml`
- Unblock IPs if legitimate users were caught in brute-force mitigation

## Similar Past Incidents
- INC-2024-014: JWT secret rotated in auth service but not in API gateway
- INC-2024-037: Auth0 outage caused 100% login failure for 23 minutes
- INC-2023-079: NTP service stopped, 5-minute clock drift invalidated all JWTs
