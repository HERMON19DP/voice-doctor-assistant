from datetime import datetime

from pydantic import BaseModel, ConfigDict


class DoctorResponse(BaseModel):
    id: int
    name: str
    specialty: str
    experience: int
    is_active: bool

    model_config = ConfigDict(from_attributes=True)


class SlotResponse(BaseModel):
    id: int
    doctor_id: int
    start_time: datetime
    end_time: datetime
    is_available: bool

    model_config = ConfigDict(from_attributes=True)
