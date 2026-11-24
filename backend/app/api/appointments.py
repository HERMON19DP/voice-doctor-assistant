from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas.appointment import (
    AppointmentCancel,
    AppointmentCreate,
    AppointmentResponse,
)
from app.services.appointment_service import (
    book_appointment,
    cancel_appointment,
    get_appointments,
)

router = APIRouter(
    prefix="/api/appointments",
    tags=["Appointments"],
)


@router.post(
    "",
    response_model=AppointmentResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_appointment(
    payload: AppointmentCreate,
    db: Session = Depends(get_db),
):
    try:
        return book_appointment(
            db=db,
            doctor_id=payload.doctor_id,
            slot_id=payload.slot_id,
            phone_number=payload.phone_number,
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))


@router.get("", response_model=list[AppointmentResponse])
def list_appointments(
    phone_number: str | None = None,
    db: Session = Depends(get_db),
):
    return get_appointments(db, phone_number)


@router.post(
    "/{appointment_id}/cancel",
    response_model=AppointmentResponse,
)
def cancel_existing_appointment(
    appointment_id: int,
    payload: AppointmentCancel,
    db: Session = Depends(get_db),
):
    try:
        return cancel_appointment(
            db=db,
            appointment_id=appointment_id,
            phone_number=payload.phone_number,
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
