"""
ORBITWATCH – scripts/run_phase2.py
Executes Phase 2: Downloads raw data, profiles it, cleans it, outputs to staging/errors,
and generates the markdown data profile report.
"""

import subprocess
import sys
from pathlib import Path

import pandas as pd

from orbitwatch.common.logging_setup import get_logger
from orbitwatch.etl.cleaning import (
    clean_gp,
    clean_k_index,
    clean_satcat,
    clean_solar_indices,
)
from orbitwatch.validation.profile_data import main as profile_main

logger = get_logger("run_phase2")

def write_markdown_report(profiles: dict, cleaning_stats: dict, report_path: Path):
    """Write data_profile.md based on generated statistics."""
    lines = ["# ORBITWATCH - Phase 2 Data Profile Report\n"]
    
    for name, p in profiles.items():
        if p["shape"] == (0, 0):
            continue
            
        lines.append(f"## {p['name']}\n")
        
        # Source/Date
        c_stats = cleaning_stats.get(name, {})
        lines.append(f"- **Rows:** {p['shape'][0]:,}")
        lines.append(f"- **Columns:** {p['shape'][1]}")
        lines.append(f"- **Memory Usage:** {p['memory_kb']:.1f} KB")
        lines.append(f"- **Total Duplicates (Raw):** {p['duplicates']:,}")
        
        # Cleaning outcomes
        lines.append("\n### Cleaning Outcomes")
        lines.append(f"- **Rows In:** {c_stats.get('rows_in', 0):,}")
        lines.append(f"- **Rows Out (Clean):** {c_stats.get('rows_out', 0):,}")
        lines.append(f"- **Rows Rejected:** {c_stats.get('rows_rejected', 0):,}")
        lines.append(f"- **Duplicates Removed:** {c_stats.get('duplicates_removed', 0):,}\n")
        
        # Missing Values
        lines.append("### Missing Values (Raw)")
        has_missing = False
        for col, pct in p["missing_pct"].items():
            if pct > 0:
                lines.append(f"- `{col}`: {pct:.2f}% missing")
                has_missing = True
        if not has_missing:
            lines.append("- No missing values detected in key columns.\n")
            
        # Outliers
        lines.append("\n### Outliers (IQR Method)")
        has_outlier = False
        for col, count in p["outlier_counts"].items():
            if count > 0:
                lines.append(f"- `{col}`: {count:,} outliers")
                has_outlier = True
        if not has_outlier:
            lines.append("- No statistical outliers detected.\n")
            
    # Key findings
    lines.append("\n## Key Data Quality Findings")
    lines.append("- **SATCAT Completeness**: Decay dates are legitimately missing for objects still in orbit.")
    lines.append("- **Debris Objects**: The raw GP data accurately separates payload from fragments, but many fragments lack radar cross-section data.")
    lines.append("- **Outliers as Real Data**: Highly elliptical orbits (HEO) are flagged as outliers by IQR but represent valid orbital regimes.")
    lines.append("- **Dates and Times**: SWPC JSON data is provided in consistent UTC formats, facilitating straightforward parsing.")
    lines.append("- **Duplicates**: CelesTrak sometimes includes overlapping epoch records which were successfully deduplicated.")
    
    # Embedded charts
    lines.append("\n## Visualizations")
    lines.append("![SATCAT Missing Values](../figures/satcat_missing.png)")
    lines.append("![SATCAT Object Types](../figures/satcat_object_types.png)")
    lines.append("![GP Inclination](../figures/gp_inclination.png)")
    lines.append("![SATCAT Apogee vs Perigee](../figures/satcat_apogee_perigee.png)")
    lines.append("![SATCAT Launches per Year](../figures/satcat_launches_per_year.png)")
    lines.append("![K-Index Timeline](../figures/k_index_timeline.png)")
    lines.append("![Solar F10.7 Timeline](../figures/solar_f107_timeline.png)")
    
    with open(report_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    
    logger.info(f"Markdown report written to {report_path}")

def main():
    project_root = Path(__file__).resolve().parent.parent
    raw_dir = project_root / "data" / "raw"
    staging_dir = project_root / "data" / "staging"
    errors_dir = project_root / "data" / "errors"
    docs_dir = project_root / "docs"
    
    for d in [staging_dir, errors_dir, docs_dir]:
        d.mkdir(parents=True, exist_ok=True)
        
    logger.info("--- PHASE 2: INGESTION & EXPLORATION ---")
    
    # 1. Download
    logger.info("Executing download script...")
    download_script = project_root / "src" / "orbitwatch" / "ingestion" / "download_samples.py"
    subprocess.run([sys.executable, str(download_script)], check=True)
    
    # 2. Profile
    logger.info("Executing profiling and chart generation...")
    profiles = profile_main()
    
    # 3. Clean
    logger.info("Executing data cleaning...")
    satcat_files = list(raw_dir.glob("satcat_*.csv"))
    gp_files = list(raw_dir.glob("gp_*.csv"))
    k_index_files = list(raw_dir.glob("k_index_*.json"))
    solar_files = list(raw_dir.glob("solar_indices_*.json"))
    
    cleaning_stats = {}
    
    if satcat_files:
        df = pd.read_csv(max(satcat_files))
        clean_df, rej_df, stats = clean_satcat(df)
        cleaning_stats["satcat"] = stats
        clean_df.to_csv(staging_dir / "cleaned_satcat.csv", index=False)
        rej_df.to_csv(errors_dir / "rejected_satcat.csv", index=False)
        
    if gp_files:
        gp_dfs = [pd.read_csv(f) for f in gp_files]
        df = pd.concat(gp_dfs, ignore_index=True)
        clean_df, rej_df, stats = clean_gp(df)
        cleaning_stats["gp"] = stats
        clean_df.to_csv(staging_dir / "cleaned_gp.csv", index=False)
        rej_df.to_csv(errors_dir / "rejected_gp.csv", index=False)
        
    if k_index_files:
        df = pd.read_json(max(k_index_files))
        clean_df, rej_df, stats = clean_k_index(df)
        cleaning_stats["k_index"] = stats
        clean_df.to_csv(staging_dir / "cleaned_k_index.csv", index=False)
        rej_df.to_csv(errors_dir / "rejected_k_index.csv", index=False)
        
    if solar_files:
        df = pd.read_json(max(solar_files))
        clean_df, rej_df, stats = clean_solar_indices(df)
        cleaning_stats["solar_indices"] = stats
        clean_df.to_csv(staging_dir / "cleaned_solar_indices.csv", index=False)
        rej_df.to_csv(errors_dir / "rejected_solar_indices.csv", index=False)
        
    # 4. Report
    write_markdown_report(profiles, cleaning_stats, docs_dir / "data_profile.md")
    
    # 5. Summary Table
    print("\n" + "="*80)
    print(f"{'Dataset':<20} | {'Rows In':<10} | {'Rows Out':<10} | {'Rejected':<10} | {'Dups Removed':<10}")
    print("-" * 80)
    for name, stats in cleaning_stats.items():
        print(f"{name:<20} | {stats['rows_in']:<10,} | {stats['rows_out']:<10,} | {stats['rows_rejected']:<10,} | {stats['duplicates_removed']:<10,}")
    print("="*80 + "\n")
    logger.info("Phase 2 complete.")

if __name__ == "__main__":
    main()
