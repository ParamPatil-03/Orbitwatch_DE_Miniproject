# ORBITWATCH – Data Normalization Analysis (1NF to 3NF)

## 1. Overview and Scope

This document provides a relational normalization analysis of the ingested satellite catalog (`staging.satcat_clean`). The source dataset is ingested as a wide, denormalized staging table. In accordance with the project architecture, the analytical layer utilizes a Star Schema in schema `dw` rather than a separate 3NF relational schema. This analysis demonstrates how the flat staging table would normalize into Third Normal Form (3NF).

---

## 2. Flat Unnormalized Table: `staging.satcat_clean`

The ingested satellite catalog contains 20 attributes:

```text
satcat_clean(
    norad_cat_id,       -- (PK/Candidate Key) Unique satellite catalog ID
    object_name,        -- Satellite / object designation
    object_id,          -- International designator (e.g., 1998-067A)
    object_type,        -- PAY (Payload), R/B (Rocket Body), DEB (Debris), UNK
    ops_status_code,    -- Operational status (+, -, P, B, etc.)
    owner,              -- Country or organization code (e.g., US, CIS, PRC)
    launch_date,        -- Timestamp of launch
    launch_site,        -- Launch facility code (e.g., AFETR, TYMSC)
    decay_date,         -- Timestamp of atmospheric reentry (nullable)
    period,             -- Orbital period in minutes
    inclination,        -- Orbital inclination in degrees
    apogee,             -- Apogee altitude in km
    perigee,            -- Perigee altitude in km
    rcs,                -- Radar cross section category
    data_status_code,   -- Data quality status
    orbit_center,       -- Primary body (e.g., EA for Earth)
    orbit_type,         -- Orbit classification
    orbit_regime,       -- Derived regime (LEO, MEO, GEO, HEO, UNKNOWN)
    is_outlier,         -- Data hygiene outlier flag
    loaded_at           -- Pipeline ingest timestamp
)
```

---

## 3. Functional Dependencies (FDs)

Based on the domain rules and real data semantics:

1. **FD1 (Primary Key):**  
   $$\text{norad\_cat\_id} \rightarrow \{\text{object\_name}, \text{object\_id}, \text{object\_type}, \text{ops\_status\_code}, \text{owner}, \text{launch\_date}, \text{launch\_site}, \text{decay\_date}, \text{period}, \text{inclination}, \text{apogee}, \text{perigee}, \text{rcs}, \text{data\_status\_code}, \text{orbit\_center}, \text{orbit\_type}, \text{orbit\_regime}, \text{is\_outlier}, \text{loaded\_at}\}$$
2. **FD2 (International Designator Alternate Key):**  
   $$\text{object\_id} \rightarrow \text{norad\_cat\_id}$$ *(when non-null and uniquely assigned)*
3. **FD3 (Transitive Orbital Regime Dependency):**  
   $$\{\text{apogee}, \text{perigee}\} \rightarrow \text{orbit\_regime}$$  
   *Orbit regime is deterministically classified based on orbital bounds (e.g., apogee < 2000 km $\rightarrow$ LEO).*
4. **FD4 (Transitive Launch Entity Dependency):**  
   $$\text{launch\_site} \rightarrow \text{launch\_site\_country}$$ *(if site metadata is expanded)*

---

## 4. Normalization Progression

### First Normal Form (1NF)
- **Requirement:** Each attribute must contain only atomic (indivisible) values, and each record must be unique.
- **Evaluation:** `staging.satcat_clean` satisfies 1NF:
  - Every column holds atomic scalar values (text, double precision, timestamp, boolean).
  - No repeating groups or nested arrays exist.
  - `norad_cat_id` provides unique row identification.

### Second Normal Form (2NF)
- **Requirement:** Table must be in 1NF and have no partial key dependencies (every non-key attribute must be fully functionally dependent on the entire primary key).
- **Evaluation:** `staging.satcat_clean` has a single-attribute primary key (`norad_cat_id`). Because the primary key is not composite, partial key dependencies cannot exist. Therefore, the table is automatically in **2NF**.

### Third Normal Form (3NF)
- **Requirement:** Table must be in 2NF and contain no transitive dependencies (no non-prime attribute is functionally dependent on another non-prime attribute; $X \rightarrow Y$ implies $X$ is a superkey or $Y$ is a prime attribute).
- **Violation in Flat Table:**
  - `norad_cat_id` $\rightarrow$ `{apogee, perigee}`
  - `{apogee, perigee}` $\rightarrow$ `orbit_regime`
  - Because `{apogee, perigee}` is not a candidate key, `norad_cat_id` $\rightarrow$ `orbit_regime` represents a transitive dependency.
  - `object_type` (PAY, R/B, DEB, UNK) has descriptive domain definitions independent of satellite instances.

### 3NF Decomposition
To achieve strict 3NF without transitive dependencies, the flat entity decomposes into three normalized relations:

1. **`satellites` (3NF Entity):**  
   `satellites(norad_cat_id [PK], object_name, object_id, object_type_code [FK], ops_status_code, owner, launch_date, launch_site, decay_date, period, inclination, apogee, perigee, rcs, data_status_code, orbit_center, orbit_type, is_outlier, loaded_at)`
2. **`object_types` (Reference Table):**  
   `object_types(object_type_code [PK], type_name, description)`
3. **`orbit_regimes` (Domain Reference Table):**  
   `orbit_regimes(regime_code [PK], min_apogee_km, max_apogee_km, description)`

---

## 5. Architectural Decision: Star Schema vs. 3NF Core

In analytical systems (OLAP), strict 3NF introduces complex join paths that degrade analytical query throughput. ORBITWATCH transitions directly from clean staging into a dimensional **Star Schema** in the `dw` schema:

- **Dimensions (`dim_satellite`, `dim_orbit_regime`, `dim_object_type`, `dim_date`):** Pre-classified attributes with surrogate keys, eliminating costly runtime computations.
- **Facts (`fact_gp_snapshot`, `fact_decay_month`, `fact_space_weather_month`):** Clean numerical metrics and event counts joined to dimensions along simple single-hop foreign key relationships.
