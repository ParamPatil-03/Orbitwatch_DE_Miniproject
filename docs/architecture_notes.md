# ORBITWATCH Architecture Notes

## Planned Data Flow

The platform follows a layered data engineering architecture to extract, process, and serve space data:

1. **Sources**: External APIs including CelesTrak (satellite and debris catalog) and NOAA SWPC (space weather conditions).
2. **Ingestion**: FastAPI endpoints and Python scripts pull raw data and store it un-transformed in **MongoDB**. This ensures we never lose original source data if downstream processing fails.
3. **Stream**: Raw events are published to **Redpanda (Kafka)** to decouple ingestion from processing and enable real-time consumption.
4. **Staging**: Data is pulled from Redpanda, flattened, and inserted into the `staging` PostgreSQL schema. 
5. **Warehouse & ETL**: Data is cleaned, validated (Great Expectations), and transformed. Valid records move to the `warehouse` schema for analytical queries.
6. **Serving**: A Streamlit dashboard queries the `warehouse` schema (using a read-only role) to visualize orbital tracks, debris density, and space-weather correlations.

## Database Schemas

The PostgreSQL database is organized into four distinct schemas for logical separation:

- **`staging`**: Temporary landing zone for flattened raw data. Tables here closely mirror the source JSON structure.
- **`warehouse`**: The curated analytical layer. Contains dimension and fact tables optimized for dashboard queries and data science.
- **`audit`**: System metadata and observability. Holds pipeline execution logs and lineage data.
- **`quality`**: Data quality management. Holds records that fail validation, ensuring they aren't lost and can be investigated.

## Audit and Quality Tables

- **`audit.pipeline_runs`**: Logs the start, end, status, and row-counts for every ETL run, ensuring operations visibility.
- **`audit.data_lineage`**: Tracks data movement between tables/systems, providing traceability from source to target for any given row.
- **`audit.access_log`**: A lightweight log for tracking critical user/system actions within the platform.
- **`quality.dead_letter`**: The Dead Letter Queue (DLQ). Any data payload that fails Great Expectations validations is inserted here along with a reason code, allowing engineers to fix the logic or data and reprocess it without querying the source APIs again.
