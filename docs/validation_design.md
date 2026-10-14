# ORBITWATCH – Validation Layer Architecture & Design (Phase 5)

## 1. Overview & Two-Stage Validation Strategy

Phase 5 introduces robust data quality assurance and validation to ORBITWATCH using **Great Expectations (GX 1.x)**.
To maintain high data integrity while gaining full visibility into upstream data defects, validation operates under a **two-stage architecture**:

```
[Raw Staging / Mongo]
        │
        ▼
   (Load & Flatten)
        │
        ▼
 ┌───────────────┐
 │   RAW Suite   │ ──► Findings Only: Logs violations, metrics & counts
 └───────────────┘     (Never halts pipeline or alters exit codes)
        │
        ▼
 ┌───────────────┐
 │ Clean & Route │ ──► Valid rows pass forward
 └───────────────┘ ──► Invalid rows -> data/errors/rejected_<dataset>.csv & quality.dead_letter
        │
        ▼
 ┌───────────────┐
 │  CLEAN Suite  │ ──► Strict Quality Gate: All rules must pass 100%
 └───────────────┘     (Any failure halts pipeline with exit code 1)
        │
        ▼
[staging.*_clean Tables]
```

### 1.1 Stage 1: RAW Suite (Findings)
The RAW suite executes on the incoming raw dataset immediately after extraction and light type coercion.
- **Goal**: Measure raw data hygiene, track real-world upstream anomalies, and generate diagnostic evidence.
- **Threshold**: Set to `mostly=1.0` so every anomaly is detected and recorded.
- **Pipeline behavior**: Failures in the RAW suite are treated as **findings**, not fatal errors. They are logged and captured in Data Docs without failing the validation job.

### 1.2 Stage 2: CLEAN Suite (Quality Gate)
The CLEAN suite runs on the output of the Phase 2 cleaning functions.
- **Goal**: Guarantee that data entering downstream analytics and staging clean tables adheres to all structural, relational, and physical constraints.
- **Pipeline behavior**: This acts as a strict **quality gate**. If any expectation in the clean suite fails, `run_validation.py` exits with status `1`.

---

## 2. Expectations Catalog & Physical Rationale

Every rule applied in ORBITWATCH corresponds to a real-world physical, mathematical, or aerospace invariant:

| Dataset | Column(s) | Rule / Expectation | Physical & Operational Rationale |
| :--- | :--- | :--- | :--- |
| **GP** | `norad_cat_id` | `ExpectColumnValuesToNotBeNull` | Every tracked orbital body must possess an official CelesTrak/NORAD identifier. |
| **GP** | `inclination` | `ExpectColumnValuesToBeBetween(0.0, 180.0)` | Inclination is the orbital plane angle relative to the equatorial plane ($0^\circ \le i \le 180^\circ$). Beyond $180^\circ$ is geometrically invalid. |
| **GP** | `eccentricity` | `ExpectColumnValuesToBeBetween(0.0, 0.9999999)` | For closed Earth orbits, eccentricity must satisfy $0 \le e < 1$. Values $\ge 1$ represent parabolic or hyperbolic escape trajectories not bound to Earth. |
| **GP** | `mean_motion` | `ExpectColumnValuesToBeBetween(min=1e-9)` | Mean motion measures revolutions per day ($n > 0$). Zero or negative values indicate non-orbiting or corrupt ephemeris records. |
| **GP** | `epoch` | `ExpectColumnValuesToNotBeNull` | Ephemeris data is valid only at a specific instant in time; timeless state vectors cannot be propagated. |
| **GP** | `norad_cat_id, epoch` | `ExpectCompoundColumnsToBeUnique` | A physical satellite cannot occupy multiple contradictory state vectors at the exact same instant. |
| **GP** | `orbit_regime` (clean) | `ExpectColumnValuesToBeInSet(["LEO", "MEO", "GEO", "HEO", "UNKNOWN"])` | Classifies orbital altitude zones (e.g. LEO $< 2,000$ km; GEO $\approx 35,786$ km) computed via Keplerian orbital dynamics: $a = (\mu / n^2)^{1/3}$. |
| **SATCAT** | `norad_cat_id` | `ExpectColumnValuesToNotBeNull`, `ExpectColumnValuesToBeUnique` | Master satellite catalog primary key must uniquely identify cataloged payloads and debris. |
| **SATCAT** | `object_type` | `ExpectColumnValuesToBeInSet(["PAY", "R/B", "DEB", "UNK"])` | Standard satellite classifications: Payload (PAY), Rocket Body (R/B), Debris (DEB), or Unknown (UNK). |
| **SATCAT** | `apogee, perigee` | `ExpectColumnPairValuesAToBeGreaterThanB(or_equal=True)` | Apogee is the point of greatest altitude; perigee is the point of closest approach. Perigee cannot exceed apogee. |
| **SATCAT** | `decay_date` | Null allowed | Operational satellites currently in orbit have no decay date; null decay date is expected and valid. |
| **K-Index** | `time_tag` | `ExpectColumnValuesToNotBeNull`, `ExpectColumnValuesToBeUnique` | Space weather measurements require distinct, contiguous observation timestamps. |
| **K-Index** | `kp_index` | `ExpectColumnValuesToBeBetween(0.0, 9.0)` | The planetary Kp-index is defined strictly on a 0 to 9 quasi-logarithmic geomagnetic activity scale. |
| **Solar Indices** | `time_tag` | `ExpectColumnValuesToNotBeNull`, `ExpectColumnValuesToBeUnique` | Daily space weather observation timestamps must be unique. |
| **Solar Indices** | `f107` | `ExpectColumnValuesToBeBetween(min=0.0)` | 10.7 cm solar radio flux ($F_{10.7}$) represents radiant energy and cannot be negative. Upstream -1 sentinels denote missing data. |
| **Solar Indices** | `ssn` | `ExpectColumnValuesToBeBetween(min=0.0)` | International Sunspot Number represents physical counts of spots/groups and cannot be negative. |

---

## 3. Rejected Row Routing & Quarantine Strategy

When data fails business rules or physics invariants during the cleaning phase:
1. **Error CSV Export**:
   - Dropped rows are written to `data/errors/rejected_<dataset>.csv`.
   - Each row is enriched with `reason_code` (e.g. `INCLINATION_OUT_OF_RANGE`, `NEGATIVE_MEAN_MOTION`) and `reason_detail` describing the exact values.
2. **Dead-Letter Database Quarantine**:
   - Rejected rows are quarantined in PostgreSQL table `quality.dead_letter`.
   - Populated with `source_name = 'validation:<dataset>'`, `payload = to_jsonb(row)`, `reason_code`, and `reason_detail`.
   - Previous entries for the same source are deleted prior to insertion, ensuring full idempotency on repeated runs.
3. **Auditing & Lineage**:
   - `audit.pipeline_runs`: Logs `pipeline_name`, start/completion timestamps, `rows_in`, `rows_out`, `rows_rejected`, and final execution status (`success` or `failed`).
   - `audit.data_lineage`: Records row transformation from `source_name` to `target_name` (`staging.<dataset>_clean`).
