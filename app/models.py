from datetime import date, datetime, timezone
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    String,
    Uuid,
    ForeignKey,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class Patient(Base):
    __tablename__ = "patients"

    __table_args__ = (
        CheckConstraint(
            "length(first_name) BETWEEN 1 AND 50",
            name="valid_first_name_length",
        ),
        CheckConstraint(
            "length(last_name) BETWEEN 1 AND 50",
            name="valid_last_name_length",
        ),
        CheckConstraint(
            "sex IN ('Male', 'Female', 'Other', 'Decline to Answer')",
            name="valid_sex",
        ),
        CheckConstraint(
            "length(phone_number) = 10",
            name="valid_phone_length",
        ),
        CheckConstraint(
            "length(address_line_1) > 0",
            name="required_street_address",
        ),
        CheckConstraint(
            "length(city) BETWEEN 1 AND 100",
            name="valid_city_length",
        ),
        CheckConstraint(
            "state IN ("
            "'AL','AK','AZ','AR','CA','CO','CT','DE','FL','GA',"
            "'HI','ID','IL','IN','IA','KS','KY','LA','ME','MD',"
            "'MA','MI','MN','MS','MO','MT','NE','NV','NH','NJ',"
            "'NM','NY','NC','ND','OH','OK','OR','PA','RI','SC',"
            "'SD','TN','TX','UT','VT','VA','WA','WV','WI','WY','DC'"
            ")",
            name="valid_state",
        ),
        CheckConstraint(
            "length(zip_code) IN (5, 10)",
            name="valid_zip_length",
        ),
        CheckConstraint(
            "emergency_contact_phone IS NULL "
            "OR length(emergency_contact_phone) = 10",
            name="valid_emergency_phone_length",
        ),
    )

    patient_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )

    first_name: Mapped[str] = mapped_column(String(50))
    last_name: Mapped[str] = mapped_column(String(50), index=True)
    date_of_birth: Mapped[date] = mapped_column(Date)
    sex: Mapped[str] = mapped_column(String(20))

    # Phone numbers are not unique: family members may share a number.
    phone_number: Mapped[str] = mapped_column(String(10), index=True)
    email: Mapped[str | None] = mapped_column(String(254))

    address_line_1: Mapped[str] = mapped_column(String(255))
    address_line_2: Mapped[str | None] = mapped_column(String(255))
    city: Mapped[str] = mapped_column(String(100))
    state: Mapped[str] = mapped_column(String(2))
    zip_code: Mapped[str] = mapped_column(String(10))

    insurance_provider: Mapped[str | None] = mapped_column(String(255))
    insurance_member_id: Mapped[str | None] = mapped_column(String(100))

    preferred_language: Mapped[str] = mapped_column(
        String(100),
        default="English",
    )

    emergency_contact_name: Mapped[str | None] = mapped_column(String(150))
    emergency_contact_phone: Mapped[str | None] = mapped_column(String(10))

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        onupdate=utc_now,
    )
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    
class CallLog(Base):
    __tablename__ = "call_logs"

    call_id: Mapped[str] = mapped_column(
        String(100),
        primary_key=True,
    )
    patient_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("patients.patient_id"),
        nullable=True,
        index=True,
    )
    transcript: Mapped[str | None] = mapped_column(Text)
    ended_reason: Mapped[str | None] = mapped_column(String(255))

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        onupdate=utc_now,
    )