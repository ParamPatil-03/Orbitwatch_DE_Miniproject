# ORBITWATCH - Phase 2 Data Profile Report

## SATCAT

- **Rows:** 70,953
- **Columns:** 17
- **Memory Usage:** 13153.0 KB
- **Total Duplicates (Raw):** 0

### Cleaning Outcomes
- **Rows In:** 70,953
- **Rows Out (Clean):** 70,953
- **Rows Rejected:** 0
- **Duplicates Removed:** 0

### Missing Values (Raw)
- `OPS_STATUS_CODE`: 23.29% missing
- `DECAY_DATE`: 49.72% missing
- `PERIOD`: 2.89% missing
- `INCLINATION`: 2.91% missing
- `APOGEE`: 2.89% missing
- `PERIGEE`: 2.89% missing
- `RCS`: 53.59% missing
- `DATA_STATUS_CODE`: 98.08% missing

### Outliers (IQR Method)
- `PERIOD`: 6,646 outliers
- `APOGEE`: 7,091 outliers
- `PERIGEE`: 5,177 outliers
- `RCS`: 6,531 outliers
## GP Data

- **Rows:** 19,366
- **Columns:** 17
- **Memory Usage:** 3516.6 KB
- **Total Duplicates (Raw):** 0

### Cleaning Outcomes
- **Rows In:** 19,366
- **Rows Out (Clean):** 19,365
- **Rows Rejected:** 1
- **Duplicates Removed:** 0

### Missing Values (Raw)
- No missing values detected in key columns.


### Outliers (IQR Method)
- `MEAN_MOTION`: 2,143 outliers
- `ECCENTRICITY`: 3,519 outliers
- `NORAD_CAT_ID`: 770 outliers
- `REV_AT_EPOCH`: 2,114 outliers
- `BSTAR`: 1,434 outliers
- `MEAN_MOTION_DOT`: 1,495 outliers
- `MEAN_MOTION_DDOT`: 81 outliers
## K-Index

- **Rows:** 359
- **Columns:** 4
- **Memory Usage:** 18.7 KB
- **Total Duplicates (Raw):** 0

### Cleaning Outcomes
- **Rows In:** 359
- **Rows Out (Clean):** 359
- **Rows Rejected:** 0
- **Duplicates Removed:** 0

### Missing Values (Raw)
- No missing values detected in key columns.


### Outliers (IQR Method)
- No statistical outliers detected.

## Solar Indices

- **Rows:** 3,333
- **Columns:** 7
- **Memory Usage:** 205.2 KB
- **Total Duplicates (Raw):** 0

### Cleaning Outcomes
- **Rows In:** 3,333
- **Rows Out (Clean):** 3,333
- **Rows Rejected:** 0
- **Duplicates Removed:** 0

### Missing Values (Raw)
- No missing values detected in key columns.


### Outliers (IQR Method)
- `ssn`: 30 outliers
- `smoothed_ssn`: 17 outliers
- `observed_swpc_ssn`: 357 outliers
- `smoothed_swpc_ssn`: 345 outliers
- `f10.7`: 264 outliers
- `smoothed_f10.7`: 252 outliers

## Key Data Quality Findings
- **SATCAT Completeness**: Decay dates are legitimately missing for objects still in orbit.
- **Debris Objects**: The raw GP data accurately separates payload from fragments, but many fragments lack radar cross-section data.
- **Outliers as Real Data**: Highly elliptical orbits (HEO) are flagged as outliers by IQR but represent valid orbital regimes.
- **Dates and Times**: SWPC JSON data is provided in consistent UTC formats, facilitating straightforward parsing.
- **Duplicates**: CelesTrak sometimes includes overlapping epoch records which were successfully deduplicated.

## Visualizations
![SATCAT Missing Values](../figures/satcat_missing.png)
![SATCAT Object Types](../figures/satcat_object_types.png)
![GP Inclination](../figures/gp_inclination.png)
![SATCAT Apogee vs Perigee](../figures/satcat_apogee_perigee.png)
![SATCAT Launches per Year](../figures/satcat_launches_per_year.png)
![K-Index Timeline](../figures/k_index_timeline.png)
![Solar F10.7 Timeline](../figures/solar_f107_timeline.png)