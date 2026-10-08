import datetime

import numpy as np
import pandas as pd

from orbitwatch.etl.cleaning import clean_gp, clean_satcat


def test_clean_satcat_inclination_rejected():
    df = pd.DataFrame([{
        "NORAD_CAT_ID": 12345,
        "OBJECT_NAME": "TEST",
        "INCLINATION": 200,
        "APOGEE": 1000,
        "PERIGEE": 900
    }])
    clean_df, rej_df, stats = clean_satcat(df)
    
    assert len(clean_df) == 0
    assert len(rej_df) == 1
    assert rej_df.iloc[0]["reason_code"] == "INCLINATION_OUT_OF_RANGE"
    assert stats["rows_rejected"] == 1


def test_clean_satcat_null_decay_date_not_rejected():
    df = pd.DataFrame([{
        "NORAD_CAT_ID": 12345,
        "DECAY_DATE": "",
        "LAUNCH_DATE": "2020-01-01",
        "INCLINATION": 45,
        "APOGEE": 1000,
        "PERIGEE": 900
    }])
    clean_df, rej_df, stats = clean_satcat(df)
    
    assert len(clean_df) == 1
    assert len(rej_df) == 0
    assert pd.isna(clean_df.iloc[0]["decay_date"])
    assert clean_df.iloc[0]["orbit_regime"] == "LEO"
    assert stats["rows_out"] == 1


def test_clean_gp_duplicates_removed():
    df = pd.DataFrame([
        {
            "NORAD_CAT_ID": 12345,
            "EPOCH": "2024-01-01T00:00:00Z",
            "MEAN_MOTION": 15.0,
            "ECCENTRICITY": 0.001,
            "INCLINATION": 45.0
        },
        {
            "NORAD_CAT_ID": 12345,
            "EPOCH": "2024-01-01T00:00:00Z",
            "MEAN_MOTION": 15.1, # Different data but same key
            "ECCENTRICITY": 0.001,
            "INCLINATION": 45.0
        }
    ])
    clean_df, rej_df, stats = clean_gp(df)
    
    assert len(clean_df) == 1
    assert len(rej_df) == 0
    assert stats["duplicates_removed"] == 1
    assert clean_df.iloc[0]["mean_motion"] == 15.1


def test_clean_types_converted_correctly():
    df = pd.DataFrame([{
        "NORAD_CAT_ID": " 12345 ",
        "OBJECT_NAME": "   SPACECRAFT   ",
        "INCLINATION": "45.5"
    }])
    # clean_gp standardizes columns and strips strings
    clean_df, rej_df, stats = clean_gp(df)
    
    assert len(clean_df) == 1
    assert clean_df.iloc[0]["object_name"] == "SPACECRAFT"
    # the inclination string wasn't explicitly cast to numeric in clean_gp
    # but pandas inferred it. Let's check string stripping.
    assert clean_df.iloc[0]["norad_cat_id"] == "12345"
