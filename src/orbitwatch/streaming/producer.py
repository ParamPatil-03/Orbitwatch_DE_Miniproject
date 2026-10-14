#!/usr/bin/env python3
"""
ORBITWATCH Phase 4 - Streaming Producer
Reads raw documents from MongoDB and produces messages to Redpanda topics.
"""
import argparse
import datetime
import hashlib
import json
import sys
import time
import uuid
from pathlib import Path

# Setup paths for local execution
sys.path.insert(0, str((Path(__file__).parent.parent.parent.parent).resolve()))
sys.path.insert(0, str((Path(__file__).parent.parent.parent).resolve()))

from confluent_kafka import Producer
from orbitwatch.common.db import get_mongo_client, get_postgres_engine
from config.settings import get_settings
from sqlalchemy import text


NAMESPACE_ORBITWATCH = uuid.uuid5(uuid.NAMESPACE_URL, "orbitwatch")

def generate_event_id(source: str, natural_key: str, payload_hash: str) -> str:
    """Generate deterministic event_id."""
    name = f"{source}:{natural_key}:{payload_hash}"
    return str(uuid.uuid5(NAMESPACE_ORBITWATCH, name))


class StreamProducer:
    """Producer to stream Mongo data to Redpanda."""
    
    def __init__(self, dry_run: bool = False, rate: int = 0):
        self.settings = get_settings()
        self.dry_run = dry_run
        self.rate = rate
        
        self.mongo_client = get_mongo_client()
        self.mongo_db = self.mongo_client[self.settings.mongo_db]
        
        if not dry_run:
            self.producer = Producer({
                "bootstrap.servers": self.settings.kafka_bootstrap_servers,
                "acks": "all",
                "enable.idempotence": True
            })
        
        self.stats = {
            "gp": {"sent": 0, "failed": 0},
            "k_index": {"sent": 0, "failed": 0},
            "solar_indices": {"sent": 0, "failed": 0}
        }

    def delivery_report(self, err, msg):
        """Called once for each message produced to indicate delivery result."""
        topic_map = {
            "orbitwatch.gp_updates": "gp",
            "orbitwatch.k_index_updates": "k_index",
            "orbitwatch.solar_updates": "solar_indices"
        }
        
        source = topic_map.get(msg.topic())
        if not source:
            return

        if err is not None:
            print(f"Message delivery failed: {err}")
            self.stats[source]["failed"] += 1
        else:
            self.stats[source]["sent"] += 1

    def process_source(self, source: str, limit: int = 0):
        """Process documents from a specific source."""
        collection_name = f"raw_{source}"
        topic_name = f"orbitwatch.{source}_updates"
        if source == "solar_indices":
            topic_name = "orbitwatch.solar_updates"
        
        collection = self.mongo_db[collection_name]
        cursor = collection.find(batch_size=500)
        
        if limit > 0:
            cursor = cursor.limit(limit)
            
        count = 0
        for doc in cursor:
            natural_key = str(doc.get("natural_key", ""))
            payload_hash = str(doc.get("payload_hash", ""))
            
            event_id = generate_event_id(source, natural_key, payload_hash)
            
            # Construct envelope
            envelope = {
                "event_id": event_id,
                "source": source,
                "natural_key": natural_key,
                "mongo_batch_id": str(doc.get("batch_id", "")),
                "produced_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                "payload": doc.get("payload", {})
            }
            
            if not self.dry_run:
                try:
                    self.producer.produce(
                        topic=topic_name,
                        key=natural_key.encode('utf-8'),
                        value=json.dumps(envelope).encode('utf-8'),
                        callback=self.delivery_report
                    )
                    # Periodically poll to trigger callbacks
                    if count % 1000 == 0:
                        self.producer.poll(0)
                except BufferError:
                    print(f"Local producer queue is full ({len(self.producer)} messages awaiting delivery): try again")
                    self.producer.poll(1)
                    self.producer.produce(
                        topic=topic_name,
                        key=natural_key.encode('utf-8'),
                        value=json.dumps(envelope).encode('utf-8'),
                        callback=self.delivery_report
                    )
            else:
                self.stats[source]["sent"] += 1
                
            count += 1
            if self.rate > 0:
                time.sleep(1.0 / self.rate)
                
        if not self.dry_run:
            print(f"Flushing producer for {source}...")
            self.producer.flush()

    def run(self, source: str, limit: int):
        """Run the producer for the given source."""
        sources = ["gp", "k_index", "solar_indices"] if source == "all" else [source]
        
        for s in sources:
            print(f"Processing source: {s}")
            self.process_source(s, limit)
            
        print("\n--- Producer Summary ---")
        for s, counts in self.stats.items():
            if counts["sent"] > 0 or counts["failed"] > 0:
                print(f"{s}: Sent={counts['sent']}, Failed={counts['failed']}")
                
        self.write_audit()

    def write_audit(self):
        """Write audit row to audit.pipeline_runs."""
        engine = get_postgres_engine("etl")
        run_id = str(uuid.uuid4())
        total_processed = sum(c["sent"] for c in self.stats.values())
        total_failed = sum(c["failed"] for c in self.stats.values())
        status = "success" if total_failed == 0 else "failed"
        
        with engine.begin() as conn:
            conn.execute(
                text("""
                    INSERT INTO audit.pipeline_runs
                    (run_id, pipeline_name, status, rows_in, rows_out, rows_rejected, started_at, finished_at)
                    VALUES (:run_id, :pipeline_name, :status, :rows_in, :rows_out, :rows_rejected, :started_at, :finished_at)
                """),
                {
                    "run_id": run_id,
                    "pipeline_name": "stream_producer",
                    "status": status,
                    "rows_in": total_processed + total_failed,
                    "rows_out": total_processed,
                    "rows_rejected": total_failed,
                    "started_at": datetime.datetime.now(datetime.timezone.utc),
                    "finished_at": datetime.datetime.now(datetime.timezone.utc)
                }
            )


def main():
    parser = argparse.ArgumentParser(description="ORBITWATCH Stream Producer")
    parser.add_argument("--source", choices=["gp", "k_index", "solar_indices", "all"], required=True)
    parser.add_argument("--limit", type=int, default=0, help="Max messages per source")
    parser.add_argument("--rate", type=int, default=0, help="Max messages per second")
    parser.add_argument("--dry-run", action="store_true", help="Build and count without sending")
    
    args = parser.parse_args()
    
    producer = StreamProducer(dry_run=args.dry_run, rate=args.rate)
    producer.run(args.source, args.limit)


if __name__ == "__main__":
    main()
