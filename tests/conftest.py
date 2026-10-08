import sys
import os
from pathlib import Path

# Add src/ to the Python path for testing
src_path = str((Path(__file__).parent.parent / "src").resolve())
if src_path not in sys.path:
    sys.path.insert(0, src_path)
    
root_path = str((Path(__file__).parent.parent).resolve())
if root_path not in sys.path:
    sys.path.insert(0, root_path)
