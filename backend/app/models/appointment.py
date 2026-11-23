
from sqlalchemy import (
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    func,
    text,
)
from sqlalchemy.orm import relationship

from app.database import Base


class Appointment(Base):
    __tablename__ = "appointments"

    id = Column(Integer, primary_key=True, index=True)
    doctor_id = Column(Integer, ForeignKey("doctors.id"), nullable=False)
    slot_id = Column(Integer, ForeignKey("slots.id"), nullable=False)

    phone_number = Column(String(20), nullable=False, index=True)
    status = Column(String(20), default="booked", nullable=False)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)

    doctor = relationship("Doctor", back_populates="appointments")
    slot = relationship("Slot", back_populates="appointment")

    __table_args__ = (
        Index(
            "uq_active_appointment_per_slot",
            "slot_id",
            unique=True,
            sqlite_where=text("status = 'booked'"),
        ),
    )
