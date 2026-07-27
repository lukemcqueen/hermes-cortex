# ClickHouse Low-Memory Configuration

Reference config for single-server ClickHouse deployments (e.g. Langfuse self-hosted) where CPU/memory must not compete with other agent services.

## The problem

The ClickHouse Alpine 25.5 default config assumes a multi-core production server:
- `background_schedule_pool_size = 512` — 512 threads for periodic operations
- `background_pool_size = 16` — merge/mutation threads
- `max_thread_pool_size = 10000` — global query thread pool
- `<level>trace</level>` — logs every single background iteration
- System log tables collect metrics every 1 second

On a resource-constrained server, this causes sustained CPU spin (15-20% per core), 700+ threads, and massive log accumulation (1.5 GB log files, 550 MB system tables in 40 minutes).

## The fix: two config override files

Drop these into `<compose-dir>/clickhouse-config.d/` and mount as volumes in docker-compose.yml:

### 01-log-level.xml

```xml
<?xml version="1.0"?>
<clickhouse>
    <logger>
        <level>warning</level>
    </logger>
</clickhouse>
```

### 02-low-memory.xml

```xml
<?xml version="1.0"?>
<clickhouse>
    <!-- ── Thread pools ── -->
    <background_pool_size>4</background_pool_size>
    <background_schedule_pool_size>32</background_schedule_pool_size>
    <background_common_pool_size>2</background_common_pool_size>
    <background_buffer_flush_schedule_pool_size>2</background_buffer_flush_schedule_pool_size>
    <background_distributed_schedule_pool_size>4</background_distributed_schedule_pool_size>
    <background_fetches_pool_size>2</background_fetches_pool_size>
    <background_move_pool_size>2</background_move_pool_size>
    <background_message_broker_schedule_pool_size>2</background_message_broker_schedule_pool_size>

    <!-- Global thread pool -->
    <max_thread_pool_size>128</max_thread_pool_size>
    <thread_pool_queue_size>128</thread_pool_queue_size>

    <!-- Query concurrency -->
    <max_concurrent_queries>50</max_concurrent_queries>

    <!-- Merge tuning -->
    <merge_max_block_size>2048</merge_max_block_size>
    <merges_mutations_memory_usage_to_ram_ratio>0.3</merges_mutations_memory_usage_to_ram_ratio>

    <!-- System log tables: throttle collection intervals -->
    <metric_log>
        <database>system</database>
        <table>metric_log</table>
        <flush_interval_milliseconds>60000</flush_interval_milliseconds>
        <collect_interval_milliseconds>60000</collect_interval_milliseconds>
    </metric_log>
    <asynchronous_metric_log>
        <database>system</database>
        <table>asynchronous_metric_log</table>
        <flush_interval_milliseconds>60000</flush_interval_milliseconds>
        <collect_interval_milliseconds>60000</collect_interval_milliseconds>
    </asynchronous_metric_log>
    <query_log>
        <database>system</database>
        <table>query_log</table>
        <flush_interval_milliseconds>30000</flush_interval_milliseconds>
    </query_log>
    <trace_log>
        <database>system</database>
        <table>trace_log</table>
        <flush_interval_milliseconds>30000</flush_interval_milliseconds>
        <level>error</level>
    </trace_log>
    <part_log>
        <database>system</database>
        <table>part_log</table>
        <flush_interval_milliseconds>60000</flush_interval_milliseconds>
    </part_log>

    <!-- Disable: not used by Langfuse -->
    <processors_profile_log><database>system</database><table></table></processors_profile_log>
    <session_log><database>system</database><table></table></session_log>
    <error_log><database>system</database><table></table></error_log>
    <latency_log><database>system</database><table></table></latency_log>

    <!-- Per-query memory limits -->
    <profiles>
        <default>
            <max_memory_usage>500000000</max_memory_usage>
            <max_bytes_before_external_group_by>300000000</max_bytes_before_external_group_by>
            <max_threads>2</max_threads>
            <max_block_size>4096</max_block_size>
        </default>
    </profiles>
</clickhouse>
```

### Docker compose volume mount

Add to the clickhouse service in docker-compose.yml:

```yaml
services:
  clickhouse:
    volumes:
      - ./clickhouse-config.d/01-log-level.xml:/etc/clickhouse-server/config.d/01-log-level.xml:ro
      - ./clickhouse-config.d/02-low-memory.xml:/etc/clickhouse-server/config.d/02-low-memory.xml:ro
```

## Setting rationale

| Setting | Default | Low-memory | Why |
|---|---|---|---|
| `background_schedule_pool_size` | 512 | 32 | Main CPU spinner — 512 threads for periodic ops that rarely run |
| `background_pool_size` | 16 | 4 | Fewer concurrent merge threads needed at low insert rates |
| `max_thread_pool_size` | 10000 | 128 | Queries on a single-user deployment rarely need >128 threads |
| `merge_max_block_size` | 8192 | 2048 | Smaller merge blocks = less RAM per merge |
| `metric_log` interval | 1s | 60s | Don't need per-second metrics in a single-user setup |
| `max_memory_usage` | unlimited | 500MB | Prevents a single query from eating all container RAM |
| `max_threads` (per query) | auto | 2 | Enough for Langfuse UI queries; reduces contention |
| Processor profile log | on | disabled | Langfuse never reads it |
| Session log | on | disabled | Not used by Langfuse |
| Error log | on | disabled | Errors already go to text_log at error level |

## Initial cleanup

If trace logging was on before reducing, truncate accumulated system tables:

```sql
TRUNCATE TABLE system.text_log;
TRUNCATE TABLE system.trace_log;
TRUNCATE TABLE system.asynchronous_metric_log;
TRUNCATE TABLE system.metric_log;
TRUNCATE TABLE system.query_log;
TRUNCATE TABLE system.processors_profile_log;
TRUNCATE TABLE system.latency_log;
TRUNCATE TABLE system.error_log;
TRUNCATE TABLE system.part_log;
```

## Expected idle resource usage

After applying both config files and truncating accumulated data:
- **CPU**: <1% at idle (down from 15-20%)
- **Memory**: ~200-300 MB RSS (down from 800 MB+)
- **Threads**: ~50-80 (down from 700+)
- **Disk writes**: negligible (down from 1.5 GB/hour of logs)
