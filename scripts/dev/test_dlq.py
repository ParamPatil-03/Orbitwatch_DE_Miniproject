#!/usr/bin/env python3
import sys
from pathlib import Path
import json

sys.path.insert(0, str((Path(__file__).parent.parent).resolve()))
sys.path.insert(0, str((Path(__file__).parent.parent / "src").resolve()))

from confluent_kafka import Producer
from config.settings import get_settings

def main():
    settings = get_settings()
    producer = Producer({
        "bootstrap.servers": settings.kafka_bootstrap_servers,
        "acks": "all"
    })
    
    topic = "orbitwatch.gp_updates"
    
    # 1. Invalid JSON
    print("Producing invalid JSON message...")
    producer.produce(topic, b"{ invalid: json }")
    
    # 2. Missing natural_key
    print("Producing missing natural_key message...")
    bad_msg = {
        "event_id": "123e4567-e89b-12d3-a456-426614174000",
        "payload": {"a": 1},
        "source": "gp"
    }
    producer.produce(topic, json.dumps(bad_msg).encode('utf-8'))
    
    producer.flush()
    print("Done producing bad messages.")

if __name__ == "__main__":
    main()
