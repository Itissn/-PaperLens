"""Machine-local model cache; environment override preserves container use."""
import os
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
CACHE = Path(os.environ.get("PAPERLENS_CACHE_DIR", str(ROOT / ".cache")))
