"""
run_dashboard.py — Launch script for the Market Microstructure AI Dashboard.

Performs pre-flight checks before starting the Streamlit server:
  - Verifies app.py is present
  - Warns if the database has not yet been built (run etl.py first)
  - Warns if HF_TOKEN is missing from the environment

Usage:
    python run_dashboard.py
"""

import os
import pathlib
import subprocess
import sys

from dotenv import load_dotenv

load_dotenv()


def main() -> None:
    root_dir = pathlib.Path(__file__).parent.resolve()
    app_path = root_dir / "app.py"
    db_path = root_dir / "advanced_microstructure.db"

    print("🚀 Initializing Market Microstructure AI Dashboard...")
    print("-" * 50)

    # --- Pre-flight checks ---
    checks_passed = True

    if not app_path.exists():
        print(f"❌ Error: app.py not found in {root_dir}")
        print("   Please ensure app.py is in the same directory as this script.")
        checks_passed = False

    if not db_path.exists():
        print("⚠️  Warning: 'advanced_microstructure.db' not found.")
        print("   Run the ETL pipeline first:  python etl.py")

    if not os.getenv("HF_TOKEN"):
        print("⚠️  Warning: HF_TOKEN not set in your .env file.")
        print("   The dashboard will open, but AI chat responses will be unavailable.")
        print("   Add this to a .env file in this directory:  HF_TOKEN=hf_xxxx")

    if not checks_passed:
        sys.exit(1)

    print("-" * 50)
    print("✅ Pre-flight checks complete. Launching Streamlit server...")
    print("🌐 Opening at: http://localhost:8501")
    print("   Press Ctrl+C to stop the server.")
    print("-" * 50)

    try:
        subprocess.run(
            [sys.executable, "-m", "streamlit", "run", str(app_path)],
            check=True,
        )
    except KeyboardInterrupt:
        print("\n🛑 Dashboard stopped. See you next time!")
    except subprocess.CalledProcessError as exc:
        print(f"❌ Streamlit exited with an error (code {exc.returncode}).")
        sys.exit(exc.returncode)
    except Exception as exc:
        print(f"❌ Failed to launch dashboard: {exc}")
        sys.exit(1)


if __name__ == "__main__":
    main()