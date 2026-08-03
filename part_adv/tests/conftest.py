from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0,str(ROOT))
PROJECT=ROOT.parent
if str(PROJECT) not in sys.path:
    sys.path.insert(0,str(PROJECT))
