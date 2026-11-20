"""Download Maia-3 model weights using its official cache utility."""
from pathlib import Path
import os
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "vendor" / "maia3"))
os.environ.setdefault("HF_HOME", str(ROOT / "data" / "maia-cache"))
os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")

from maia3.cache import main  # noqa: E402

main()
