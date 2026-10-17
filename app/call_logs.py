from datetime import datetime, timezone

from sqlalchemy.dialects.postgresql import insert as postgres_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from app.models import CallLog


def upsert_call_log(db: Session, call_id: str, **changes):
    if not call_id or len(call_id) > 100:
        raise ValueError("Invalid call ID")

    now = datetime.now(timezone.utc)
    dialect = db.get_bind().dialect.name

    if dialect == "postgresql":
        insert = postgres_insert
    elif dialect == "sqlite":
        insert = sqlite_insert
    else:
        raise RuntimeError("Unsupported database for call-log upsert")

    statement = insert(CallLog).values(
        call_id=call_id,
        created_at=now,
        updated_at=now,
        **changes,
    )

    statement = statement.on_conflict_do_update(
        index_elements=["call_id"],
        set_={
            **changes,
            "updated_at": now,
        },
    )

    db.execute(statement)