#!/usr/bin/env python3
"""
ORBITWATCH Phase 4 - Apply SQL migration using admin user.
"""
import sys
from pathlib import Path
sys.path.insert(0, str((Path(__file__).parent.parent).resolve()))
from sqlalchemy import create_engine, text
from config.settings import get_settings

def main():
    if len(sys.argv) < 2:
        print("Usage: python apply_sql.py <path_to_sql_file>")
        sys.exit(1)
        
    sql_file = Path(sys.argv[1])
    if not sql_file.exists():
        print(f"File not found: {sql_file}")
        sys.exit(1)
        
    settings = get_settings()
    engine = create_engine(settings.admin_postgres_url)
    
    with engine.begin() as conn:
        print(f"Applying {sql_file}...")
        sql_text = sql_file.read_text(encoding="utf-8")
        conn.execute(text(sql_text))
        
    print("SQL applied successfully.")
    
    # Check grants for etl_user on staging tables
    with engine.begin() as conn:
        res = conn.execute(text("""
            SELECT table_name, privilege_type 
            FROM information_schema.role_table_grants 
            WHERE grantee = 'etl_user' AND table_schema = 'staging';
        """)).fetchall()
        print("Grants for etl_user on staging tables:")
        for r in res:
            print(f"  {r[0]}: {r[1]}")

        res2 = conn.execute(text("""
            SELECT table_name, privilege_type 
            FROM information_schema.role_table_grants 
            WHERE grantee = 'dashboard_user' AND table_schema = 'staging';
        """)).fetchall()
        print("Grants for dashboard_user on staging tables (expected none):")
        for r in res2:
            print(f"  {r[0]}: {r[1]}")

if __name__ == "__main__":
    main()
