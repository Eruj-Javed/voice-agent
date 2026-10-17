import re
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, field_validator

Sex = Literal["Male", "Female", "Other", "Decline to Answer"]

US_STATES = set(
    "AL AK AZ AR CA CO CT DE FL GA HI ID IL IN IA KS KY LA ME MD "
    "MA MI MN MS MO MT NE NV NH NJ NM NY NC ND OH OK OR PA RI SC "
    "SD TN TX UT VT VA WA WV WI WY DC".split()
)


class PatientInput(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
    )

    first_name: str
    last_name: str
    date_of_birth: date
    sex: Sex
    phone_number: str
    address_line_1: str
    city: str
    state: str
    zip_code: str

    email: EmailStr | None = None
    address_line_2: str | None = None
    insurance_provider: str | None = None
    insurance_member_id: str | None = None
    preferred_language: str = "English"
    emergency_contact_name: str | None = None
    emergency_contact_phone: str | None = None

    @field_validator("*", mode="before")
    @classmethod
    def clean_strings(cls, value):
        if isinstance(value, str):
            return value.strip()
        return value

    @field_validator(
        "email",
        "address_line_2",
        "insurance_provider",
        "insurance_member_id",
        "emergency_contact_name",
        "emergency_contact_phone",
        mode="before",
    )
    @classmethod
    def empty_optional_to_none(cls, value):
        return None if value == "" else value

    @field_validator("first_name", "last_name")
    @classmethod
    def validate_name(cls, value):
        if not 1 <= len(value) <= 50:
            raise ValueError("Must contain 1–50 characters")
        if not any(char.isalpha() for char in value):
            raise ValueError("Must contain letters")
        if not all(char.isalpha() or char in "-'" for char in value):
            raise ValueError("Use only letters, hyphens, or apostrophes")
        return value

    @field_validator("date_of_birth", mode="before")
    @classmethod
    def parse_birth_date(cls, value):
        if isinstance(value, str):
            for fmt in ("%m/%d/%Y", "%Y-%m-%d"):
                try:
                    return datetime.strptime(value, fmt).date()
                except ValueError:
                    pass
            raise ValueError("Use a valid date: MM/DD/YYYY or YYYY-MM-DD")
        return value

    @field_validator("date_of_birth")
    @classmethod
    def validate_birth_date(cls, value):
        if value > date.today():
            raise ValueError("Date of birth cannot be in the future")
        return value

    @field_validator("phone_number", "emergency_contact_phone")
    @classmethod
    def validate_phone(cls, value):
        if value is None:
            return value

        if not re.fullmatch(r"\+?[0-9() .-]+", value):
            raise ValueError("Use a valid U.S. phone number")

        digits = re.sub(r"[^0-9]", "", value)
        if len(digits) == 11 and digits.startswith("1"):
            digits = digits[1:]

        if not re.fullmatch(r"[2-9][0-9]{2}[2-9][0-9]{6}", digits):
            raise ValueError(
                "Use a 10-digit U.S. number with a valid area code "
                "and exchange, optionally prefixed with +1"
            )
        return digits

    @field_validator("state")
    @classmethod
    def validate_state(cls, value):
        value = value.upper()
        if value not in US_STATES:
            raise ValueError("Use a valid two-letter U.S. state code")
        return value

    @field_validator("zip_code")
    @classmethod
    def validate_zip(cls, value):
        if not re.fullmatch(r"[0-9]{5}(?:-[0-9]{4})?", value):
            raise ValueError("Use a five-digit ZIP or ZIP+4")
        return value

    @field_validator("address_line_1", "city", "preferred_language")
    @classmethod
    def validate_required_text(cls, value, info):
        limit = 255 if info.field_name == "address_line_1" else 100
        if not 1 <= len(value) <= limit:
            raise ValueError(f"Must contain 1–{limit} characters")
        return value

    @field_validator(
        "address_line_2",
        "insurance_provider",
        "insurance_member_id",
        "emergency_contact_name",
    )
    @classmethod
    def validate_optional_text(cls, value, info):
        if value is None:
            return value

        limits = {
            "address_line_2": 255,
            "insurance_provider": 255,
            "insurance_member_id": 100,
            "emergency_contact_name": 150,
        }
        if len(value) > limits[info.field_name]:
            raise ValueError("Value is too long")

        if (
            info.field_name == "insurance_member_id"
            and not re.fullmatch(r"[A-Za-z0-9]+", value)
        ):
            raise ValueError("Insurance member ID must be alphanumeric")

        return value