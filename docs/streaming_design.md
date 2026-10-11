# Streaming Design (Phase 4)

This document describes the streaming architecture implemented in Phase 4.

## Topics and Partitions
- `orbitwatch.gp_updates`: 3 partitions (high volume). Keyed by `NORAD_CAT_ID` to ensure updates for the same satellite are processed in order.
- `orbitwatch.k_index_updates`: 1 partition (low volume).
- `orbitwatch.solar_updates`: 1 partition (low volume).
- `orbitwatch.dlq`: 1 partition (dead-letter queue).

## At-Least-Once Delivery & Idempotency
We use an at-least-once delivery semantic. The consumer processes messages and inserts them into PostgreSQL `staging` tables.
To make it idempotent, we use a unique constraint on the staging tables: `UNIQUE (natural_key, md5(payload::text))`.
We perform an `INSERT ... ON CONFLICT DO NOTHING`. Offsets are committed to Kafka *only* after a successful database commit. If there are duplicates (e.g. consumer crashed before offset commit), they are safely ignored.

## Dead Letter Queue (DLQ)
Messages with invalid envelopes (e.g., missing required fields, invalid JSON) are pushed to the `orbitwatch.dlq` topic and inserted into the `quality.dead_letter` table. This ensures the consumer does not crash, and bad messages can be investigated and reprocessed later.

## Excluded Sources
The `SATCAT` source is not streamed because it is mostly static reference data. It will be loaded in bulk in the warehouse phase.
