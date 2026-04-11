# Runbook: Queue Overflow

## Alert Pattern
- Message queue depth exceeding threshold (e.g., > 10,000 messages)
- Consumer lag growing continuously
- Queue memory usage high (RabbitMQ / Redis approaching limits)
- Messages being dropped or dead-lettered
- Processing latency increasing (minutes to hours behind real-time)

## Common Root Causes
1. **Consumer crash**: Worker processes consuming from the queue have crashed or stopped
2. **Producer spike**: Sudden burst of messages overwhelming consumer capacity
3. **Slow consumer**: Consumer processing time increased (slow DB, external API)
4. **Poison message**: A single bad message causing consumer to crash on processing
5. **Misconfigured prefetch**: Consumer prefetch count too high, causing memory issues

## Diagnosis Steps
1. Check queue depth: `rabbitmqctl list_queues name messages` or Redis `LLEN <queue>`
2. Check consumers: `rabbitmqctl list_consumers` — are consumers connected?
3. Check consumer logs for errors or crashes
4. Check message rate: RabbitMQ management UI → message rates in/out
5. Check for poison messages: inspect dead-letter queue
6. Check consumer resource usage: CPU, memory, network

## Remediation
1. **Restart consumers**: `systemctl restart <worker-service>` or scale up workers
2. **Scale consumers**: Increase worker replicas: `kubectl scale deployment/<worker> --replicas=5`
3. **Purge stale messages**: (if safe) `rabbitmqctl purge_queue <queue-name>`
4. **Fix poison message**: Move bad messages to dead-letter queue, fix consumer error handling
5. **Increase consumer throughput**: Optimize processing code, batch operations
6. **Add backpressure**: Implement rate limiting on producers

## Rollback
- Scale consumers back down after backlog is cleared
- Re-enable purged queue bindings if messages were important
- Revert consumer code changes if they introduced the slowdown

## Similar Past Incidents
- INC-2024-018: Worker pod OOMKilled, queue grew to 500K messages in 30 minutes
- INC-2024-039: Poison JSON message crashed all consumers on deserialization
- INC-2023-082: Producer retry storm after upstream outage flooded queue with duplicates
