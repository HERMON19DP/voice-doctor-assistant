from datetime import datetime

from sqlalchemy import update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import Appointment, Doctor, Slot


def book_appointment(
    db: Session,
    doctor_id: int,
    slot_id: int,
    phone_number: str,
):
    try:
        doctor = (
            db.query(Doctor)
            .filter(
                Doctor.id == doctor_id,
                Doctor.is_active.is_(True),
            )
            .first()
        )

        if not doctor:
            raise LookupError("Doctor not found or inactive")

        # Atomically claim the slot only if it is still available.
        result = db.execute(
            update(Slot)
            .where(
                Slot.id == slot_id,
                Slot.doctor_id == doctor_id,
                Slot.is_available.is_(True),
                Slot.start_time > datetime.now(),
            )
            .values(is_available=False)
        )

        if result.rowcount != 1:
            raise ValueError("Slot is unavailable, invalid, or already booked")

        appointment = Appointment(
            doctor_id=doctor_id,
            slot_id=slot_id,
            phone_number=phone_number,
            status="booked",
        )

        db.add(appointment)
        db.commit()
        db.refresh(appointment)

        return appointment

    except Exception:
        db.rollback()
        raise


def get_appointments(db: Session, phone_number: str | None = None):
    query = db.query(Appointment)

    if phone_number:
        query = query.filter(Appointment.phone_number == phone_number)

    return query.order_by(Appointment.created_at.desc()).all()


def cancel_appointment(
    db: Session,
    appointment_id: int,
    phone_number: str,
):
    try:
        appointment = (
            db.query(Appointment)
            .filter(
                Appointment.id == appointment_id,
                Appointment.phone_number == phone_number,
                Appointment.status == "booked",
            )
            .first()
        )

        if not appointment:
            raise LookupError(
                "Appointment not found, already cancelled, "
                "or phone number does not match"
            )
        appointment.status = "cancelled"
        # Only reopen a slot if its appointment time is still in the future.
        if appointment.slot.start_time > datetime.now():
            appointment.slot.is_available = True

        db.commit()
        db.refresh(appointment)

        return appointment

    except Exception:
        db.rollback()
        raise
