import logging
from datetime import date, datetime, timezone
from uuid import UUID

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.database import Base, engine, get_db
from app.models import Patient
from app.schemas import PatientInput

from pathlib import Path
from fastapi.responses import FileResponse

from typing import Literal

from pydantic import BaseModel, ConfigDict
from fastapi import Header
from app.call_logs import upsert_call_log
from app.models import CallLog

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("patient-registration")

app = FastAPI(title="CareCloud Patient Registration API")


@app.on_event("startup")
def startup():
    Base.metadata.create_all(bind=engine)


def success(data):
    return {"data": data, "error": None}


def validation_details(errors):
    return [
        {
            "field": ".".join(str(part) for part in item["loc"]),
            "message": item["msg"],
        }
        for item in errors
    ]


@app.exception_handler(RequestValidationError)
async def request_validation_error(
    request: Request, exc: RequestValidationError
):
    return JSONResponse(
        status_code=422,
        content={
            "data": None,
            "error": {
                "message": "Validation failed",
                "details": validation_details(exc.errors()),
            },
        },
    )


@app.exception_handler(StarletteHTTPException)
async def http_error(request: Request, exc: StarletteHTTPException):
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "data": None,
            "error": {"message": exc.detail},
        },
        headers=exc.headers,
    )


@app.exception_handler(SQLAlchemyError)
async def database_error(request: Request, exc: SQLAlchemyError):
    logger.error("Database operation failed: %s", type(exc).__name__)
    return JSONResponse(
        status_code=500,
        content={
            "data": None,
            "error": {
                "message": "Database operation failed. Please try again."
            },
        },
    )


@app.exception_handler(Exception)
async def unexpected_error(request: Request, exc: Exception):
    logger.error("Unexpected server error: %s", type(exc).__name__)
    return JSONResponse(
        status_code=500,
        content={
            "data": None,
            "error": {"message": "An unexpected server error occurred."},
        },
    )


def serialize_patient(patient: Patient):
    result = {}

    for column in Patient.__table__.columns:
        value = getattr(patient, column.name)

        if isinstance(value, datetime):
            # SQLite returns naive datetimes; our stored timestamps are UTC.
            if value.tzinfo is None:
                value = value.replace(tzinfo=timezone.utc)
            value = value.astimezone(timezone.utc).isoformat()
        elif isinstance(value, date):
            value = value.strftime("%m/%d/%Y")
        elif isinstance(value, UUID):
            value = str(value)

        result[column.name] = value

    return result


def find_patient(db: Session, patient_id: UUID):
    patient = db.scalar(
        select(Patient).where(
            Patient.patient_id == patient_id,
            Patient.deleted_at.is_(None),
        )
    )
    if patient is None:
        raise HTTPException(status_code=404, detail="Patient not found")
    return patient


@app.get("/health")
def health():
    return success({"status": "ok"})


@app.get("/patients")
def list_patients(
    last_name: str | None = None,
    date_of_birth: str | None = None,
    phone_number: str | None = None,
    db: Session = Depends(get_db),
):
    query = select(Patient).where(Patient.deleted_at.is_(None))

    if last_name is not None:
        query = query.where(
            Patient.last_name.ilike(
                last_name.strip()
                .replace("\\", "\\\\")
                .replace("%", "\\%")
                .replace("_", "\\_"),
                escape="\\",
            )
        )

    if date_of_birth is not None:
        try:
            birth_date = PatientInput.parse_birth_date(date_of_birth)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc))
        query = query.where(Patient.date_of_birth == birth_date)

    if phone_number is not None:
        try:
            phone = PatientInput.validate_phone(phone_number.strip())
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc))
        query = query.where(Patient.phone_number == phone)

    patients = db.scalars(
        query.order_by(Patient.created_at.desc())
    ).all()

    return success([serialize_patient(patient) for patient in patients])


@app.get("/patients/{patient_id}")
def get_patient(patient_id: UUID, db: Session = Depends(get_db)):
    return success(serialize_patient(find_patient(db, patient_id)))


@app.post("/patients", status_code=201)
def create_patient(
    payload: PatientInput,
    db: Session = Depends(get_db),
    call_id: str | None = Header(
        default=None,
        alias="X-Vapi-Call-Id",
        min_length=1,
        max_length=100,
    ),
):
    patient = Patient(**payload.model_dump())
    db.add(patient)
    db.flush()

    if call_id:
        upsert_call_log(
            db,
            call_id,
            patient_id=patient.patient_id,
        )

    # Patient creation and the call association commit together.
    db.commit()
    db.refresh(patient)

    logger.info(
        "Patient created: patient_id=%s payload=%s",
        patient.patient_id,
        jsonable_encoder(payload.model_dump()),
    )

    return success(serialize_patient(patient))


