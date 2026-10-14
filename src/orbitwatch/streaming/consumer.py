#!/usr/bin/env python3
"""
ORBITWATCH Phase 4 - Streaming Consumer
Consumes messages from Redpanda topics and inserts them into PostgreSQL staging tables.

Phase 4 fix:
- data_lineage now writes one row per topic->table per run (consumed >= 0, not just inserted > 0)
- pipeline_runs status is 'success' or 'failed' (not 'completed'), set in a finally block
- SIGINT/SIGTERM marks the run as 'success' (clean shutdown) rather than leaving it 'running'
- topic name for solar lineage corrected to 'orbitwatch.solar_updates'
"""
import argparse
import datetime
import json
import signal
import sys
import time
import uuid
from pathlib import Path
from typing import List, Dict, Any

# Setup paths for local execution
sys.path.insert(0, str((Path(__file__).parent.parent.parent.parent).resolve()))
sys.path.insert(0, str((Path(__file__).parent.parent.parent).resolve()))

from confluent_kafka import Consumer, Producer, KafkaException
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from orbitwatch.common.db import get_postgres_engine
from config.settings import get_settings

# Map: internal source key -> (kafka topic, staging table)
SOURCE_MAP = {
    "gp":            ("orbitwatch.gp_updates",          "staging.gp_raw"),
    "k_index":       ("orbitwatch.k_index_updates",     "staging.k_index_raw"),
    "solar_indices": ("orbitwatch.solar_updates",       "staging.solar_indices_raw"),
}


