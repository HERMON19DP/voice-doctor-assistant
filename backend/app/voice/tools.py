import re
from datetime import datetime

from loguru import logger
from pipecat.services.llm_service import FunctionCallParams

from app.database import SessionLocal
from app.models import Appointment, Doctor
from app.services.appointment_service import (
    book_appointment,
    cancel_appointment,
    get_appointments,
)
from app.services.doctor_service import get_all_doctors, get_available_slots


def normalize_phone_number(phone_number: str) -> str:
    """Normalize a spoken phone number to digits for comparison."""
    return re.sub(r"\D", "", phone_number or "")


def get_pending_actions(params: FunctionCallParams) -> dict:
    """Get pending actions for this individual voice session."""
    return params.app_resources.setdefault("pending_actions", {})


def format_datetime(value: datetime) -> str:
    return value.strftime("%A, %d %B %Y at %I:%M %p")


async def check_doctor_availability(
    params: FunctionCallParams,
    specialty: str = "",
    doctor_name: str = "",
):
    """Find active doctors and their upcoming available appointment slots.

    Use this when the caller asks which doctors are available, asks for a
    particular specialty, or asks for a particular doctor's availability.
    """
    db = SessionLocal()

    try:
        doctors = get_all_doctors(db)
        specialty_query = specialty.strip().casefold()
        name_query = doctor_name.strip().casefold()

        matching_doctors = [
            doctor
            for doctor in doctors
            if (not specialty_query or specialty_query in doctor.specialty.casefold())
            and (not name_query or name_query in doctor.name.casefold())
        ]

        if not matching_doctors:
            await params.result_callback(
                {
                    "success": True,
                    "doctors": [],
                    "message": "No doctors matched those search criteria.",
                }
            )
            return

        results = []
        now = datetime.now()

        for doctor in matching_doctors:
            slots = get_available_slots(db, doctor.id) or []

            upcoming_slots = [
                slot for slot in slots if slot.is_available and slot.start_time > now
            ]

            results.append(
                {
                    "doctor_id": doctor.id,
                    "doctor_name": doctor.name,
                    "specialty": doctor.specialty,
                    "experience_years": doctor.experience,
                    "available_slots": [
                        {
                            "slot_id": slot.id,
                            "start_time": slot.start_time.isoformat(),
                            "end_time": slot.end_time.isoformat(),
                            "display_time": format_datetime(slot.start_time),
                        }
                        for slot in upcoming_slots
                    ],
                }
            )

        await params.result_callback(
            {
                "success": True,
                "doctors": results,
                "message": (
                    "Availability retrieved. Only offer slots returned "
                    "in this result."
                ),
            }
        )

    except Exception:
        logger.exception("Failed to check doctor availability")
        await params.result_callback(
            {
                "success": False,
                "message": "I could not retrieve doctor availability right now.",
            }
        )

    finally:
        db.close()


