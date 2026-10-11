import sys
from pathlib import Path
sys.path.insert(0, str((Path(__file__).parent.parent).resolve()))
sys.path.insert(0, str((Path(__file__).parent.parent / "src").resolve()))
from config.settings import get_settings
from orbitwatch.common.db import get_mongo_client

def peek():
    settings = get_settings()
    client = get_mongo_client()
    db = client[settings.mongo_db]
    
    for coll_name in ["raw_gp", "raw_k_index", "raw_solar_indices"]:
        print(f"--- {coll_name} ---")
        doc = db[coll_name].find_one()
        if doc:
            print(doc.keys())
            # print a few specific keys if present
            for k in ["NORAD_CAT_ID", "time_tag"]:
                if k in doc:
                    print(f"{k}: {doc[k]}")
        else:
            print("Empty collection")

if __name__ == "__main__":
    peek()
