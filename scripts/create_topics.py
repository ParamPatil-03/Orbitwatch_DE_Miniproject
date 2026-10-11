"""
Idempotent script to create Redpanda (Kafka) topics for ORBITWATCH.
Uses confluent_kafka.admin.AdminClient.
"""
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str((Path(__file__).parent.parent).resolve()))

from confluent_kafka.admin import AdminClient, NewTopic
from config.settings import get_settings

def main():
    settings = get_settings()
    admin = AdminClient({'bootstrap.servers': settings.kafka_bootstrap_servers})
    
    # Define topics to create
    topics = [
        NewTopic("orbitwatch.gp_updates", num_partitions=3, replication_factor=1),
        NewTopic("orbitwatch.k_index_updates", num_partitions=1, replication_factor=1),
        NewTopic("orbitwatch.solar_updates", num_partitions=1, replication_factor=1),
        NewTopic("orbitwatch.dlq", num_partitions=1, replication_factor=1)
    ]
    
    print("Creating topics...")
    fs = admin.create_topics(topics)
    
    for topic, f in fs.items():
        try:
            f.result()  # The result itself is None
            print(f"Topic {topic} created successfully.")
        except Exception as e:
            if "TOPIC_ALREADY_EXISTS" in str(e):
                print(f"Topic {topic} already exists.")
            else:
                print(f"Failed to create topic {topic}: {e}")
                
    # Print topic list
    print("\nCurrent Topics:")
    md = admin.list_topics(timeout=10)
    for t in md.topics:
        if t.startswith("orbitwatch"):
            print(f"- {t} (partitions: {len(md.topics[t].partitions)})")

if __name__ == "__main__":
    main()
