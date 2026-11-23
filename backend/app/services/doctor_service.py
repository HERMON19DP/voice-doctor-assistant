
from sqlalchemy.orm import Session

from app.models import Doctor, Slot


def get_all_doctors(db: Session):
    return (
        db.query(Doctor)
        .filter(Doctor.is_active.is_(True))
        .order_by(Doctor.name)
        .all()
    )


def get_available_slots(db: Session, doctor_id: int):
    doctor = (
        db.query(Doctor)
        .filter(
            Doctor.id == doctor_id,
            Doctor.is_active.is_(True),
        )
        .first()
    )

    if not doctor:
        return None

    slots = (
        db.query(Slot)
        .filter(
            Slot.doctor_id == doctor_id,
            Slot.is_available.is_(True),
        )
        .order_by(Slot.start_time)
        .all()
    )

    return slots
