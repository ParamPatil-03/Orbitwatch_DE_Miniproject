"""
ORBITWATCH – src/orbitwatch/validation/profile_data.py
Profiles raw data, detecting anomalies and generating charts.
"""

import argparse
import json
import logging
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd
import seaborn as sns

from orbitwatch.common.logging_setup import get_logger

logger = get_logger("profile_data")

def profile_dataset(df: pd.DataFrame, name: str, out_dir: Path) -> dict:
    """Generate a profile dictionary and plots for a given dataframe."""
    profile = {
        "name": name,
        "shape": df.shape,
        "memory_kb": float(df.memory_usage(deep=True).sum() / 1024),
        "columns": df.columns.tolist(),
        "dtypes": df.dtypes.astype(str).to_dict(),
        "missing_pct": (df.isnull().sum() / len(df) * 100).to_dict(),
        "duplicates": int(df.duplicated().sum()),
        "summary_stats": {},
        "categorical_counts": {},
        "outlier_counts": {}
    }
    
    # Numeric summary
    numeric_df = df.select_dtypes(include=["number"])
    if not numeric_df.empty:
        # Convert desc to dict
        desc = numeric_df.describe().to_dict()
        profile["summary_stats"] = desc
        
        # Outliers (IQR)
        for col in numeric_df.columns:
            Q1 = numeric_df[col].quantile(0.25)
            Q3 = numeric_df[col].quantile(0.75)
            IQR = Q3 - Q1
            outliers = numeric_df[(numeric_df[col] < Q1 - 1.5 * IQR) | (numeric_df[col] > Q3 + 1.5 * IQR)]
            profile["outlier_counts"][col] = len(outliers)

    # Categorical summary for key cols
    cat_cols = ["OBJECT_TYPE", "OPS_STATUS_CODE", "OWNER", "ORBIT_TYPE"]
    for c in cat_cols:
        if c in df.columns:
            profile["categorical_counts"][c] = df[c].value_counts().to_dict()

    return profile

def generate_charts(satcat: pd.DataFrame, gp: pd.DataFrame, k_index: pd.DataFrame, solar: pd.DataFrame, fig_dir: Path):
    """Generate PNG charts for the data profile."""
    fig_dir.mkdir(parents=True, exist_ok=True)
    sns.set_theme(style="whitegrid")
    
    # 1. Missing values per column (bar chart) for SATCAT.
    plt.figure(figsize=(10, 6))
    missing = satcat.isnull().sum()
    missing = missing[missing > 0]
    if not missing.empty:
        missing.plot(kind="bar", color="coral")
        plt.title("SATCAT: Missing Values per Column")
        plt.ylabel("Count")
        plt.tight_layout()
        plt.savefig(fig_dir / "satcat_missing.png")
    plt.close()

    # 2. Object type distribution
    if "OBJECT_TYPE" in satcat.columns:
        plt.figure(figsize=(8, 5))
        sns.countplot(data=satcat, y="OBJECT_TYPE", order=satcat["OBJECT_TYPE"].value_counts().index, hue="OBJECT_TYPE", palette="viridis", legend=False)
        plt.title("SATCAT: Object Type Distribution")
        plt.xlabel("Count")
        plt.tight_layout()
        plt.savefig(fig_dir / "satcat_object_types.png")
        plt.close()

    # 3. Inclination distribution histogram for the GP data
    if "INCLINATION" in gp.columns:
        plt.figure(figsize=(8, 5))
        sns.histplot(gp["INCLINATION"], bins=50, kde=True, color="skyblue")
        plt.title("GP: Inclination Distribution")
        plt.xlabel("Inclination (degrees)")
        plt.tight_layout()
        plt.savefig(fig_dir / "gp_inclination.png")
        plt.close()

    # 4. Apogee vs perigee scatter plot for SATCAT
    if "APOGEE" in satcat.columns and "PERIGEE" in satcat.columns:
        plt.figure(figsize=(8, 6))
        sns.scatterplot(data=satcat, x="PERIGEE", y="APOGEE", alpha=0.3, s=10)
        plt.xscale("log")
        plt.yscale("log")
        plt.title("SATCAT: Apogee vs Perigee")
        plt.plot([1, 1000000], [1, 1000000], "r--", label="Apogee = Perigee")
        plt.legend()
        plt.tight_layout()
        plt.savefig(fig_dir / "satcat_apogee_perigee.png")
        plt.close()

    # 5. Objects launched per year
    if "LAUNCH_DATE" in satcat.columns:
        satcat["LAUNCH_YEAR"] = pd.to_datetime(satcat["LAUNCH_DATE"], errors="coerce").dt.year
        plt.figure(figsize=(10, 5))
        counts = satcat["LAUNCH_YEAR"].value_counts().sort_index()
        counts.plot(kind="line", marker=".", color="green")
        plt.title("SATCAT: Objects Launched per Year")
        plt.ylabel("Count")
        plt.tight_layout()
        plt.savefig(fig_dir / "satcat_launches_per_year.png")
        plt.close()

    # 6. K-index over time and F10.7 over time
    if "time_tag" in k_index.columns and "kp_index" in k_index.columns:
        plt.figure(figsize=(10, 3))
        # Ensure time_tag is datetime
        k_index["time_tag"] = pd.to_datetime(k_index["time_tag"])
        sns.lineplot(data=k_index, x="time_tag", y="kp_index", color="purple")
        plt.title("Planetary K-Index over Time")
        plt.tight_layout()
        plt.savefig(fig_dir / "k_index_timeline.png")
        plt.close()

    if "time-tag" in solar.columns and "f10.7" in solar.columns:
        plt.figure(figsize=(10, 3))
        solar["time-tag"] = pd.to_datetime(solar["time-tag"])
        sns.lineplot(data=solar, x="time-tag", y="f10.7", color="orange")
        plt.title("Observed F10.7 over Time")
        plt.tight_layout()
        plt.savefig(fig_dir / "solar_f107_timeline.png")
        plt.close()

def main():
    parser = argparse.ArgumentParser(description="Profile raw data and generate charts")
    parser.parse_args()
    
    project_root = Path(__file__).resolve().parent.parent.parent.parent
    raw_dir = project_root / "data" / "raw"
    fig_dir = project_root / "docs" / "figures"
    
    logger.info("Loading raw data for profiling...")
    satcat_files = list(raw_dir.glob("satcat_*.csv"))
    gp_files = list(raw_dir.glob("gp_*.csv"))
    k_index_files = list(raw_dir.glob("k_index_*.json"))
    solar_files = list(raw_dir.glob("solar_indices_*.json"))
    
    satcat = pd.read_csv(max(satcat_files)) if satcat_files else pd.DataFrame()
    
    gp_dfs = [pd.read_csv(f) for f in gp_files]
    gp = pd.concat(gp_dfs, ignore_index=True) if gp_dfs else pd.DataFrame()
    
    k_index = pd.read_json(max(k_index_files)) if k_index_files else pd.DataFrame()
    solar = pd.read_json(max(solar_files)) if solar_files else pd.DataFrame()
    
    logger.info("Generating data profiles...")
    profiles = {
        "satcat": profile_dataset(satcat, "SATCAT", fig_dir),
        "gp": profile_dataset(gp, "GP Data", fig_dir),
        "k_index": profile_dataset(k_index, "K-Index", fig_dir),
        "solar_indices": profile_dataset(solar, "Solar Indices", fig_dir)
    }
    
    logger.info("Generating charts...")
    generate_charts(satcat, gp, k_index, solar, fig_dir)
    
    logger.info("Profiling complete.")
    return profiles

if __name__ == "__main__":
    main()