async def prepare_appointment_booking(
    params: FunctionCallParams,
    doctor_id: int,
    slot_id: int,
    phone_number: str,
):
    """Prepare a booking, but do not create it yet.

    Call this only after the caller has selected a doctor and a slot.
    Read the phone number back to the caller and ask for explicit confirmation.
    """
    db = SessionLocal()

    try:
        phone = normalize_phone_number(phone_number)

        if not 7 <= len(phone) <= 15:
            await params.result_callback(
                {
                    "success": False,
                    "message": (
                        "That phone number does not appear valid. "
                        "Ask the caller to repeat it."
                    ),
                }
            )
            return

        doctor = (
            db.query(Doctor)
            .filter(
                Doctor.id == doctor_id,
                Doctor.is_active.is_(True),
            )
            .first()
        )

        if not doctor:
            await params.result_callback(
                {
                    "success": False,
                    "message": "That doctor could not be found.",
                }
            )
            return

        slots = get_available_slots(db, doctor_id) or []
        slot = next(
            (
                item
                for item in slots
                if item.id == slot_id
                and item.is_available
                and item.start_time > datetime.now()
            ),
            None,
        )

        if not slot:
            await params.result_callback(
                {
                    "success": False,
                    "message": (
                        "That slot is no longer available. " "Check availability again."
                    ),
                }
            )
            return

        pending = get_pending_actions(params)

        pending["booking"] = {
            "doctor_id": doctor_id,
            "slot_id": slot_id,
            "phone_number": phone,
        }

        await params.result_callback(
            {
                "success": True,
                "confirmation_required": True,
                "doctor_name": doctor.name,
                "specialty": doctor.specialty,
                "appointment_time": format_datetime(slot.start_time),
                "phone_number_to_confirm": phone,
                "message": (
                    "Booking has NOT been created. Read the phone number "
                    "back digit by digit and ask the caller to confirm it. "
                    "Then ask whether they want to confirm this booking."
                ),
            }
        )

    except Exception:
        logger.exception("Failed to prepare appointment booking")
        await params.result_callback(
            {
                "success": False,
                "message": "I could not prepare that booking. Please try again.",
            }
        )

    finally:
        db.close()


async def confirm_appointment_booking(params: FunctionCallParams):
    """Create the pending appointment after the caller explicitly agrees.

    Call only after the caller has confirmed the read-back phone number
    and clearly agreed to book the appointment.
    """
    pending = get_pending_actions(params)
    booking = pending.get("booking")

    if not booking:
        await params.result_callback(
            {
                "success": False,
                "message": (
                    "There is no pending booking. Check availability "
                    "and prepare the booking again."
                ),
            }
        )
        return

    db = SessionLocal()

    try:
        appointment = book_appointment(
            db=db,
            doctor_id=booking["doctor_id"],
            slot_id=booking["slot_id"],
            phone_number=booking["phone_number"],
        )

        pending.pop("booking", None)

        await params.result_callback(
            {
                "success": True,
                "appointment_id": appointment.id,
                "status": appointment.status,
                "message": ("The appointment has been booked successfully."),
            }
        )

    except (LookupError, ValueError) as exc:
        pending.pop("booking", None)
        await params.result_callback(
            {
                "success": False,
                "message": str(exc),
            }
        )

    except Exception:
        logger.exception("Failed to confirm appointment booking")
        await params.result_callback(
            {
                "success": False,
                "message": ("I could not complete the booking due to a system error."),
            }
        )

    finally:
        db.close()


async def find_my_appointments(
    params: FunctionCallParams,
    phone_number: str,
):
    """Find booked appointments associated with a phone number.

    Ask the caller for the phone number they used when booking.
    """
    db = SessionLocal()

    try:
        phone = normalize_phone_number(phone_number)

        if not 7 <= len(phone) <= 15:
            await params.result_callback(
                {
                    "success": False,
                    "appointments": [],
                    "message": "Please ask the caller to repeat their phone number.",
                }
            )
            return

        # Fetch all appointments so differently formatted versions of the
        # same phone number can be compared after normalization.
        appointments = get_appointments(db)

        matching_appointments = [
            appointment
            for appointment in appointments
            if (
                appointment.status == "booked"
                and normalize_phone_number(appointment.phone_number) == phone
            )
        ]

        results = [
            {
                "appointment_id": appointment.id,
                "doctor_name": appointment.doctor.name,
                "specialty": appointment.doctor.specialty,
                "appointment_time": format_datetime(appointment.slot.start_time),
                "status": appointment.status,
            }
            for appointment in matching_appointments
        ]

        await params.result_callback(
            {
                "success": True,
                "appointments": results,
                "message": (
                    "Appointments retrieved."
                    if results
                    else "No active appointments were found for that phone number."
                ),
            }
        )

    except Exception:
        logger.exception("Failed to find appointments")
        await params.result_callback(
            {
                "success": False,
                "appointments": [],
                "message": "I could not retrieve appointments right now.",
            }
        )

    finally:
        db.close()


