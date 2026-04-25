# Runbook: Certificate Chain Invalid

## Alert Pattern
- TLS handshake failures with "unable to get local issuer certificate"
- One client (mobile, older Java, embedded device) failing while browsers succeed
- New monitoring probe failing on a domain that previously worked
- `openssl s_client` showing "verify error: num=20" or "num=21"
- Cert chain length only 1 (leaf) instead of 2-3 (leaf + intermediates)

## Common Root Causes
1. **Missing intermediate cert**: server only serving the leaf, not the chain
2. **Wrong order in chain**: leaf must be first, then intermediates in upward order
3. **Expired intermediate CA**: a root or intermediate in the chain has expired
4. **Cross-signed cert mismatch**: removed the cross-sign needed by older trust stores
5. **Wrong chain deployed**: cert deployed against a different CA's chain

## Diagnosis Steps
1. Inspect what the server presents: `openssl s_client -showcerts -connect host:443 < /dev/null`
2. Verify the chain: `openssl verify -CAfile /etc/ssl/certs/ca-certificates.crt fullchain.pem`
3. Check chain order: leaf cert must come first; the file should look like `leaf -> intermediate1 -> intermediate2`
4. Check intermediate expiry: `openssl x509 -in intermediate.pem -noout -dates`
5. Test with a strict client: `curl -v https://host` (look at "TLS certificate verify ok" or the failure)
6. Test from the affected client class: e.g., older Android emulator

## Remediation
1. **Fix the chain file**: concatenate `cat leaf.pem intermediates.pem > fullchain.pem` and re-deploy
2. **Update the issuer's intermediate**: download the latest intermediate from the CA
3. **Add cross-sign**: include the older cross-signed intermediate alongside the new one for compat
4. **K8s ingress**: re-create the TLS secret: `kubectl create secret tls <name> --cert=fullchain.pem --key=key.pem --dry-run=client -o yaml | kubectl apply -f -`
5. **Reload the LB / proxy**: nginx `nginx -s reload`, AWS ELB needs cert reattachment

## Rollback
- Restore the previous TLS secret if the new cert breaks more clients than it fixes
- Re-add the deprecated cross-signed intermediate if older clients regress

## Similar Past Incidents
- INC-2024-155: removed an "expired" intermediate that older Android still needed to validate the chain
- INC-2024-162: cert renewed correctly but only the leaf was deployed; iOS Safari worked, Java clients didn't
- INC-2023-178: Let's Encrypt R3 intermediate rotated and one of our 5 LBs missed the update
