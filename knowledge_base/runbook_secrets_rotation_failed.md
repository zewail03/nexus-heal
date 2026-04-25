# Runbook: Secrets Rotation Failed

## Alert Pattern
- Vault / AWS Secrets Manager rotation Lambda erroring
- Service auth failures starting exactly at the scheduled rotation window
- Two services for the same DB use different credentials (one rotated, one didn't)
- `aws secretsmanager describe-secret` shows `RotationEnabled: true` but `LastRotatedDate` is stale
- Pods restarting in a loop after a credential rollover

## Common Root Causes
1. **Rotation Lambda IAM missing**: lambda lacks `secretsmanager:UpdateSecretVersionStage`
2. **DB / IAM permission denied**: rotator can't create the new credential
3. **Application doesn't refresh**: service caches the old secret in memory, never re-reads
4. **Two-stage rotation interrupted**: AWSPENDING was set but never promoted to AWSCURRENT
5. **Network egress blocked**: the rotator can't reach the secret store from its subnet

## Diagnosis Steps
1. Check the rotator's last invocation: `aws lambda get-function --function-name <rotator>` then check CloudWatch logs
2. Inspect the secret stages: `aws secretsmanager describe-secret --secret-id <id>` (look for AWSCURRENT vs AWSPENDING)
3. Get the current value (audit-logged): `aws secretsmanager get-secret-value --secret-id <id> --version-stage AWSCURRENT`
4. Test the new credential against the target service: `psql -U <new_user> -h <db_host>`
5. Check application reload: `kubectl rollout status deployment/<svc>` to see if pods picked up the new secret

## Remediation
1. **Force completion of the stuck rotation**: `aws secretsmanager update-secret-version-stage --secret-id <id> --version-stage AWSCURRENT --move-to-version-id <pending_version>`
2. **Restart consumers** so they re-read the secret: `kubectl rollout restart deployment/<svc>`
3. **Fix the rotator IAM**: attach `SecretsManagerReadWrite` (or scoped equivalent) to the Lambda's role
4. **Revert to previous version** if the new credential is broken: `--move-to-version-id <previous>`
5. **Add a sidecar that watches the secret**: e.g., `external-secrets-operator` to push updates into pods automatically

## Rollback
- Move AWSCURRENT back to the previous version with `update-secret-version-stage`
- Re-trigger rotation only after the underlying error is fixed

## Similar Past Incidents
- INC-2024-184: rotator Lambda's VPC subnet lost its NAT gateway, rotator timed out for 6 days
- INC-2024-199: service cached DB password at startup, never re-read; new password was set but unused
- INC-2023-211: AWSPENDING was created but the DB grant statement failed, leaving rotation half-applied
