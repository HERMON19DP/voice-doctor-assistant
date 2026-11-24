from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas.doctor import DoctorResponse, SlotResponse
from app.services.doctor_service import (
    get_all_doctors,
    get_available_slots,
)

router = APIRouter(
    prefix="/api/doctors",
    tags=["Doctors"],
)


@router.get("", response_model=list[DoctorResponse])
def list_doctors(db: Session = Depends(get_db)):
    return get_all_doctors(db)


@router.get(
    "/{doctor_id}/slots",
    response_model=list[SlotResponse],
)
def list_available_slots(
    doctor_id: int,
    db: Session = Depends(get_db),
):
    slots = get_available_slots(db, doctor_id)

    if slots is None:
        raise HTTPException(
            status_code=404,
            detail="Doctor not found or inactive",
        )

    return slots
