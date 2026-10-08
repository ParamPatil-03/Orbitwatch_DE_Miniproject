"""
Pydantic models for the FastAPI ingestion service.
We use lenient validation: only the natural keys are explicitly required.
Any other fields are retained in the payload using model_config extra='allow'.
"""

from typing import Any
from pydantic import BaseModel, Field

class BasePayload(BaseModel):
    """Base model for payloads allowing any extra fields."""
    model_config = {"extra": "allow"}

class SatcatPayload(BasePayload):
    NORAD_CAT_ID: Any = Field(..., description="Natural key for SATCAT")

class GPPayload(BasePayload):
    NORAD_CAT_ID: Any = Field(..., description="Part 1 of GP natural key")
    EPOCH: Any = Field(..., description="Part 2 of GP natural key")

class KIndexPayload(BasePayload):
    time_tag: Any = Field(..., description="Natural key for K-index")

class SolarIndicesPayload(BasePayload):
    time_tag: Any = Field(..., alias="time-tag", description="Natural key for Solar Indices")

class IngestResponse(BaseModel):
    batch_id: str
    received: int
    inserted: int
    duplicates: int
    rejected: int
