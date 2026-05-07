"""
config.py — Central configuration for the Market Microstructure Dashboard.
All environment variables and paths are resolved here. No other file should
call load_dotenv() or hardcode paths.
"""

import pathlib
import os
from dotenv import load_dotenv

load_dotenv()

# --- API Credentials ---
HF_TOKEN: str = os.getenv("HF_TOKEN", "")

# --- Paths ---
# BASE_DIR resolves to the project root regardless of where the script is called from
BASE_DIR: pathlib.Path = pathlib.Path(__file__).parent.resolve()
DATA_DIR: pathlib.Path = pathlib.Path(os.getenv("DATA_DIR", str(BASE_DIR / "data")))
DB_NAME: str = os.getenv("DB_NAME", str(BASE_DIR / "advanced_microstructure.db"))

# --- Validation ---
if not HF_TOKEN:
    import warnings
    warnings.warn(
        "HF_TOKEN is not set in your .env file. AI chat responses will be unavailable.",
        stacklevel=2,
    )