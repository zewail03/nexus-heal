# Runbook: Log Pipeline Lag

## Alert Pattern
- Logs in Kibana / Datadog / Loki are 10+ minutes behind real time
- Fluentd / Vector / Filebeat backlog growing: `output_buffer_queued_records` rising
- Disk usage on log-shipper hosts climbing (buffered events spilling to disk)
- Downstream alert rules (which depend on log signals) firing late or not firing at all
- Loss of correlation between logs and metrics during incident triage

## Common Root Causes
1. **Logging backend slow / down**: Elasticsearch cluster yellow / red, accepting writes slowly
2. **Log volume spike**: a service started DEBUG-logging in prod and 10×'d its log rate
3. **Log pipeline worker crash**: Fluentd OOMKilled, logs buffering on disk
4. **Network egress saturated**: shipper IO contending with application traffic
5. **Schema reject loop**: a malformed log line is rejected on every retry, blocking the queue
6. **ES rollover failed**: index hit `max_docs` and rollover policy didn't fire

## Diagnosis Steps
1. Check shipper health: `kubectl logs -l app=fluentd --tail=100`
2. Check buffer size: Fluentd `monitor_agent` endpoint: `curl -s localhost:24220/api/plugins.json`
3. Check ES cluster health: `curl -s localhost:9200/_cluster/health?pretty`
4. Spot-check a recent doc: `curl -s localhost:9200/logs-*/_search?q=*&size=1&sort=@timestamp:desc`
5. Find the noisy service: query for log volume by `service` over the last hour
6. Look for repeated rejection errors in shipper logs: same line, same error, retried many times

## Remediation
1. **Throttle the noisy service**: change its log level back from DEBUG to INFO
2. **Drop the bad records**: configure the shipper to dead-letter parse failures instead of retrying forever
3. **Scale the log backend**: add ES data nodes / increase Loki ingester replicas
4. **Increase shipper buffer**: spill more to disk so we don't drop events while rebuilding
5. **Force ES rollover**: `curl -XPOST localhost:9200/logs/_rollover` to start a fresh index
6. **Drop low-value fields**: stop indexing high-cardinality fields that bloat the index

## Rollback
- Re-enable the dropped log level once volume is sustainable
- Re-add high-cardinality fields if downstream queries actually used them

## Similar Past Incidents
- INC-2024-433: someone left `LOG_LEVEL=DEBUG` in payment-service after a debug session, log volume 12×
- INC-2024-446: ES rollover policy hit a quota, no new indices created, ingest stalled silently
- INC-2023-465: malformed JSON line from a misbehaving client poisoned the shipper queue for 4 hours