async def prepare_appointment_cancellation(
    params: FunctionCallParams,
    appointment_id: int,
    phone_number: str,
):
    """Prepare cancellation, but do not cancel the appointment yet.

    Find the appointment using its ID and the phone number supplied by
    the caller. Ask for explicit confirmation before cancelling.
    """
    db = SessionLocal()

    try:
        phone = normalize_phone_number(phone_number)

        if not 7 <= len(phone) <= 15:
            await params.result_callback(
                {
                    "success": False,
                    "message": "Please ask the caller to repeat their phone number.",
                }
            )
            return

        appointment = (
            db.query(Appointment)
            .filter(
                Appointment.id == appointment_id,
                Appointment.status == "booked",
            )
            .first()
        )

        if not appointment or normalize_phone_number(appointment.phone_number) != phone:
            await params.result_callback(
                {
                    "success": False,
                    "message": (
                        "No active appointment was found matching that "
                        "appointment ID and phone number."
                    ),
                }
            )
            return

        pending = get_pending_actions(params)

        # Preserve the exact stored phone number because the existing
        # cancellation service performs an exact database comparison.
        pending["cancellation"] = {
            "appointment_id": appointment.id,
            "phone_number": appointment.phone_number,
        }

        await params.result_callback(
            {
                "success": True,
                "confirmation_required": True,
                "appointment_id": appointment.id,
                "doctor_name": appointment.doctor.name,
                "appointment_time": format_datetime(appointment.slot.start_time),
                "phone_number_to_confirm": phone,
                "message": (
                    "The appointment has NOT been cancelled. Read the "
                    "phone number back digit by digit, then ask the caller "
                    "whether they want to cancel this appointment."
                ),
            }
        )

    except Exception:
        logger.exception("Failed to prepare appointment cancellation")
        await params.result_callback(
            {
                "success": False,
                "message": "I could not prepare that cancellation.",
            }
        )

    finally:
        db.close()


async def confirm_appointment_cancellation(params: FunctionCallParams):
    """Cancel the pending appointment after the caller explicitly agrees.

    Call only after the caller has confirmed the phone-number read-back
    and clearly agreed to cancel the appointment.
    """
    pending = get_pending_actions(params)
    cancellation = pending.get("cancellation")

    if not cancellation:
        await params.result_callback(
            {
                "success": False,
                "message": (
                    "There is no pending cancellation. Find the appointment "
                    "and prepare the cancellation again."
                ),
            }
        )
        return

    db = SessionLocal()

    try:
        appointment = cancel_appointment(
            db=db,
            appointment_id=cancellation["appointment_id"],
            phone_number=cancellation["phone_number"],
        )

        pending.pop("cancellation", None)

        await params.result_callback(
            {
                "success": True,
                "appointment_id": appointment.id,
                "status": appointment.status,
                "message": "The appointment has been cancelled successfully.",
            }
        )

    except LookupError as exc:
        pending.pop("cancellation", None)
        await params.result_callback(
            {
                "success": False,
                "message": str(exc),
            }
        )

    except Exception:
        logger.exception("Failed to confirm appointment cancellation")
        await params.result_callback(
            {
                "success": False,
                "message": (
                    "I could not cancel the appointment due to a system error."
                ),
            }
        )

    finally:
        db.close()


async def discard_pending_action(
    params: FunctionCallParams,
    action: str,
):
    """Discard a pending booking or cancellation when the caller declines."""
    pending = get_pending_actions(params)

    if action not in {"booking", "cancellation", "all"}:
        await params.result_callback(
            {
                "success": False,
                "message": "Unknown pending action.",
            }
        )
        return

    if action == "all":
        pending.clear()
    else:
        pending.pop(action, None)

    await params.result_callback(
        {
            "success": True,
            "message": "The pending action has been discarded. No changes were made.",
        }
    )
