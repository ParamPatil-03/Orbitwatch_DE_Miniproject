"""
ORBITWATCH – src/orbitwatch/etl/cleaning.py
Reusable functions to clean, validate, and standardize raw space data.
Each function returns (clean_df, rejected_df, stats_dict).
"""

import pandas as pd
import numpy as np

def _normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Standardize column names to snake_case lowercase."""
    df.columns = (
        df.columns.str.strip()
        .str.lower()
        .str.replace(" ", "_")
        .str.replace("-", "_")
        .str.replace(".", "")
    )
    return df

def _flag_outliers_iqr(df: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    """Flag statistical outliers in numeric columns using IQR, adds 'is_outlier' column."""
    if "is_outlier" not in df.columns:
        df["is_outlier"] = False
        
    for col in columns:
        if col in df.columns and pd.api.types.is_numeric_dtype(df[col]):
            Q1 = df[col].quantile(0.25)
            Q3 = df[col].quantile(0.75)
            IQR = Q3 - Q1
            lower_bound = Q1 - 1.5 * IQR
            upper_bound = Q3 + 1.5 * IQR
            
            # Use bitwise OR to accumulate outlier flags
            outlier_mask = (df[col] < lower_bound) | (df[col] > upper_bound)
            df.loc[outlier_mask, "is_outlier"] = True
            
    return df

def clean_satcat(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    """Clean SATCAT data."""
    initial_count = len(df)
    
    # Standardize columns
    df = _normalize_columns(df)
    
    # Strip text fields and replace empty strings with NaN
    for col in df.select_dtypes(include=['object']).columns:
        df[col] = df[col].str.strip()
        df[col] = df[col].replace("", np.nan)
        
    numeric_cols = ["inclination", "apogee", "perigee", "period"]
    for col in numeric_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce')
            
    # Dates to UTC
    for date_col in ["launch_date", "decay_date"]:
        if date_col in df.columns:
            df[date_col] = pd.to_datetime(df[date_col], errors='coerce', utc=True)
            
    # Deduplicate on norad_cat_id keeping latest (if multiple rows present somehow)
    if "norad_cat_id" in df.columns:
        dups_before = len(df)
        df = df.drop_duplicates(subset=["norad_cat_id"], keep="last")
        duplicates_removed = dups_before - len(df)
    else:
        duplicates_removed = 0
        
    # Reject logic
    rejected_rows = []
    clean_rows = []
    
    # We'll build reason_code and reason_detail
    df["reason_code"] = ""
    df["reason_detail"] = ""
    
    now = pd.Timestamp.now(tz='UTC')
    for idx, row in df.iterrows():
        reasons = []
        details = []
        
        # Rule: norad_cat_id must not be null
        if pd.isna(row.get("norad_cat_id")):
            reasons.append("MISSING_NORAD_ID")
            details.append("NORAD_CAT_ID is null")
            
        # Rule: dates must not be in future
        if not pd.isna(row.get("launch_date")) and row["launch_date"] > now:
            reasons.append("FUTURE_LAUNCH_DATE")
            details.append("Launch date is in the future")
            
        if not pd.isna(row.get("decay_date")) and row["decay_date"] > now:
            reasons.append("FUTURE_DECAY_DATE")
            details.append("Decay date is in the future")
            
        # Rule: DECAY_DATE must not be earlier than LAUNCH_DATE
        if not pd.isna(row.get("decay_date")) and not pd.isna(row.get("launch_date")):
            if row["decay_date"] < row["launch_date"]:
                reasons.append("INVALID_DECAY_DATE")
                details.append("Decay date is before launch date")
                
        # Rule: INCLINATION between 0 and 180
        if not pd.isna(row.get("inclination")):
            if row["inclination"] < 0 or row["inclination"] > 180:
                reasons.append("INCLINATION_OUT_OF_RANGE")
                details.append(f"Inclination {row['inclination']} not between 0 and 180")
                
        # Rule: PERIGEE must not exceed APOGEE
        if not pd.isna(row.get("perigee")) and not pd.isna(row.get("apogee")):
            if row["perigee"] > row["apogee"]:
                reasons.append("PERIGEE_EXCEEDS_APOGEE")
                details.append("Perigee is greater than Apogee")
                
        if reasons:
            row["reason_code"] = reasons[0]
            row["reason_detail"] = " | ".join(details)
            rejected_rows.append(row)
        else:
            clean_rows.append(row)
            
    clean_df = pd.DataFrame(clean_rows) if clean_rows else pd.DataFrame(columns=df.columns)
    rejected_df = pd.DataFrame(rejected_rows) if rejected_rows else pd.DataFrame(columns=df.columns)
    
    # Drop rejection columns from clean_df
    if not clean_df.empty:
        clean_df = clean_df.drop(columns=["reason_code", "reason_detail"])
        
        # Outlier flag
        numeric_cols = ["inclination", "apogee", "perigee", "period"]
        clean_df = _flag_outliers_iqr(clean_df, numeric_cols)
        
        # Add orbit_regime
        # Thresholds: LEO (apogee < 2000), MEO (2000 <= apogee < 35500), GEO (35500 <= apogee <= 36000), HEO (apogee > 36000)
        def determine_regime(r):
            if pd.isna(r.get("apogee")) or pd.isna(r.get("perigee")):
                return "UNKNOWN"
            apo = r["apogee"]
            peri = r["perigee"]
            if apo < 2000:
                return "LEO"
            elif 35500 <= apo <= 36000 and 35500 <= peri <= 36000:
                return "GEO"
            elif 2000 <= apo < 35500:
                return "MEO"
            else:
                return "HEO"
                
        clean_df["orbit_regime"] = clean_df.apply(determine_regime, axis=1)

    stats = {
        "rows_in": initial_count,
        "rows_out": len(clean_df),
        "rows_rejected": len(rejected_df),
        "duplicates_removed": duplicates_removed
    }
    
    return clean_df, rejected_df, stats


def clean_gp(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    """Clean General Perturbation (GP) active and debris data."""
    initial_count = len(df)
    df = _normalize_columns(df)
    
    for col in df.select_dtypes(include=['object', 'string']).columns:
        df[col] = df[col].str.strip()
        df[col] = df[col].replace("", np.nan)
        
    if "epoch" in df.columns:
        df["epoch"] = pd.to_datetime(df["epoch"], errors='coerce', utc=True)
        
    numeric_cols = ["inclination", "eccentricity", "mean_motion"]
    for col in numeric_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce')
        
    # Deduplicate on norad_cat_id and epoch keeping latest
    if "norad_cat_id" in df.columns and "epoch" in df.columns:
        df = df.sort_values("epoch")
        dups_before = len(df)
        df = df.drop_duplicates(subset=["norad_cat_id", "epoch"], keep="last")
        duplicates_removed = dups_before - len(df)
    else:
        duplicates_removed = 0
        
    rejected_rows = []
    clean_rows = []
    
    df["reason_code"] = ""
    df["reason_detail"] = ""
    
    now = pd.Timestamp.now(tz='UTC')
    for idx, row in df.iterrows():
        reasons = []
        details = []
        
        if pd.isna(row.get("norad_cat_id")):
            reasons.append("MISSING_NORAD_ID")
            details.append("NORAD_CAT_ID is null")
            
        if not pd.isna(row.get("epoch")) and row["epoch"] > now:
            reasons.append("FUTURE_EPOCH")
            details.append("Epoch is in the future")
            
        if not pd.isna(row.get("inclination")):
            if row["inclination"] < 0 or row["inclination"] > 180:
                reasons.append("INCLINATION_OUT_OF_RANGE")
                details.append(f"Inclination {row['inclination']} not between 0 and 180")
                
        if not pd.isna(row.get("eccentricity")):
            if row["eccentricity"] < 0 or row["eccentricity"] >= 1:
                reasons.append("ECCENTRICITY_OUT_OF_RANGE")
                details.append("Eccentricity must be >= 0 and < 1")
                
        if not pd.isna(row.get("mean_motion")):
            if row["mean_motion"] <= 0:
                reasons.append("INVALID_MEAN_MOTION")
                details.append("Mean motion must be > 0")
                
        if reasons:
            row["reason_code"] = reasons[0]
            row["reason_detail"] = " | ".join(details)
            rejected_rows.append(row)
        else:
            clean_rows.append(row)
            
    clean_df = pd.DataFrame(clean_rows) if clean_rows else pd.DataFrame(columns=df.columns)
    rejected_df = pd.DataFrame(rejected_rows) if rejected_rows else pd.DataFrame(columns=df.columns)
    
    if not clean_df.empty:
        clean_df = clean_df.drop(columns=["reason_code", "reason_detail"])
        numeric_cols = ["inclination", "eccentricity", "mean_motion"]
        clean_df = _flag_outliers_iqr(clean_df, numeric_cols)
        
        def determine_regime_gp(r):
            if pd.isna(r.get("mean_motion")) or pd.isna(r.get("eccentricity")) or r["mean_motion"] <= 0:
                return "UNKNOWN"
            # Convert mean motion (revs/day) to radians/sec
            n_rad_s = r["mean_motion"] * 2 * np.pi / 86400
            mu = 398600.4418 # Earth's gravitational constant (km^3/s^2)
            # Semi-major axis in km
            a = (mu / (n_rad_s ** 2)) ** (1/3)
            # Earth's equatorial radius is ~6378.137 km
            apo = a * (1 + r["eccentricity"]) - 6378.137
            peri = a * (1 - r["eccentricity"]) - 6378.137
            
            if apo < 2000:
                return "LEO"
            elif 35500 <= apo <= 36000 and 35500 <= peri <= 36000:
                return "GEO"
            elif 2000 <= apo < 35500:
                return "MEO"
            else:
                return "HEO"
                
        clean_df["orbit_regime"] = clean_df.apply(determine_regime_gp, axis=1)

    stats = {
        "rows_in": initial_count,
        "rows_out": len(clean_df),
        "rows_rejected": len(rejected_df),
        "duplicates_removed": duplicates_removed
    }
    
    return clean_df, rejected_df, stats


def clean_k_index(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    """Clean NOAA Planetary K-index data."""
    initial_count = len(df)
    df = _normalize_columns(df)
    
    for col in df.select_dtypes(include=['object']).columns:
        df[col] = df[col].str.strip()
        df[col] = df[col].replace("", np.nan)
        
    if "time_tag" in df.columns:
        df["time_tag"] = pd.to_datetime(df["time_tag"], errors='coerce', utc=True)
        
    if "kp_index" in df.columns:
        df["kp_index"] = pd.to_numeric(df["kp_index"], errors='coerce')
        
    if "time_tag" in df.columns:
        dups_before = len(df)
        df = df.drop_duplicates(subset=["time_tag"], keep="last")
        duplicates_removed = dups_before - len(df)
    else:
        duplicates_removed = 0
        
    rejected_rows = []
    clean_rows = []
    
    df["reason_code"] = ""
    df["reason_detail"] = ""
    
    for idx, row in df.iterrows():
        reasons = []
        details = []
        
        now = pd.Timestamp.utcnow()
        if not pd.isna(row.get("time_tag")) and row["time_tag"] > now:
            reasons.append("FUTURE_TIME_TAG")
            details.append("Time tag is in the future")
            
        if not pd.isna(row.get("kp_index")):
            # K-index is typically 0 to 9
            if row["kp_index"] < 0 or row["kp_index"] > 9:
                reasons.append("K_INDEX_OUT_OF_RANGE")
                details.append("K-index must be between 0 and 9")
                
        if reasons:
            row["reason_code"] = reasons[0]
            row["reason_detail"] = " | ".join(details)
            rejected_rows.append(row)
        else:
            clean_rows.append(row)
            
    clean_df = pd.DataFrame(clean_rows) if clean_rows else pd.DataFrame(columns=df.columns)
    rejected_df = pd.DataFrame(rejected_rows) if rejected_rows else pd.DataFrame(columns=df.columns)
    
    if not clean_df.empty:
        clean_df = clean_df.drop(columns=["reason_code", "reason_detail"])
        clean_df = _flag_outliers_iqr(clean_df, ["kp_index"])
        
    stats = {
        "rows_in": initial_count,
        "rows_out": len(clean_df),
        "rows_rejected": len(rejected_df),
        "duplicates_removed": duplicates_removed
    }
    
    return clean_df, rejected_df, stats


def clean_solar_indices(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    """Clean NOAA Solar Indices data."""
    initial_count = len(df)
    df = _normalize_columns(df)
    
    for col in df.select_dtypes(include=['object']).columns:
        df[col] = df[col].str.strip()
        df[col] = df[col].replace("", np.nan)
        
    if "time_tag" in df.columns:
        df["time_tag"] = pd.to_datetime(df["time_tag"], errors='coerce', utc=True)
        
    numeric_columns = ["f107", "ssn", "sunspot"]
    for col in numeric_columns:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce')
            # NOAA encodes missing as -1
            df.loc[df[col] == -1, col] = np.nan
            
    if "time_tag" in df.columns:
        dups_before = len(df)
        df = df.drop_duplicates(subset=["time_tag"], keep="last")
        duplicates_removed = dups_before - len(df)
    else:
        duplicates_removed = 0
        
    rejected_rows = []
    clean_rows = []
    
    df["reason_code"] = ""
    df["reason_detail"] = ""
    
    now = pd.Timestamp.now(tz='UTC')
    for idx, row in df.iterrows():
        reasons = []
        details = []
        
        if not pd.isna(row.get("time_tag")) and row["time_tag"] > now:
            reasons.append("FUTURE_TIME_TAG")
            details.append("Time tag is in the future")
            
        if not pd.isna(row.get("f107")) and row["f107"] < 0:
            reasons.append("INVALID_F107")
            details.append("F10.7 must be non-negative")
            
        if not pd.isna(row.get("ssn")) and row["ssn"] < 0:
            reasons.append("INVALID_SSN")
            details.append("Sunspot number (ssn) must be non-negative")
            
        if reasons:
            row["reason_code"] = reasons[0]
            row["reason_detail"] = " | ".join(details)
            rejected_rows.append(row)
        else:
            clean_rows.append(row)
            
    clean_df = pd.DataFrame(clean_rows) if clean_rows else pd.DataFrame(columns=df.columns)
    rejected_df = pd.DataFrame(rejected_rows) if rejected_rows else pd.DataFrame(columns=df.columns)
    
    if not clean_df.empty:
        clean_df = clean_df.drop(columns=["reason_code", "reason_detail"])
        cols_to_check = [c for c in ["f107", "ssn"] if c in clean_df.columns]
        clean_df = _flag_outliers_iqr(clean_df, cols_to_check)
        
    stats = {
        "rows_in": initial_count,
        "rows_out": len(clean_df),
        "rows_rejected": len(rejected_df),
        "duplicates_removed": duplicates_removed
    }
    
    return clean_df, rejected_df, stats