class StreamConsumer:
    """Consumer for streaming data from Redpanda to Postgres."""

    def __init__(self, batch_size: int, max_messages: int, idle_seconds: int, once: bool):
        self.settings = get_settings()
        self.batch_size = batch_size
        self.max_messages = max_messages
        self.idle_seconds = idle_seconds
        self.once = once
        self.run_id = str(uuid.uuid4())
        self.started_at = datetime.datetime.now(datetime.timezone.utc)

        self.engine = get_postgres_engine("etl")

        # Kafka consumer configuration
        self.consumer = Consumer({
            "bootstrap.servers": self.settings.kafka_bootstrap_servers,
            "group.id": "orbitwatch-staging-consumer",
            "auto.offset.reset": "earliest",
            "enable.auto.commit": False
        })

        # DLQ producer
        self.dlq_producer = Producer({
            "bootstrap.servers": self.settings.kafka_bootstrap_servers,
            "acks": "all"
        })

        self.topics = [info[0] for info in SOURCE_MAP.values()]

        # Per-source counters
        self.stats: Dict[str, Dict[str, int]] = {
            src: {"consumed": 0, "inserted": 0, "duplicates": 0, "dlq": 0}
            for src in SOURCE_MAP
        }

        self.is_running = True
        self._final_status = "success"  # overridden to 'failed' on unrecoverable error

        # Graceful shutdown on SIGINT / SIGTERM
        signal.signal(signal.SIGINT, self._handle_signal)
        signal.signal(signal.SIGTERM, self._handle_signal)

    # ─── Signal handling ──────────────────────────────────────────────────────

    def _handle_signal(self, signum, frame):
        """Signal handler: finish current batch then exit cleanly."""
        print(f"\nReceived signal {signum}, shutting down gracefully...")
        self.is_running = False

    # ─── Message validation ───────────────────────────────────────────────────

    def validate_message(self, val_str: str) -> tuple[bool, str, Dict[str, Any]]:
        """Validate JSON envelope. Returns (is_valid, reason, parsed_dict)."""
        try:
            msg = json.loads(val_str)
        except json.JSONDecodeError:
            return False, "Invalid JSON", {}

        required_keys = {"event_id", "natural_key", "payload", "source"}
        missing = required_keys - msg.keys()
        if missing:
            return False, f"Missing required fields: {missing}", msg

        return True, "", msg

    # ─── Batch processing ─────────────────────────────────────────────────────

    def process_batch(self, batch: List[Any]):
        """Validate, route, and persist a batch of Kafka messages."""
        if not batch:
            return

        # Reverse-map topic -> source key
        topic_to_source = {info[0]: src for src, info in SOURCE_MAP.items()}

        valid_by_source: Dict[str, List[Dict]] = {src: [] for src in SOURCE_MAP}
        bad_messages: List[tuple] = []

        for msg in batch:
            topic = msg.topic()
            source = topic_to_source.get(topic)

            if source is None:
                bad_messages.append(("unknown", msg.value().decode("utf-8", errors="replace"), "Unknown topic"))
                continue

            self.stats[source]["consumed"] += 1

            val_str = msg.value().decode("utf-8") if msg.value() else "{}"
            is_valid, reason, parsed = self.validate_message(val_str)

            if is_valid:
                valid_by_source[source].append({
                    "event_id":       parsed["event_id"],
                    "natural_key":    parsed["natural_key"],
                    "payload":        json.dumps(parsed["payload"]),
                    "mongo_batch_id": parsed.get("mongo_batch_id"),
                    "kafka_topic":    topic,
                    "kafka_partition": msg.partition(),
                    "kafka_offset":   msg.offset(),
                    "produced_at":    parsed.get("produced_at"),
                })
            else:
                self.stats[source]["dlq"] += 1
                bad_messages.append((source, val_str, reason))

        # Send bad messages to DLQ before DB writes
        if bad_messages:
            self._handle_bad_messages(bad_messages)

        # Insert valid messages per source
        for source, rows in valid_by_source.items():
            if not rows:
                continue
            success = self._insert_with_retry(source, rows)
            if not success:
                print(f"[ERROR] Failed to insert batch for {source} after retries. Exiting.")
                self._final_status = "failed"
                self.is_running = False
                return

        # Only commit Kafka offsets AFTER successful DB commit (at-least-once guarantee)
        self.consumer.commit(asynchronous=False)
        self.dlq_producer.flush()

    # ─── Bad message handling ─────────────────────────────────────────────────

    def _handle_bad_messages(self, bad_messages: List[tuple]):
        """Send bad messages to orbitwatch.dlq topic and quality.dead_letter table."""
        for source, payload, reason in bad_messages:
            # Publish to Kafka DLQ topic
            dlq_msg = {"original_payload": payload, "reason": reason, "source": source}
            self.dlq_producer.produce("orbitwatch.dlq", json.dumps(dlq_msg).encode("utf-8"))

            # Wrap non-JSON payloads so Postgres JSONB accepts them
            try:
                db_payload = json.dumps(json.loads(payload))
            except json.JSONDecodeError:
                db_payload = json.dumps({"raw_unparseable": payload})

            try:
                with self.engine.begin() as conn:
                    conn.execute(
                        text("""
                            INSERT INTO quality.dead_letter
                                (source_name, payload, reason_code, reason_detail, run_id)
                            VALUES (:source, :payload, :code, :detail, :run_id)
                        """),
                        {
                            "source":  source,
                            "payload": db_payload,
                            "code":    "INVALID_ENVELOPE",
                            "detail":  reason,
                            "run_id":  self.run_id,
                        },
                    )
            except Exception as exc:
                print(f"[WARN] Failed to write to quality.dead_letter: {exc}")

    # ─── DB insert with retry ─────────────────────────────────────────────────

    def _insert_with_retry(self, source: str, rows: List[Dict[str, Any]], max_retries: int = 3) -> bool:
        """Insert rows into the matching staging table with exponential-backoff retry."""
        _, target_table = SOURCE_MAP[source]
        schema, table = target_table.split(".")

        stmt = f"""
            INSERT INTO {schema}.{table}
                (event_id, natural_key, payload, mongo_batch_id,
                 kafka_topic, kafka_partition, kafka_offset, produced_at)
            VALUES
                (:event_id, :natural_key, :payload, :mongo_batch_id,
                 :kafka_topic, :kafka_partition, :kafka_offset, :produced_at)
            ON CONFLICT (natural_key, md5(payload::text)) DO NOTHING
            RETURNING event_id;
        """

        for attempt in range(max_retries):
            try:
                with self.engine.begin() as conn:
                    result = conn.execute(text(stmt), rows)
                    inserted_count = result.rowcount

                self.stats[source]["inserted"]   += inserted_count
                self.stats[source]["duplicates"] += len(rows) - inserted_count
                return True
            except SQLAlchemyError as exc:
                print(f"[DB ERROR] attempt {attempt + 1}/{max_retries}: {exc}")
                if attempt < max_retries - 1:
                    time.sleep(2 ** attempt)

        return False

    # ─── Main loop ────────────────────────────────────────────────────────────

    def run(self):
        """Subscribe and process messages until stopped or idle-timeout."""
        print(f"Starting consumer (run_id={self.run_id}). Subscribing to: {self.topics}")
        self.consumer.subscribe(self.topics)

        total_consumed = 0
        last_message_time = time.time()

        try:
            while self.is_running:
                batch: List[Any] = []
                batch_start = time.time()

                # Accumulate up to batch_size messages or 2 seconds
                while len(batch) < self.batch_size and time.time() - batch_start < 2:
                    msg = self.consumer.poll(0.1)
                    if msg is None:
                        continue
                    if msg.error():
                        if msg.error().code() == KafkaException._PARTITION_EOF:
                            continue
                        print(f"[KAFKA ERROR] {msg.error()}")
                        break
                    batch.append(msg)
                    last_message_time = time.time()

                if batch:
                    self.process_batch(batch)
                    total_consumed += len(batch)

                    if self.max_messages > 0 and total_consumed >= self.max_messages:
                        print("Reached --max-messages limit.")
                        break

                elif self.once:
                    if time.time() - last_message_time > self.idle_seconds:
                        print(f"Idle for {self.idle_seconds}s with --once set. Exiting.")
                        break

        except KeyboardInterrupt:
            pass  # _handle_signal already set is_running = False
        finally:
            # Always close cleanly and write audit, even on error / signal
            print("Closing consumer...")
            self.consumer.close()
            self._print_summary()
            self._write_audit()

    # ─── Summary & audit ─────────────────────────────────────────────────────

    def _print_summary(self):
        """Print per-source stats."""
        print("\n--- Consumer Summary ---")
        for source, counts in self.stats.items():
            if counts["consumed"] > 0 or counts["dlq"] > 0:
                print(f"{source}:")
                print(f"  Consumed:   {counts['consumed']}")
                print(f"  Inserted:   {counts['inserted']}")
                print(f"  Duplicates: {counts['duplicates']}")
                print(f"  Sent to DLQ:{counts['dlq']}")
        total_inserted = sum(c["inserted"] for c in self.stats.values())
        total_dlq      = sum(c["dlq"]      for c in self.stats.values())
        total_consumed = sum(c["consumed"] for c in self.stats.values())
        print(f"\nTotal consumed={total_consumed}, inserted={total_inserted}, DLQ={total_dlq}")

    def _write_audit(self):
        """
        Write audit.pipeline_runs and audit.data_lineage rows.

        Lineage fix: write one row per source that was consumed (consumed >= 0
        after subscribing), not only when inserted > 0.  This ensures every
        consumer run always produces 3 lineage rows (one per topic->table).
        Status fix: use 'success' / 'failed' (not 'completed').
        """
        total_consumed = sum(c["consumed"] for c in self.stats.values())
        total_inserted = sum(c["inserted"] for c in self.stats.values())
        total_dlq      = sum(c["dlq"]      for c in self.stats.values())
        finished_at    = datetime.datetime.now(datetime.timezone.utc)

        try:
            with self.engine.begin() as conn:
                # ── pipeline_runs ──────────────────────────────────────────
                conn.execute(
                    text("""
                        INSERT INTO audit.pipeline_runs
                            (run_id, pipeline_name, status,
                             rows_in, rows_out, rows_rejected,
                             started_at, finished_at)
                        VALUES
                            (:run_id, :pipeline_name, :status,
                             :rows_in, :rows_out, :rows_rejected,
                             :started_at, :finished_at)
                    """),
                    {
                        "run_id":        self.run_id,
                        "pipeline_name": "stream_consumer",
                        "status":        self._final_status,
                        "rows_in":       total_consumed,
                        "rows_out":      total_inserted,
                        "rows_rejected": total_dlq,
                        "started_at":    self.started_at,
                        "finished_at":   finished_at,
                    },
                )

                # ── data_lineage: one row per source per run ───────────────
                # Write for every source regardless of whether rows were inserted
                # (row_count = 0 is valid and shows the consumer did check that topic).
                for source, counts in self.stats.items():
                    kafka_topic, staging_table = SOURCE_MAP[source]
                    conn.execute(
                        text("""
                            INSERT INTO audit.data_lineage
                                (run_id, source_name, target_name,
                                 step_name, row_count, recorded_at)
                            VALUES
                                (:run_id, :source_name, :target_name,
                                 :step_name, :row_count, :recorded_at)
                        """),
                        {
                            "run_id":       self.run_id,
                            "source_name":  kafka_topic,
                            "target_name":  staging_table,
                            "step_name":    "stream_consumer",
                            "row_count":    counts["inserted"],
                            "recorded_at":  finished_at,
                        },
                    )

        except Exception as exc:
            print(f"[ERROR] Failed to write audit logs: {exc}")


def main():
    """CLI entry point."""
    parser = argparse.ArgumentParser(description="ORBITWATCH Stream Consumer")
    parser.add_argument("--once",         action="store_true", help="Drain available messages then exit")
    parser.add_argument("--max-messages", type=int, default=0,  help="Stop after N messages (0 = unlimited)")
    parser.add_argument("--batch-size",   type=int, default=500, help="Messages per processing batch")
    parser.add_argument("--idle-seconds", type=int, default=10,  help="Idle timeout for --once mode")

    args = parser.parse_args()

    consumer = StreamConsumer(
        batch_size=args.batch_size,
        max_messages=args.max_messages,
        idle_seconds=args.idle_seconds,
        once=args.once,
    )
    consumer.run()


if __name__ == "__main__":
    main()
