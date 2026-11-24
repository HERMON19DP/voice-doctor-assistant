from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app
from app.models import Doctor, Slot


@pytest.fixture
def client():
    # A fresh in-memory SQLite database for each test.
    test_engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    TestingSessionLocal = sessionmaker(
        autocommit=False,
        autoflush=False,
        bind=test_engine,
    )

    Base.metadata.create_all(bind=test_engine)

    def override_get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db

    # Create test doctor and future appointment slot.
    db = TestingSessionLocal()
    doctor = Doctor(
        name="Dr. Test Doctor",
        specialty="Cardiology",
        experience=10,
        is_active=True,
    )
    db.add(doctor)
    db.flush()

    slot = Slot(
        doctor_id=doctor.id,
        start_time=datetime.now() + timedelta(days=1),
        end_time=datetime.now() + timedelta(days=1, minutes=30),
        is_available=True,
    )
    db.add(slot)
    db.commit()

    doctor_id = doctor.id
    slot_id = slot.id
    db.close()

    with TestClient(app) as test_client:
        yield test_client, doctor_id, slot_id

    app.dependency_overrides.clear()
    Base.metadata.drop_all(bind=test_engine)
    test_engine.dispose()


PHONE = "+919876543210"


def test_book_appointment_successfully(client):
    api, doctor_id, slot_id = client

    response = api.post(
        "/api/appointments",
        json={
            "doctor_id": doctor_id,
            "slot_id": slot_id,
            "phone_number": PHONE,
        },
    )

    assert response.status_code == 201
    assert response.json()["status"] == "booked"


def test_prevent_duplicate_booking(client):
    api, doctor_id, slot_id = client

    payload = {
        "doctor_id": doctor_id,
        "slot_id": slot_id,
        "phone_number": PHONE,
    }

    first = api.post("/api/appointments", json=payload)
    second = api.post("/api/appointments", json=payload)

    assert first.status_code == 201
    assert second.status_code == 409


def test_prevent_booking_with_wrong_doctor(client):
    api, doctor_id, slot_id = client

    response = api.post(
        "/api/appointments",
        json={
            "doctor_id": doctor_id + 999,
            "slot_id": slot_id,
            "phone_number": PHONE,
        },
    )

    assert response.status_code == 404


def test_cannot_cancel_with_wrong_phone_number(client):
    api, doctor_id, slot_id = client

    booking = api.post(
        "/api/appointments",
        json={
            "doctor_id": doctor_id,
            "slot_id": slot_id,
            "phone_number": PHONE,
        },
    )

    appointment_id = booking.json()["id"]

    response = api.post(
        f"/api/appointments/{appointment_id}/cancel",
        json={"phone_number": "+919999999999"},
    )

    assert response.status_code == 404


def test_cannot_cancel_twice(client):
    api, doctor_id, slot_id = client

    booking = api.post(
        "/api/appointments",
        json={
            "doctor_id": doctor_id,
            "slot_id": slot_id,
            "phone_number": PHONE,
        },
    )

    appointment_id = booking.json()["id"]
    cancel_url = f"/api/appointments/{appointment_id}/cancel"
    cancel_payload = {"phone_number": PHONE}

    first = api.post(cancel_url, json=cancel_payload)
    second = api.post(cancel_url, json=cancel_payload)

    assert first.status_code == 200
    assert first.json()["status"] == "cancelled"
    assert second.status_code == 404
