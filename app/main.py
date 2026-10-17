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
):
    patient = Patient(**payload.model_dump())
    db.add(patient)
    db.commit()
    db.refresh(patient)

    # Demo uses fictional data only, as required by the assessment.
    logger.info(
        "Patient created: %s",
        jsonable_encoder(payload.model_dump()),
    )

    return success(serialize_patient(patient))


@app.put("/patients/{patient_id}")
def update_patient(
    patient_id: UUID,
    changes: dict,
    db: Session = Depends(get_db),
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
    db.commit()
    db.refresh(patient)

    logger.info("Patient updated: %s", patient.patient_id)
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