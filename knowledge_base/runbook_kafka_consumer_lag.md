# Runbook: Kafka Consumer Lag

## Alert Pattern
- Consumer-group lag exceeds threshold (e.g., > 100 k records on a topic)
- Lag growing monotonically over the last 15 minutes
- End-to-end latency from producer to downstream consumer > SLA
- One partition's lag dominates the total (skewed key distribution)
- Consumer pods CPU-saturated but not making progress

## Common Root Causes
1. **Consumer too slow**: per-record processing latency increased (slow DB write, external call)
2. **Partition skew**: a single partition has 90 % of traffic because of a hot key
3. **Worker scale-down**: HPA reduced replicas while traffic stayed flat
4. **Rebalance loop**: consumer-group keeps rebalancing, never gets work done
5. **Compacted topic surprise**: tombstones causing replay of historical data
6. **Network partition**: consumer can't reach the broker, but heartbeat succeeds

## Diagnosis Steps
1. Check lag per partition: `kafka-consumer-groups --bootstrap-server <b> --describe --group <g>`
2. Identify the hot partition (largest LAG column)
3. Count consumer members in the group (same command, MEMBERS column)
4. Check rebalance frequency: `kafka.consumer:type=consumer-coordinator-metrics` JMX
5. Inspect consumer logs for `RebalanceInProgress` exceptions
6. Check downstream: is the slow link a DB write, a downstream API, or CPU?

## Remediation
1. **Scale consumers**: `kubectl scale deployment/<consumer> --replicas=<2x>` (limited by partition count)
2. **Increase partition count**: `kafka-topics --alter --partitions <new>` (requires consumer-group reset to rebalance)
3. **Fix the hot key**: bucket the key (e.g., append `key + "_" + hash(timestamp) % 16`) on the producer side
4. **Tune fetch size**: increase `max.poll.records` and `fetch.max.bytes` to amortize round-trips
5. **Process in parallel within a partition**: use a worker pool inside the consumer for the slow downstream call
6. **Reset offset to skip backlog** (data-loss risk): `kafka-consumer-groups --reset-offsets --to-latest --execute`

## Rollback
- Scale consumers back down once lag is drained
- Revert partition increase only by recreating the topic (rare; usually keep)

## Similar Past Incidents
- INC-2024-101: payment events all went to partition 0 because of a `tenant_id=null` bug, lag hit 2 M
- INC-2024-117: consumer rebalance loop after a deployment, group made no progress for 14 minutes
- INC-2023-152: enrichment service called a slow ML model in the consumer hot path; lag grew 30 k/min
