# MongoDB Design for ORBITWATCH Raw Layer

## Why MongoDB?
MongoDB is chosen for the raw data ingestion layer because it natively supports unstructured and semi-structured data. Our data sources (CelesTrak CSVs, NOAA JSON payloads) have different schemas, varying numbers of fields, and potential upstream schema drifts. By storing these "as-is" in MongoDB's BSON format, we ensure immutable, unaltered data storage without needing complex relational migrations every time an upstream provider adds or renames a field.

## Document Shape
Each record is stored as a single document with the following structure:
- `payload`: The original JSON record, unaltered.
- `metadata`:
    - `source`: The origin of the data (`satcat`, `gp`, `k_index`, `solar_indices`).
    - `batch_id`: UUID string tracking the ingestion run.
    - `ingested_at`: UTC timestamp of when the record hit the API.
    - `natural_key`: String composed of the unique identifier(s) from the payload (e.g., `NORAD_CAT_ID` for SATCAT).
    - `payload_hash`: SHA-256 hash of the canonical JSON payload, enabling fast duplicate detection.
    - `schema_version`: Integer tracking our internal metadata schema, starting at 1.

## Collections
We maintain dedicated collections for each source for isolation and independent scaling:
- `raw_satcat`
- `raw_gp`
- `raw_k_index`
- `raw_solar_indices`

Additionally, we maintain two operational collections:
- `ingest_batches`: Tracks metadata per ingestion run (counts of received, inserted, duplicate, and rejected records).
- `rejected_events`: Captures payloads that failed validation, keeping the reason and the raw body for later review.

## Indexes
- **Idempotency (Unique Index)**: `(source, natural_key, payload_hash)`. This guarantees that if the exact same record is re-ingested from the same source, it violates a unique constraint and can be gracefully counted as a duplicate without creating duplicate data.
- **Query Performance**: Standard indexes are placed on `batch_id` and `ingested_at` to facilitate fast lookups and reporting (e.g., GET `/stats` or paginated lookups in the API).