@app.put("/patients/{patient_id}")
def update_patient(
    patient_id: UUID,
    changes: dict,
    db: Session = Depends(get_db),
    call_id: str | None = Header(
        default=None,
        alias="X-Vapi-Call-Id",
        min_length=1,
        max_length=100,
    ),
):
    patient = find_patient(db, patient_id)

    current = {
        field: getattr(patient, field)
        for field in PatientInput.model_fields
    }

    try:
        validated = PatientInput.model_validate({**current, **changes})
    except ValidationError as exc:
        return JSONResponse(
            status_code=422,
            content={
                "data": None,
                "error": {
                    "message": "Validation failed",
                    "details": validation_details(exc.errors()),
                },
            },
        )

    for field, value in validated.model_dump().items():
        setattr(patient, field, value)

    patient.updated_at = datetime.now(timezone.utc)
    if call_id:
        upsert_call_log(
            db,
            call_id,
            patient_id=patient.patient_id,
        )
    db.commit()
    db.refresh(patient)

    logger.info(
        "Patient updated: patient_id=%s payload=%s",
        patient.patient_id,
        jsonable_encoder(validated.model_dump()),
    )
    return success(serialize_patient(patient))


@app.delete("/patients/{patient_id}")
def delete_patient(patient_id: UUID, db: Session = Depends(get_db)):
    patient = find_patient(db, patient_id)
    now = datetime.now(timezone.utc)

    patient.deleted_at = now
    patient.updated_at = now
    db.commit()

    return success({
        "patient_id": str(patient_id),
        "deleted_at": now.isoformat(),
    })

@app.get("/", include_in_schema=False)
def dashboard():
    return FileResponse(
        Path(__file__).resolve().parent / "dashboard.html"
    )


class PatientLookupRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    phone_number: str


class VoicePatientUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    patient_id: UUID
    confirmed: Literal[True]
    patient: PatientInput


@app.post("/voice/lookup-patient")
def voice_lookup_patient(
    payload: PatientLookupRequest,
    db: Session = Depends(get_db),
):
    try:
        phone = PatientInput.validate_phone(payload.phone_number.strip())
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    matches = db.scalars(
        select(Patient).where(
            Patient.phone_number == phone,
            Patient.deleted_at.is_(None),
        )
    ).all()

    return success({
        "match_count": len(matches),
        "patients": [serialize_patient(patient) for patient in matches],
    })


@app.post("/voice/update-patient")
def voice_update_patient(
    payload: VoicePatientUpdateRequest,
    db: Session = Depends(get_db),
    call_id: str | None = Header(
        default=None,
        alias="X-Vapi-Call-Id",
        min_length=1,
        max_length=100,
    ),
):
    return update_patient(
        patient_id=payload.patient_id,
        changes=payload.patient.model_dump(exclude_unset=True),
        db=db,
        call_id=call_id,
    )

@app.post("/webhooks/vapi")
def vapi_webhook(
    payload: dict,
    db: Session = Depends(get_db),
):
    message = payload.get("message")
    if not isinstance(message, dict):
        raise HTTPException(
            status_code=400,
            detail="Missing message object",
        )

    if message.get("type") != "end-of-call-report":
        return success({"received": True, "ignored": True})

    call = message.get("call") or {}
    if not isinstance(call, dict):
        raise HTTPException(status_code=400, detail="Invalid call object")

    call_id = call.get("id")
    if (
        not isinstance(call_id, str)
        or not call_id.strip()
        or len(call_id) > 100
    ):
        raise HTTPException(status_code=400, detail="Invalid call ID")

    artifact = message.get("artifact") or {}
    if not isinstance(artifact, dict):
        raise HTTPException(
            status_code=400,
            detail="Invalid artifact object",
        )

    transcript = artifact.get("transcript")

    # Fallback if Vapi supplies messages without a combined transcript.
    if not isinstance(transcript, str) or not transcript.strip():
        lines = []
        messages = artifact.get("messages") or []

        if isinstance(messages, list):
            for item in messages:
                if not isinstance(item, dict):
                    continue

                role = item.get("role")
                text = item.get("message")

                if (
                    role in {"user", "assistant", "bot"}
                    and isinstance(text, str)
                    and text.strip()
                ):
                    lines.append(f"{role}: {text}")

        transcript = "\n".join(lines)

    if not transcript.strip():
        # Leave an existing transcript intact if a report is incomplete.
        raise HTTPException(
            status_code=422,
            detail="End-of-call report contains no transcript",
        )

    ended_reason = message.get("endedReason")
    if ended_reason is not None:
        if not isinstance(ended_reason, str):
            raise HTTPException(
                status_code=400,
                detail="Invalid endedReason",
            )
        ended_reason = ended_reason[:255]

    upsert_call_log(
        db,
        call_id,
        transcript=transcript,
        ended_reason=ended_reason,
    )
    db.commit()

    logger.info("Call transcript stored: call_id=%s", call_id)
    return success({"received": True, "call_id": call_id})


@app.get("/patients/{patient_id}/calls")
def get_patient_calls(
    patient_id: UUID,
    db: Session = Depends(get_db),
):
    find_patient(db, patient_id)

    calls = db.scalars(
        select(CallLog)
        .where(CallLog.patient_id == patient_id)
        .order_by(CallLog.created_at.desc())
    ).all()

    return success([
        {
            "call_id": call.call_id,
            "patient_id": str(call.patient_id),
            "transcript": call.transcript,
            "ended_reason": call.ended_reason,
            "created_at": jsonable_encoder(call.created_at),
            "updated_at": jsonable_encoder(call.updated_at),
        }
        for call in calls
    ])