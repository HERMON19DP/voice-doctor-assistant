
from datetime import date, datetime, time, timedelta

from app.database import Base, SessionLocal, engine
from app.models import Doctor, Slot


DOCTORS = [
    {
        "name": "Dr. Ananya Rao",
        "specialty": "Cardiology",
        "experience": 12,
    },
    {
        "name": "Dr. Rahul Sharma",
        "specialty": "Dermatology",
        "experience": 8,
    },
    {
        "name": "Dr. Meera Nair",
        "specialty": "General Medicine",
        "experience": 10,
    },
]

SLOT_START_HOURS = [9, 10, 11, 14, 15]
SLOT_DURATION_MINUTES = 30
DAYS_TO_SEED = 5


def seed_database():
    Base.metadata.create_all(bind=engine)

    db = SessionLocal()

    try:
        # Avoid inserting duplicate seed data.
        if db.query(Doctor).first():
            print("Seed data already exists. Skipping.")
            return

        doctors = [Doctor(**data) for data in DOCTORS]

        db.add_all(doctors)
        db.flush()

        slots = []

        for doctor in doctors:
            for day_offset in range(1, DAYS_TO_SEED + 1):
                slot_date = date.today() + timedelta(days=day_offset)

                for hour in SLOT_START_HOURS:
                    start_time = datetime.combine(
                        slot_date,
                        time(hour=hour),
                    )

                    end_time = start_time + timedelta(
                        minutes=SLOT_DURATION_MINUTES
                    )

                    slots.append(
                        Slot(
                            doctor_id=doctor.id,
                            start_time=start_time,
                            end_time=end_time,
                            is_available=True,
                        )
                    )

        db.add_all(slots)
        db.commit()

        print(f"Created {len(doctors)} doctors.")
        print(f"Created {len(slots)} appointment slots.")

    except Exception:
        db.rollback()
        raise

    finally:
        db.close()


if __name__ == "__main__":
    seed_database()
