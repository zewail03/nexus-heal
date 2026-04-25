# Runbook: ImagePullBackOff

## Alert Pattern
- Pods stuck in `ImagePullBackOff` or `ErrImagePull` state
- `kubectl describe pod` shows `Failed to pull image "...": ...`
- Deployment rollout stalled
- New pods can't start, old pods still serving traffic (graceful degradation)
- Registry rate-limit errors in kubelet logs

## Common Root Causes
1. **Image tag doesn't exist**: deploy referenced a tag that wasn't actually pushed
2. **Registry credentials expired / missing**: `imagePullSecrets` not present in the namespace
3. **Registry rate-limit hit**: anonymous Docker Hub pulls limited to 100 per 6h per IP
4. **Network egress blocked**: NetworkPolicy or firewall blocks the registry FQDN
5. **Wrong registry domain**: typo (e.g., `gcr.io/` vs `gcr.io/project/`)
6. **Image too large**: kubelet timeout pulling a multi-GB image

## Diagnosis Steps
1. Get the failure reason: `kubectl describe pod <pod>` (look at the Events section)
2. Try pulling manually from a node: `crictl pull <image>` or `docker pull <image>`
3. Check imagePullSecrets: `kubectl get sa default -o yaml` (look at `imagePullSecrets`)
4. Verify the tag exists: `docker manifest inspect <image>:<tag>` from a workstation
5. Check rate-limit headers: `curl -I https://registry-1.docker.io/v2/<image>/manifests/<tag>`
6. Check egress: `kubectl exec -it <pod> -- nslookup <registry>`

## Remediation
1. **Fix the tag**: re-tag and re-push, or update the deployment to a tag that exists
2. **Recreate the pull secret**: `kubectl create secret docker-registry regcred --docker-server=... --docker-username=... --docker-password=...`
3. **Authenticate to bypass rate limits**: even with a free Docker Hub account, authenticated pulls have higher limits
4. **Switch to a mirrored registry**: pull through ECR / GCR / a self-hosted Harbor mirror
5. **Pre-pull on nodes**: use a DaemonSet to keep critical images warm
6. **Whitelist the registry FQDN** in NetworkPolicy / firewall

## Rollback
- Roll back the deployment to the last known-good image: `kubectl rollout undo deployment/<name>`
- Revert pull-secret changes if the new secret had unintended scope

## Similar Past Incidents
- INC-2024-275: deploy referenced `app:1.4.2-rc` but the CI only pushed `app:1.4.2`; new pods couldn't start
- INC-2024-289: cluster IP hit Docker Hub's anonymous limit during a rolling restart of all node pools
- INC-2023-301: NetworkPolicy was tightened to "deny all egress", pulls succeeded only because cache was warm
