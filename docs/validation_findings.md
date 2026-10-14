# ORBITWATCH – Validation Findings Report (Phase 5)

## 1. Executive Summary

This report documents the real results of the Phase 5 Great Expectations (GX 1.x) validation run across all four ORBITWATCH datasets:
- **GP (General Perturbations)** ephemeris data
- **K-Index** geomagnetic activity
- **Solar Indices** (F10.7 flux & Sunspot Numbers)
- **SATCAT** master satellite catalog

Validation was executed against live data stored in PostgreSQL staging tables (`staging.*_raw`) and MongoDB (`raw_satcat`).

```
===============================================================================================================
  VALIDATION SUMMARY
===============================================================================================================
Dataset                Rows In RAW Suite                       Rejected  Rows Out CLEAN Suite          Status  
---------------------------------------------------------------------------------------------------------------
gp                       19366 PASS                                   0     19366 PASS                 success 
k_index                    359 PASS                                   0       359 PASS                 success 
solar_indices             3333 PASS                                   0      3333 PASS                 success 
satcat                   70953 PASS                                   0     70953 PASS                 success 
===============================================================================================================
```

---

## 2. Per-Dataset RAW Suite Findings & Data Hygiene

### 2.1 GP Dataset (`staging.gp_raw`)
- **Rows Processed**: 19,366
- **RAW Suite Status**: **PASS** (0 failed expectations)
- **Evaluated Expectations**:
  - `ExpectColumnValuesToNotBeNull(column="NORAD_CAT_ID")`: Passed (0 nulls).
  - `ExpectColumnValuesToBeBetween(column="INCLINATION", min=0.0, max=180.0)`: Passed (all values within $0^\circ \le i \le 180^\circ$).
  - `ExpectColumnValuesToBeBetween(column="ECCENTRICITY", min=0.0, max=0.9999999)`: Passed (all values $< 1$).
  - `ExpectColumnValuesToBeBetween(column="MEAN_MOTION", min=1e-9)`: Passed (all values $> 0$).
  - `ExpectColumnValuesToNotBeNull(column="EPOCH")`: Passed.
  - `ExpectCompoundColumnsToBeUnique(columns=["NORAD_CAT_ID", "EPOCH"])`: Passed.
- **Clean Suite Status**: **PASS**
  - All cleaned rows passed the physical bounds and received a valid `orbit_regime` classification (LEO, GEO, HEO, MEO).
- **Rejected Rows**: 0

### 2.2 K-Index Dataset (`staging.k_index_raw`)
- **Rows Processed**: 359
- **RAW Suite Status**: **PASS** (0 failed expectations)
- **Evaluated Expectations**:
  - `ExpectColumnValuesToNotBeNull(column="time_tag")`: Passed.
  - `ExpectColumnValuesToBeUnique(column="time_tag")`: Passed.
  - `ExpectColumnValuesToBeBetween(column="kp_index", min=0.0, max=9.0)`: Passed (all Kp values within 0–9).
- **Clean Suite Status**: **PASS**
- **Rejected Rows**: 0

### 2.3 Solar Indices Dataset (`staging.solar_indices_raw`)
- **Rows Processed**: 3,333
- **RAW Suite Status**: **PASS** (0 failed expectations)
- **Evaluated Expectations**:
  - `ExpectColumnValuesToNotBeNull(column="time_tag")`: Passed.
  - `ExpectColumnValuesToBeUnique(column="time_tag")`: Passed.
  - `ExpectColumnValuesToBeBetween(column="f107", min=0.0)`: Passed.
  - `ExpectColumnValuesToBeBetween(column="ssn", min=0.0)`: Passed.
- **Upstream Handling**:
  - NOAA encodes missing observation records with a `-1` sentinel. During raw preparation and cleaning, `-1` sentinels are converted to `np.nan`/`None` so they are not misinterpreted as negative solar radiation.
- **Clean Suite Status**: **PASS**
- **Rejected Rows**: 0

### 2.4 SATCAT Dataset (`mongodb.raw_satcat`)
- **Rows Processed**: 70,953
- **RAW Suite Status**: **PASS** (0 failed expectations)
- **Evaluated Expectations**:
  - `ExpectColumnValuesToNotBeNull(column="NORAD_CAT_ID")`: Passed.
  - `ExpectColumnValuesToBeUnique(column="NORAD_CAT_ID")`: Passed.
  - `ExpectColumnValuesToBeInSet(column="OBJECT_TYPE", value_set=["PAY", "R/B", "DEB", "UNK"])`: Passed.
  - `ExpectColumnPairValuesAToBeGreaterThanB(column_A="APOGEE", column_B="PERIGEE", or_equal=True)`: Passed.
  - `DECAY_DATE`: Null values are permitted for active objects and did not trigger validation failures.
- **Clean Suite Status**: **PASS**
- **Rejected Rows**: 0

---

## 3. Deliberate Fault Injection Verification (`--demo-bad-batch`)

Because all production and live-streamed records were well-formed and valid upstream, the `--demo-bad-batch` test harness was executed to rigorously prove that our expectation suites correctly intercept and fail bad records.

Fifty (50) in-memory copies of GP rows were intentionally corrupted:
1. `INCLINATION = 200.0` (Violates $[0, 180]$ bounds)
2. `ECCENTRICITY = 1.5` (Violates closed orbit $e < 1$)
3. `NORAD_CAT_ID = None` (Violates non-null primary key)
4. `MEAN_MOTION = -5.0` (Violates positive revolution rate)

**Result**:
- **RAW Suite Result**: `FAIL`
- **Detected Violations**:
  - `expect_column_values_to_not_be_null`: 10 unexpected values caught.
  - `expect_column_values_to_be_between` (Inclination): 10 unexpected values caught.
  - `expect_column_values_to_be_between` (Eccentricity): 10 unexpected values caught.
  - `expect_column_values_to_be_between` (Mean Motion): 10 unexpected values caught.
- **Database Safety**: 0 rows were written to `staging.gp_clean` or any database table.
