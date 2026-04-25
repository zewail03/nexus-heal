# Runbook: Storage IOPS Throttled

## Alert Pattern
- EBS / managed-disk burst credits exhausted
- Disk read/write latency p99 > 200 ms (normally < 5 ms)
- `iostat` showing `%util` pegged at 100% with low MB/s
- Database query latency degrading without an obvious query plan change
- CloudWatch / Cloud Monitoring `BurstBalance` metric dropping below 5%

## Common Root Causes
1. **Burstable volume out of credits**: gp2 volume sustained throughput beyond baseline
2. **Provisioned IOPS underspec'd**: gp3 / io2 IOPS too low for current workload
3. **Noisy-neighbor on shared infrastructure**: another tenant on the same physical disk
4. **Backup / snapshot job competing**: scheduled snapshot saturating IO bandwidth
5. **Filesystem fragmentation**: random IO pattern on a heavily-fragmented filesystem

## Diagnosis Steps
1. Check IO latency: `iostat -xm 1 5` (look at `await` and `%util`)
2. Check burst credits: AWS console → EC2 → Volume → Monitoring → `BurstBalance`
3. Identify hot processes: `iotop -oa`
4. Check backup schedule: was a snapshot running during the spike?
5. Check filesystem health: `xfs_info /data` (look at fragmentation hints)

## Remediation
1. **Immediate**: pause non-essential IO (stop the analytics replica, delay the snapshot)
2. **Upgrade to gp3 with provisioned IOPS**: AWS `modify-volume --iops 6000 --throughput 250`
3. **Add IOPS-provisioned tier**: io2 for databases that need consistent latency
4. **Move to local NVMe**: for ephemeral workloads, use instance-store
5. **Defragment**: `xfs_fsr` (XFS) — only works while IO is light, schedule overnight
6. **Stripe across volumes**: RAID 0 across two gp3 volumes doubles IOPS

## Rollback
- Snapshot the upgraded volume before resizing in case of corruption
- Restore the previous volume type if cost regression is unacceptable

## Similar Past Incidents
- INC-2024-128: prod Postgres on gp2, BurstBalance hit 0% during Black Friday, p99 query latency 4× normal
- INC-2024-141: nightly RDS snapshot starved a co-located reporting workload
- INC-2023-167: filesystem 78% fragmented after 18 months without defrag, random reads collapsed
