"""
schemas.py — Pydantic data contracts for the market metrics pipeline.
All data must conform to this schema before insertion into the database.
"""

from pydantic import BaseModel, field_validator


class MarketMetricSchema(BaseModel):
    """Strict schema enforced on every row prior to database insertion."""

    trade_date: str
    asset_class: str
    metric_name: str
    sort_variable: str
    quantile_type: str
    quantile_bucket: int
    metric_value: float
    log_metric_value: float

    @field_validator("asset_class")
    @classmethod
    def asset_class_must_be_valid(cls, v: str) -> str:
        allowed = {"stock", "etp"}
        if v.lower() not in allowed:
            raise ValueError(f"asset_class must be one of {allowed}, got '{v}'")
        return v.lower()

    @field_validator("quantile_bucket")
    @classmethod
    def bucket_must_be_positive(cls, v: int) -> int:
        if v < 1:
            raise ValueError(f"quantile_bucket must be >= 1, got {v}")
        return v