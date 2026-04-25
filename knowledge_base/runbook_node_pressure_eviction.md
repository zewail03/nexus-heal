# Runbook: Node Pressure Pod Eviction

## Alert Pattern
- Pods being evicted with reason `Evicted` and message `The node was low on resource: memory`
- Multiple pods on the same node restarting around the same time
- Node condition `MemoryPressure` or `DiskPressure` = `True`
- kubelet logs: `attempting to reclaim ephemeral-storage`
- Critical workloads losing replicas without an explicit deploy

## Common Root Causes
1. **Workload bursting past requests**: pods configured with low requests but high real usage
2. **Memory leak in one pod**: a single noisy pod consumes node memory until kubelet evicts
3. **Disk pressure from logs**: `/var/log` filling up with stdout from a noisy container
4. **Image GC threshold reached**: kubelet evicts to make room for new images
5. **Wrong eviction-soft / eviction-hard config**: thresholds too aggressive, evicting healthy pods

## Diagnosis Steps
1. List recent evictions: `kubectl get events --sort-by=.lastTimestamp | grep -i evicted`
2. Check node conditions: `kubectl describe node <name>` (look for MemoryPressure / DiskPressure)
3. Find the offending pod: `kubectl top pod -A --sort-by=memory | head -20`
4. Check kubelet logs for the eviction reason: `journalctl -u kubelet -n 200`
5. Check ephemeral-storage usage: `kubectl describe pod | grep -A2 ephemeral-storage`
6. Confirm requests vs limits configuration: `kubectl get pod -o jsonpath='{.spec.containers[].resources}'`

## Remediation
1. **Set proper requests**: scale `requests.memory` to match the p95 of actual usage
2. **Add memory limits**: prevents one bad pod from taking down siblings
3. **Cordon the affected node**: `kubectl cordon <node>` and let pods reschedule
4. **Increase node pool**: scale up the cluster's auto-scaler floor
5. **Move noisy workloads to dedicated node pool**: taints + tolerations
6. **Rotate logs aggressively**: drop log retention to 7 days, switch to remote log shipping

## Rollback
- Drain and recreate the cordoned node only after capacity is restored elsewhere
- Revert eviction thresholds if the new value caused different pods to be evicted

## Similar Past Incidents
- INC-2024-310: image-cache GC misfired, evicted DaemonSet pods on every node simultaneously
- INC-2024-322: payment-processor leaked memory, kubelet evicted all 5 sibling pods on the same node
- INC-2023-348: ephemeral storage filled with debug logs left enabled in prod, every pod on the node OOMKilled
