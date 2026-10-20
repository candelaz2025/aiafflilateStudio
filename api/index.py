import os
import sys
from pathlib import Path

# Add project root to sys.path so auto_studio can be imported cleanly
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Ensure VERCEL environment flag is set
os.environ["VERCEL"] = "1"

from auto_studio.api import app
