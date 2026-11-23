
from sqlalchemy import Boolean, Column, Integer, String
from sqlalchemy.orm import relationship

from app.database import Base


class Doctor(Base):
    __tablename__ = "doctors"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    specialty = Column(String(100), nullable=False)
    experience = Column(Integer, default=0)
    is_active = Column(Boolean, default=True, nullable=False)

    slots = relationship("Slot", back_populates="doctor")
    appointments = relationship("Appointment", back_populates="doctor")
