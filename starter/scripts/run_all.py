"""Convenience entrypoint to run the full pipeline from the repository root."""

from __future__ import annotations

import sys
from pathlib import Path

STARTER_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(STARTER_DIR))

from src.run import main

if __name__ == "__main__":
    main()
