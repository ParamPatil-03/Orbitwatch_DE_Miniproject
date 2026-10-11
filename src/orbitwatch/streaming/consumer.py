#!/usr/bin/env python3
"""
ORBITWATCH Phase 4 - Streaming Consumer
Consumes messages from Redpanda topics and inserts them into PostgreSQL staging tables.
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


class StreamConsumer:
    """Consumer for streaming data from Redpanda to Postgres."""

    def __init__(self, batch_size: int, max_messages: int, idle_seconds: int, once: bool):
        self.settings = get_settings()
        self.batch_size = batch_size
        self.max_messages = max_messages
        self.idle_seconds = idle_seconds
        self.once = once
        self.run_id = str(uuid.uuid4())
        
        self.engine = get_postgres_engine("etl")
        
        # Kafka configuration
        self.consumer = Consumer({
            "bootstrap.servers": self.settings.kafka_bootstrap_servers,
            "group.id": "orbitwatch-staging-consumer",
            "auto.offset.reset": "earliest",
            "enable.auto.commit": False
        })
        
        self.dlq_producer = Producer({
            "bootstrap.servers": self.settings.kafka_bootstrap_servers,
            "acks": "all"
        })
        
        self.topics = [
            "orbitwatch.gp_updates", 
            "orbitwatch.k_index_updates", 
            "orbitwatch.solar_updates"
        ]
        
        self.stats = {
            "gp": {"consumed": 0, "inserted": 0, "duplicates": 0, "dlq": 0},
            "k_index": {"consumed": 0, "inserted": 0, "duplicates": 0, "dlq": 0},
            "solar_indices": {"consumed": 0, "inserted": 0, "duplicates": 0, "dlq": 0}
        }
        
        self.is_running = True
        
        # Handle graceful shutdown
        signal.signal(signal.SIGINT, self._handle_signal)
        signal.signal(signal.SIGTERM, self._handle_signal)

    def _handle_signal(self, signum, frame):
        """Signal handler for graceful shutdown."""
        print(f"\nReceived signal {signum}, shutting down gracefully...")
        self.is_running = False

    def validate_message(self, val_str: str) -> tuple[bool, str, Dict[str, Any]]:
        """Validate JSON envelope."""
        try:
            msg = json.loads(val_str)
        except json.JSONDecodeError:
            return False, "Invalid JSON", {}
            
        required_keys = {"event_id", "natural_key", "payload", "source"}
        if not required_keys.issubset(msg.keys()):
            return False, f"Missing required fields: {required_keys - msg.keys()}", msg
            
        return True, "", msg

    def process_batch(self, batch: List[Any]):
        """Process a batch of messages."""
        if not batch:
            return

        valid_by_source = {"gp": [], "k_index": [], "solar_indices": []}
        bad_messages = []

        for msg in batch:
            topic = msg.topic()
            source = topic.replace("orbitwatch.", "").replace("_updates", "")
            if source == "solar":
                source = "solar_indices"
            
            # Record consumed
            if source in self.stats:
                self.stats[source]["consumed"] += 1
            
            val_str = msg.value().decode('utf-8') if msg.value() else "{}"
            is_valid, reason, parsed = self.validate_message(val_str)
            
            if is_valid:
                valid_by_source[source].append({
                    "event_id": parsed["event_id"],
                    "natural_key": parsed["natural_key"],
                    "payload": json.dumps(parsed["payload"]),
                    "mongo_batch_id": parsed.get("mongo_batch_id"),
                    "kafka_topic": topic,
                    "kafka_partition": msg.partition(),
                    "kafka_offset": msg.offset(),
                    "produced_at": parsed.get("produced_at")
                })
            else:
                if source in self.stats:
                    self.stats[source]["dlq"] += 1
                bad_messages.append((source, val_str, reason))

        # Handle bad messages
        if bad_messages:
            self._handle_bad_messages(bad_messages)

        # Handle valid messages
        for source, rows in valid_by_source.items():
            if not rows:
                continue
                
            success = self._insert_with_retry(source, rows)
            if not success:
                print(f"Failed to insert batch for {source} after retries. Exiting.")
                self.is_running = False
                return
            
        # If DB write successful, commit offsets
        self.consumer.commit(asynchronous=False)
        self.dlq_producer.flush()

    def _handle_bad_messages(self, bad_messages: List[tuple]):
        """Send bad messages to Kafka DLQ and Postgres quality.dead_letter."""
        for source, payload, reason in bad_messages:
            # To Kafka DLQ
            dlq_msg = {
                "original_payload": payload,
                "reason": reason,
                "source": source
            }
            self.dlq_producer.produce("orbitwatch.dlq", json.dumps(dlq_msg).encode('utf-8'))
            
            # To Postgres dead_letter (payload column is JSONB)
            # If payload is invalid JSON string, wrap it so Postgres accepts it
            try:
                db_payload = json.dumps(json.loads(payload))
            except json.JSONDecodeError:
                db_payload = json.dumps({"raw_unparseable": payload})

            with self.engine.begin() as conn:
                try:
                    conn.execute(
                        text("""
                            INSERT INTO quality.dead_letter 
                            (source_name, payload, reason_code, reason_detail, run_id)
                            VALUES (:source, :payload, :code, :detail, :run_id)
                        """),
                        {
                            "source": source,
                            "payload": db_payload,
                            "code": "INVALID_ENVELOPE",
                            "detail": reason,
                            "run_id": self.run_id
                        }
                    )
                except Exception as e:
                    print(f"Failed to write to dead_letter: {e}")

    def _insert_with_retry(self, source: str, rows: List[Dict[str, Any]], max_retries: int = 3) -> bool:
        """Insert rows into staging table with retry logic."""
        table_name = f"{source}_raw"
        
        # Build multi-value insert statement
        stmt = f"""
            INSERT INTO staging.{table_name}
            (event_id, natural_key, payload, mongo_batch_id, kafka_topic, kafka_partition, kafka_offset, produced_at)
            VALUES (:event_id, :natural_key, :payload, :mongo_batch_id, :kafka_topic, :kafka_partition, :kafka_offset, :produced_at)
            ON CONFLICT (natural_key, md5(payload::text)) DO NOTHING
            RETURNING event_id;
        """
        
        for attempt in range(max_retries):
            try:
                with self.engine.begin() as conn:
                    result = conn.execute(text(stmt), rows)
                    inserted_count = result.rowcount
                    
                self.stats[source]["inserted"] += inserted_count
                self.stats[source]["duplicates"] += (len(rows) - inserted_count)
                return True
            except SQLAlchemyError as e:
                print(f"DB Error (attempt {attempt+1}/{max_retries}): {e}")
                if attempt < max_retries - 1:
                    time.sleep(2 ** attempt)
        return False

    def run(self):
        """Run the consumer loop."""
        print(f"Starting consumer. Subscribing to: {self.topics}")
        self.consumer.subscribe(self.topics)
        
        total_consumed = 0
        last_message_time = time.time()
        
        try:
            while self.is_running:
                batch = []
                # Poll for batch_size messages or 2 seconds
                batch_start = time.time()
                while len(batch) < self.batch_size and time.time() - batch_start < 2:
                    msg = self.consumer.poll(0.1)
                    if msg is None:
                        continue
                    if msg.error():
                        if msg.error().code() == KafkaException._PARTITION_EOF:
                            continue
                        else:
                            print(msg.error())
                            break
                    batch.append(msg)
                    last_message_time = time.time()
                
                if batch:
                    self.process_batch(batch)
                    total_consumed += len(batch)
                    
                    if self.max_messages > 0 and total_consumed >= self.max_messages:
                        print("Reached max messages limit.")
                        break
                        
                elif self.once:
                    # If --once is set and we've waited idle_seconds with no messages
                    if time.time() - last_message_time > self.idle_seconds:
                        print("Idle timeout reached. Exiting as --once was set.")
                        break

        except KeyboardInterrupt:
            pass
        finally:
            print("Closing consumer...")
            self.consumer.close()
            self._print_summary()
            self._write_audit()

    def _print_summary(self):
        print("\n--- Consumer Summary ---")
        for source, counts in self.stats.items():
            if counts["consumed"] > 0:
                print(f"{source}:")
                print(f"  Consumed: {counts['consumed']}")
                print(f"  Inserted: {counts['inserted']}")
                print(f"  Duplicates: {counts['duplicates']}")
                print(f"  Sent to DLQ: {counts['dlq']}")

    def _write_audit(self):
        total_consumed = sum(c["consumed"] for c in self.stats.values())
        total_inserted = sum(c["inserted"] for c in self.stats.values())
        total_dlq = sum(c["dlq"] for c in self.stats.values())
        
        try:
            with self.engine.begin() as conn:
                # pipeline runs
                conn.execute(
                    text("""
                        INSERT INTO audit.pipeline_runs
                        (run_id, pipeline_name, status, rows_in, rows_out, rows_rejected, started_at, finished_at)
                        VALUES (:run_id, :pipeline_name, :status, :rows_in, :rows_out, :rows_rejected, :started_at, :finished_at)
                    """),
                    {
                        "run_id": self.run_id,
                        "pipeline_name": "stream_consumer",
                        "status": "completed",
                        "rows_in": total_consumed,
                        "rows_out": total_inserted,
                        "rows_rejected": total_dlq,
                        "started_at": datetime.datetime.now(datetime.timezone.utc),
                        "finished_at": datetime.datetime.now(datetime.timezone.utc)
                    }
                )
                
                # data lineage
                for source, counts in self.stats.items():
                    if counts["inserted"] > 0:
                        conn.execute(
                            text("""
                                INSERT INTO audit.data_lineage
                                (run_id, source_name, target_name, step_name, row_count, recorded_at)
                                VALUES (:run_id, :source_name, :target_name, :step_name, :row_count, :recorded_at)
                            """),
                            {
                                "run_id": self.run_id,
                                "source_name": f"orbitwatch.{source}_updates",
                                "target_name": f"staging.{source}_raw",
                                "step_name": "stream_consumer",
                                "row_count": counts["inserted"],
                                "recorded_at": datetime.datetime.now(datetime.timezone.utc)
                            }
                        )
        except Exception as e:
            print(f"Failed to write audit logs: {e}")


def main():
    parser = argparse.ArgumentParser(description="ORBITWATCH Stream Consumer")
    parser.add_argument("--once", action="store_true", help="Drain available messages then exit")
    parser.add_argument("--max-messages", type=int, default=0, help="Max messages to consume")
    parser.add_argument("--batch-size", type=int, default=500, help="Batch size")
    parser.add_argument("--idle-seconds", type=int, default=10, help="Seconds to wait before exiting with --once")
    
    args = parser.parse_args()
    
    consumer = StreamConsumer(
        batch_size=args.batch_size,
        max_messages=args.max_messages,
        idle_seconds=args.idle_seconds,
        once=args.once
    )
    consumer.run()


if __name__ == "__main__":
    main()
