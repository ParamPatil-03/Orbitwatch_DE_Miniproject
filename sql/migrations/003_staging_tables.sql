-- Phase 4: Staging tables for streaming

CREATE SCHEMA IF NOT EXISTS staging;

CREATE TABLE IF NOT EXISTS staging.gp_raw (
    event_id uuid PRIMARY KEY,
    natural_key text NOT NULL,
    payload jsonb NOT NULL,
    mongo_batch_id text,
    kafka_topic text,
    kafka_partition int,
    kafka_offset bigint,
    produced_at timestamptz,
    loaded_at timestamptz DEFAULT now()
);

CREATE TABLE IF NOT EXISTS staging.k_index_raw (
    event_id uuid PRIMARY KEY,
    natural_key text NOT NULL,
    payload jsonb NOT NULL,
    mongo_batch_id text,
    kafka_topic text,
    kafka_partition int,
    kafka_offset bigint,
    produced_at timestamptz,
    loaded_at timestamptz DEFAULT now()
);

CREATE TABLE IF NOT EXISTS staging.solar_indices_raw (
    event_id uuid PRIMARY KEY,
    natural_key text NOT NULL,
    payload jsonb NOT NULL,
    mongo_batch_id text,
    kafka_topic text,
    kafka_partition int,
    kafka_offset bigint,
    produced_at timestamptz,
    loaded_at timestamptz DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS gp_raw_nk_hash_uq ON staging.gp_raw (natural_key, md5(payload::text));
CREATE UNIQUE INDEX IF NOT EXISTS k_index_raw_nk_hash_uq ON staging.k_index_raw (natural_key, md5(payload::text));
CREATE UNIQUE INDEX IF NOT EXISTS solar_indices_raw_nk_hash_uq ON staging.solar_indices_raw (natural_key, md5(payload::text));

CREATE INDEX IF NOT EXISTS idx_gp_raw_nk ON staging.gp_raw (natural_key);
CREATE INDEX IF NOT EXISTS idx_k_index_raw_nk ON staging.k_index_raw (natural_key);
CREATE INDEX IF NOT EXISTS idx_solar_indices_raw_nk ON staging.solar_indices_raw (natural_key);

GRANT USAGE ON SCHEMA staging TO etl_user;
GRANT SELECT, INSERT, UPDATE, DELETE ON staging.gp_raw TO etl_user;
GRANT SELECT, INSERT, UPDATE, DELETE ON staging.k_index_raw TO etl_user;
GRANT SELECT, INSERT, UPDATE, DELETE ON staging.solar_indices_raw TO etl_user;
