"""Streamlit Cloud entrypoint for the Indian Auto Monthly Monitor."""

import sys
from pathlib import Path

APP_ROOT = Path(__file__).parent / "auto_intel_platform" / "auto_intel"
sys.path.insert(0, str(APP_ROOT))

from dashboard.app import main


if __name__ == "__main__":
    main()
