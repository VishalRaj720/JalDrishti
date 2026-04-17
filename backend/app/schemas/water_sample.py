"""WaterSample Pydantic schemas."""
import uuid
from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, Field


class WaterSampleBase(BaseModel):
    sampled_at: datetime
    # Physical
    ph: Optional[float] = None
    ec_us_cm: Optional[float] = None
    tds_mg_l: Optional[float] = None
    tds_derived: bool = False
    turbidity_ntu: Optional[float] = None
    do_mg_l: Optional[float] = None
    total_hardness: Optional[float] = None
    # Chemistry
    uranium_ppb: Optional[float] = None
    nitrate_mg_l: Optional[float] = None
    fluoride_mg_l: Optional[float] = None
    arsenic_ppb: Optional[float] = None
    iron_ppm: Optional[float] = None
    chloride_mg_l: Optional[float] = None
    sulphate_mg_l: Optional[float] = None
    bicarbonate_mg_l: Optional[float] = None
    carbonate_mg_l: Optional[float] = None
    phosphate_mg_l: Optional[float] = None
    calcium_mg_l: Optional[float] = None
    magnesium_mg_l: Optional[float] = None
    sodium_mg_l: Optional[float] = None
    potassium_mg_l: Optional[float] = None


class WaterSampleCreate(WaterSampleBase):
    well_id: uuid.UUID


class WaterSampleBulkCreate(BaseModel):
    well_id: uuid.UUID
    samples: List[WaterSampleBase] = Field(..., min_length=1, max_length=1000)


class WaterSampleResponse(WaterSampleBase):
    id: uuid.UUID
    well_id: uuid.UUID
    source_id: Optional[uuid.UUID] = None
    created_at: datetime

    model_config = {"from_attributes": True}
