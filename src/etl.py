"""
etl.py — ETL pipeline for market microstructure CSV data.

Extracts raw SEC CSV files, transforms and validates each record via Pydantic,
and loads the results into a local SQLite database.

Usage:
    python etl.py
    python etl.py --data-dir /path/to/csv/folder
"""

import argparse
import logging
import pathlib
import sqlite3
from typing import List

import numpy as np
import pandas as pd
import pyarrow.csv as pv
import requests
from pydantic import ValidationError

from config import DATA_DIR, DB_NAME
from schemas import MarketMetricSchema

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


class ETLPipeline:
    """
    Orchestrates the full Extract → Transform → Validate → Load cycle
    for market microstructure CSV files into SQLite.
    """

    def __init__(self, db_path: str = DB_NAME) -> None:
        self.db_path = db_path
        self.conn = sqlite3.connect(self.db_path)
        self.us_holidays: List[str] = self._fetch_trading_holidays()
        self._setup_database()

    def _setup_database(self) -> None:
        """
        Creates the market_metrics table if it does not already exist.
        Uses CREATE TABLE IF NOT EXISTS — never destroys existing data.
        """
        cursor = self.conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS market_metrics (
                trade_date       TEXT    NOT NULL,
                asset_class      TEXT    NOT NULL,
                metric_name      TEXT    NOT NULL,
                sort_variable    TEXT    NOT NULL,
                quantile_type    TEXT    NOT NULL,
                quantile_bucket  INTEGER NOT NULL,
                metric_value     REAL    NOT NULL,
                log_metric_value REAL    NOT NULL
            )
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_metric_asset
            ON market_metrics (metric_name, asset_class)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_sort_bucket
            ON market_metrics (sort_variable, quantile_bucket)
        """)
        self.conn.commit()
        logger.info("Database schema verified at: %s", self.db_path)

    def _fetch_trading_holidays(self) -> List[str]:
        """
        Fetches US public holidays from a free public API.
        Returns an empty list gracefully if the request fails.
        """
        url = "https://date.nager.at/api/v3/PublicHolidays/2025/US"
        try:
            response = requests.get(url, timeout=5)
            response.raise_for_status()
            holidays = [day["date"] for day in response.json()]
            logger.info("Fetched %d US trading holidays.", len(holidays))
            return holidays
        except requests.RequestException as exc:
            logger.warning("Holiday API unavailable (%s). Proceeding without holiday data.", exc)
            return []

    def process_file(self, file_path: pathlib.Path) -> int:
        """
        Processes a single CSV file through the full ETL cycle.

        Args:
            file_path: Path to the CSV file to process.

        Returns:
            Number of rows successfully loaded, or 0 on validation failure.
        """
        logger.info("Processing: %s", file_path.name)

        # --- EXTRACT ---
        arrow_table = pv.read_csv(file_path)
        df = arrow_table.to_pandas()

        # Derive metadata from filename convention: {quantile_type}_{metric_name}_{asset_class}.csv
        stem_parts = file_path.stem.split("_")
        quantile_type = stem_parts[0]
        asset_class = stem_parts[-1]
        metric_name = "_".join(stem_parts[1:-1])

        # --- TRANSFORM ---
        df["Date"] = df["Date"].astype(str)
        melted = pd.melt(df, id_vars=["Date"], var_name="raw_col", value_name="metric_value")

        regex_pattern = rf"(.*?)\s+{quantile_type.capitalize()}(\d+)"
        extracted = melted["raw_col"].str.extract(regex_pattern)
        melted["sort_variable"] = extracted[0].str.strip()
        melted["quantile_bucket"] = extracted[1].astype(float)  # float to handle NaNs before cast

        final_df = melted.dropna(subset=["sort_variable", "metric_value"]).copy()
        final_df["quantile_bucket"] = final_df["quantile_bucket"].astype(int)
        final_df["log_metric_value"] = np.log1p(final_df["metric_value"])
        final_df = final_df.rename(columns={"Date": "trade_date"})
        final_df["asset_class"] = asset_class
        final_df["metric_name"] = metric_name
        final_df["quantile_type"] = quantile_type

        columns_to_keep = list(MarketMetricSchema.model_fields.keys())
        final_df = final_df[columns_to_keep]

        # --- VALIDATE ---
        sample = final_df.iloc[0].to_dict()
        try:
            MarketMetricSchema(**sample)
            logger.info("  Pydantic validation: PASS")
        except ValidationError as exc:
            logger.error("  Pydantic validation: FAIL\n%s", exc)
            return 0

        # --- LOAD ---
        final_df.to_sql("market_metrics", self.conn, if_exists="append", index=False)
        logger.info("  Loaded %d rows into SQLite.", len(final_df))
        return len(final_df)

    def process_directory(self, data_dir: pathlib.Path) -> None:
        """
        Processes all CSV files found in a directory.

        Args:
            data_dir: Directory containing raw CSV files.
        """
        if not data_dir.exists():
            logger.error("Data directory not found: %s", data_dir)
            return

        csv_files = sorted(f for f in data_dir.iterdir() if f.is_file() and f.suffix.lower() == ".csv")
        if not csv_files:
            logger.warning("No CSV files found in: %s", data_dir)
            return

        logger.info("Found %d CSV files to process.", len(csv_files))
        total_rows = 0
        for file in csv_files:
            total_rows += self.process_file(file)

        logger.info("ETL complete. Total rows loaded: %d", total_rows)

    def close(self) -> None:
        """Closes the database connection."""
        self.conn.close()
        logger.info("Database connection closed.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the market microstructure ETL pipeline.")
    parser.add_argument(
        "--data-dir",
        type=pathlib.Path,
        default=DATA_DIR,
        help="Path to the directory containing raw CSV files.",
    )
    args = parser.parse_args()

    pipeline = ETLPipeline()
    try:
        pipeline.process_directory(args.data_dir)
    finally:
        pipeline.close()


if __name__ == "__main__":
    main()