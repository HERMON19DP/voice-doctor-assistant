
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class AppointmentCreate(BaseModel):
    doctor_id: int
    slot_id: int
    phone_number: str = Field(
        min_length=7,
        max_length=20,
        pattern=r"^\+?[0-9][0-9\s-]{5,18}[0-9]$",
    )


class AppointmentResponse(BaseModel):
    id: int
    doctor_id: int
    slot_id: int
    phone_number: str
    status: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class AppointmentCancel(BaseModel):
    phone_number: str = Field(
        min_length=7,
        max_length=20,
        pattern=r"^\+?[0-9][0-9\s-]{5,18}[0-9]$",
    )
