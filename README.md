# CareCloud Voice Patient Registration

A phone-based patient registration demonstration built with Vapi, FastAPI, SQLAlchemy, and PostgreSQL. Riley collects demographic information, reads it back, requests confirmation, and uses HTTP tools to save or update a patient. A web dashboard displays the stored records.

**Use fictional information only. This is not a production healthcare system.**

## Live demo

| Resource | Address |
| --- | --- |
| U.S. inbound number | +1 (209) 508-9012 |
| Repository | https://github.com/Eruj-Javed/voice-agent |
| API base URL | https://just-nature-production-4296.up.railway.app |
| Dashboard | https://just-nature-production-4296.up.railway.app/ |
| Interactive API documentation | https://just-nature-production-4296.up.railway.app/docs |
| Health endpoint | https://just-nature-production-4296.up.railway.app/health |

No credentials are required for the current demonstration API or dashboard. Calling the number may incur carrier charges. Availability depends on the Railway deployment, Vapi account credits, and phone-number routing remaining active.

## Features

- Natural voice intake with optional information offered rather than required.
- Required patient demographic fields and server-side validation.
- Prompt instructions for corrections, spelled names, interruptions, out-of-order answers, cancellation, and restarting unconfirmed intake.
- Complete readback and explicit caller confirmation before the assistant invokes a save tool.
- Persistent patient storage, generated UUIDs, creation/update timestamps, and soft deletion.
- Patient listing, individual retrieval, creation, partial updates through PUT, and filters.
- Returning-patient lookup by supplied phone number and an offer to update an existing record.
- Dashboard with filters, manual refresh, patient counts, and patient detail views.
- Call-transcript storage through an end-of-call webhook, linked to saved patients by Vapi call ID.
- Structured JSON responses and application logging.

Conversation behavior depends on the model and speech configuration; prompt instructions are not deterministic guarantees. Transcript capture has been verified end to end, including a stored transcript linked to its patient UUID. Reproducing it requires the Vapi configuration described below.

## Architecture and technology choices

| Component | Responsibility and reason |
| --- | --- |
| Vapi | Inbound telephony, speech recognition, voice synthesis, conversation orchestration, and HTTP tool execution; avoids implementing a speech pipeline for a short assessment. |
| LLM configured in Vapi | Interprets caller answers and corrections, tracks collected values, and selects tools according to the system prompt. Model and voice settings are managed in Vapi. |
| FastAPI and Pydantic | HTTP routes, interactive OpenAPI documentation, and structured input validation. |
| SQLAlchemy | Patient/call models and database access across SQLite and PostgreSQL. |
| PostgreSQL on Railway | Persistent deployed storage independent of application container restarts. |
| SQLite | Simple local development using a persistent file. |
| HTML, CSS, JavaScript | A small dashboard served by FastAPI; no separate frontend build or hosting service. |

Vapi sends API Request tool calls directly to the backend. The browser dashboard uses the same patient API. After a call ends, Vapi sends a separate report to the transcript webhook.

The source separates database configuration, database models, validation, transcript upsert logic, and dashboard presentation. HTTP handlers and patient operations currently share `main.py`; the voice update adapter reuses the update function directly. Extracting a dedicated service layer is a future improvement.

## Repository layout

| Path | Purpose |
| --- | --- |
| `app/__init__.py` | Python package marker. |
| `app/database.py` | Environment loading, engine, session factory, and dependency. |
| `app/models.py` | Patient and call-log tables. |
| `app/schemas.py` | Patient validation and normalization. |
| `app/main.py` | REST routes, voice adapters, errors, dashboard route, and webhook. |
| `app/call_logs.py` | Database-specific conflict-safe call-log upserts. |
| `app/dashboard.html` | Dashboard UI. |
| `vapi/system-prompt.md` | Copy of the published assistant prompt. |
| `vapi/first-message.txt` | Copy of the published greeting. |
| `.env.example` | Example local database configuration. |
| `.gitignore` | Excludes credentials, virtual environment, and local database files. |
| `requirements.txt` | Python dependencies. |

Keep the prompt files synchronized with the published Vapi assistant. The repository does not automatically provision or synchronize the Vapi assistant, number, or tools.

## Local setup

Prerequisite: Python 3.10 or newer; Python 3.12 is suitable.

```bash
git clone https://github.com/Eruj-Javed/voice-agent.git
cd voice-agent
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
cp .env.example .env
```

Set `.env` to:

```dotenv
DATABASE_URL=sqlite:///./patients.db
```

Start the application from the repository root:

```bash
uvicorn app.main:app --reload
```

- Dashboard: http://127.0.0.1:8000/
- API docs: http://127.0.0.1:8000/docs
- Health: http://127.0.0.1:8000/health

Tables are created automatically at startup. The local SQLite file persists between runs, provided it is retained and the application is launched from the same directory. Local and deployed databases are separate; records are not synchronized.

For local PostgreSQL, set `DATABASE_URL` to a reachable PostgreSQL connection URL. `database.py` rewrites `postgres://` and `postgresql://` URLs to use the installed psycopg driver.

## Environment and credentials

| Variable or setting | Purpose |
| --- | --- |
| `DATABASE_URL` | Database connection string. Defaults to local SQLite if absent; explicitly configure PostgreSQL in deployment. |
| `PORT` | Provided by Railway and used by the deployment start command. |
| Vapi credentials/provider settings | Managed in Vapi, not hardcoded in Python source. |

The backend does not directly call an LLM API, so it does not require an OpenAI key to serve these routes. Vapi model access and billing must be configured separately. Never commit `.env` or real credentials.

## Railway deployment

1. Create a Railway project and deploy the GitHub repository as an application service.
2. Add PostgreSQL in the same project.
3. In the application service, reference the database URL:

   ```text
   DATABASE_URL=${{Postgres.DATABASE_URL}}
   ```

   Use the actual database service name if different.

4. Set the application start command:

   ```bash
   uvicorn app.main:app --host 0.0.0.0 --port $PORT
   ```

5. Deploy, generate a public HTTPS domain, and set its target port to the application's listening port.
6. Verify `/health`, then create and retrieve a fictional patient through `/docs` to verify database connectivity. `/health` alone does not query the database.
7. Configure Vapi to use the public URLs below.

Application code changes require a Railway deployment. Prompt/tool changes require publishing in Vapi. `create_all` creates missing tables but does not migrate existing table definitions.

## Vapi configuration

Create/publish an assistant using `vapi/system-prompt.md` and `vapi/first-message.txt`. Assign that assistant to the U.S. number's inbound settings. Select a compatible model, transcriber, and voice in Vapi.

Configure these API Request tools, using JSON request bodies and `Content-Type: application/json`:

| Tool | Method and path | Request |
| --- | --- | --- |
| `create_patient` | `POST /patients` | Patient fields; the nine required fields listed below must be required in the tool schema. |
| `lookup_patient` | `POST /voice/lookup-patient` | Required string `phone_number`. |
| `update_patient` | `POST /voice/update-patient` | Required `patient_id` string, `confirmed` boolean, and `patient` object containing the resulting patient fields. |

Use the public API base URL for all tool paths. Enable no additional properties in their schemas. Attach and publish all tools on Riley. Configure an end-call tool if the assistant should explicitly terminate calls after its goodbye.

For both create and update tools, add this request header:

```text
X-Vapi-Call-Id: {{call.id}}
```

Vapi supplies this value at runtime; do not ask the model to invent it or place it inside the patient object.

Set the assistant Server URL to:

```text
https://just-nature-production-4296.up.railway.app/webhooks/vapi
```

Enable the `end-of-call-report` server message and transcript storage where exposed in the assistant's artifact settings. Publish the assistant. The assistant Server URL is distinct from tool request URLs. Use the corresponding domain for another deployment.

## Registration and update process

1. Riley greets the caller and explains that this is a fictional-data demonstration.
2. It collects the first/last name, then the patient phone number. Volunteered out-of-order information should be retained.
3. It calls `lookup_patient` using the supplied number. An error is not treated as an empty result.
4. With no match, it collects remaining required fields and offers optional details.
5. With a matching patient, it offers an update. Multiple or ambiguous matches require clarification using the caller's name and date of birth; the agent must not arbitrarily choose a record.
6. Clear corrections replace prior values; unclear names can be spelled. Declining one optional field skips only that field.
7. Riley reads back the resulting registration and requests explicit permission to save. Changes require renewed confirmation.
8. It calls create for a new patient or update with the existing UUID. Updates should preserve information unless the caller changes or removes it.
9. It announces success only after the API returns a saved patient. Validation errors require corrections; uncertain timeouts must not trigger blind duplicate creation.
10. A save request containing the call-ID header links that call to the patient in the same transaction.
11. After the call ends, the report webhook stores its transcript and end reason using the same call ID.

Phone lookup is duplicate detection, not secure identity verification. Confirmation before creation is enforced by assistant instructions, not a server-side proof of caller consent. The update adapter requires `confirmed=true`, which is still a model-supplied assertion.

## Database contents

### `patients`

| Field | Storage and validation |
| --- | --- |
| `patient_id` | Auto-generated UUID primary key. |
| `first_name`, `last_name` | Required, 1–50 characters; letters, hyphens, apostrophes. Last name indexed. |
| `date_of_birth` | Required date; valid and not in the future. API accepts MM/DD/YYYY or YYYY-MM-DD; patient responses use MM/DD/YYYY. |
| `sex` | Required: Male, Female, Other, Decline to Answer. |
| `phone_number` | Required normalized 10-digit number; optional leading country code/formatting accepted. Area-code and exchange first digits must be 2–9. Indexed, not unique. |
| `email` | Optional validated email. |
| `address_line_1` | Required street address, up to 255 characters. |
| `address_line_2` | Optional apartment/suite/unit, up to 255 characters. |
| `city` | Required, 1–100 characters. |
| `state` | Required valid two-letter code; includes the 50 states and DC. |
| `zip_code` | Required five digits or ZIP+4; stored as a string to retain leading zeros. |
| `insurance_provider` | Optional string, up to 255 characters. |
| `insurance_member_id` | Optional alphanumeric string, up to 100 characters. |
| `preferred_language` | Nonempty string, default English, up to 100 characters. This does not itself enable multilingual speech. |
| `emergency_contact_name` | Optional name, up to 150 characters. |
| `emergency_contact_phone` | Optional phone, validated/normalized like the patient phone. |
| `created_at`, `updated_at` | Application-generated UTC timestamps. |
| `deleted_at` | Nullable timestamp set on soft deletion. |

There are nine required intake fields: first name, last name, birth date, sex, phone, street address, city, state, and ZIP. Optional fields may be null; preferred language defaults to English. Empty optional strings are normalized to null.

Database constraints enforce required values and selected length/enum rules. Pydantic applies additional character, date, email, phone, and format validation. Not all application validation is duplicated as a database constraint. Shared family phone numbers are allowed.

### `call_logs`

| Field | Purpose |
| --- | --- |
| `call_id` | Vapi call identifier; primary key, one row per call. |
| `patient_id` | Nullable foreign key to the patient saved during that call. |
| `transcript` | Conversation text received in the end-of-call report. |
| `ended_reason` | Call termination reason reported by Vapi. |
| `created_at`, `updated_at` | Application-generated UTC timestamps. |

Conflict-safe upserts support repeated reports and either arrival order between the report and patient association. Unlinked reports remain stored with a null patient ID. A save can create a linked call row before its transcript arrives. This implementation stores text, not audio, and supports one patient association per call.

## API reference

| Method | Endpoint | Behavior |
| --- | --- | --- |
| GET | `/` | Dashboard HTML. |
| GET | `/health` | Application liveness response. |
| GET | `/patients` | List active patients, newest first. Optional exact last-name (case-insensitive), birth-date, and phone filters; combined filters use AND. |
| GET | `/patients/{patient_id}` | Retrieve an active patient. |
| POST | `/patients` | Validate/create a patient; returns 201. |
| PUT | `/patients/{patient_id}` | Partial update; merge with existing fields and validate the resulting record. |
| DELETE | `/patients/{patient_id}` | Set `deleted_at`; return 200. Does not hard-delete. |
| POST | `/voice/lookup-patient` | Return `data.match_count` and `data.patients` for a normalized phone. |
| POST | `/voice/update-patient` | Confirmed update adapter using a supplied UUID and patient object. |
| POST | `/webhooks/vapi` | Store end-of-call transcripts; ignore other event types. |
| GET | `/patients/{patient_id}/calls` | List call records linked to an active patient. |

Normal patient reads exclude soft-deleted records and return 404 for a deleted or missing patient. The calls endpoint also requires an active patient; soft deletion does not remove stored call logs.

Success envelope:

```json
{"data": {"patient_id": "generated-uuid"}, "error": null}
```

Error envelope:

```json
{"data": null, "error": {"message": "Validation failed", "details": [{"field": "phone_number", "message": "Invalid value"}]}}
```

Validation errors normally return 422; malformed webhook structure can return 400; missing records return 404; database/unexpected errors return 500. Lists use an array in `data`. The HTML dashboard and framework documentation are not JSON-envelope endpoints.

### Create an example patient

```bash
curl -X POST https://just-nature-production-4296.up.railway.app/patients \
  -H 'Content-Type: application/json' \
  -d '{"first_name":"Alex","last_name":"Carter","date_of_birth":"03/12/1990","sex":"Male","phone_number":"2025550186","address_line_1":"456 Example Avenue","city":"Boston","state":"MA","zip_code":"02108"}'
```

This creates a real demonstration database row. Use fictional information. To query it:

```bash
curl 'https://just-nature-production-4296.up.railway.app/patients?phone_number=2025550186'
```

For transcripts, substitute an actual patient UUID:

```text
https://just-nature-production-4296.up.railway.app/patients/PATIENT_UUID/calls
```

The dashboard currently displays patient details, not transcript history; use this endpoint or API docs for transcripts. Vapi's call logs provide separate vendor-side conversation/tool diagnostics.

## Logging and validation checks

The application logs final new-patient payloads, updated payloads when the logging change is applied, patient identifiers, transcript receipt call IDs, and database/server error types to stdout. View these in Railway deployment logs or the local terminal. Full transcripts are stored in the database rather than printed by the webhook.

Manual checks reported during development include phone/browser registration and API retrieval, partial updates, invalid-phone rejection, soft deletion, and persistence across a deployment. No automated test suite is supplied in the implementation described here; installing pytest is not itself test coverage. Call-transcript storage has also been verified end to end: the patient call-history endpoint returned the linked call ID, patient UUID, full transcript, end reason, and timestamps. Returning-patient updates should be checked after changes to their configuration.

Suggested reproducible checks:

1. Register a fictional patient by phone and verify the saved record.
2. Make a second call for another patient; ensure both remain stored.
3. Reuse a patient's phone/name, change the city, and verify the same UUID and unchanged patient count.
4. Provide an impossible/future birth date and a short phone number; verify reprompting and server rejection.
5. Correct a spelled surname, interrupt speech, volunteer several fields, and decline optional fields.
6. Cancel or restart before confirmation; verify no incomplete registration is created.
7. Redeploy the application and retrieve previously saved records.
8. After a newly configured call ends, retrieve its transcript by patient UUID. Repeat the same report in local testing and check it does not create a second call row.
9. Test database failures in an isolated local/test environment; verify the assistant reports failure rather than announcing success.

## Limitations and trade-offs

- This is not HIPAA-compliant or suitable for real patient information.
- API, dashboard, call-history endpoint, and webhook currently lack authentication/authorization and webhook signature verification. The call-ID header is association metadata, not authentication.
- Phone/name/date-of-birth matching is not secure identity authentication. Lookup results must not be used as a production access-control mechanism.
- Unconfirmed intake lives in the voice conversation. A dropped call before saving loses that draft; cross-call resume is not implemented.
- If a save commits but the connection drops before confirmation, the record remains. Creation is not idempotent: retries after uncertain timeouts can create duplicates. Transcript upserts prevent duplicate call rows, not duplicate patient rows.
- Duplicate detection is assistant-driven, not a database uniqueness guarantee. Concurrent calls can still create duplicate patients.
- Call linking requires the exact Vapi call-ID header and end-of-call report configuration. Historical calls are not backfilled automatically. Missing reports have no reconciliation job.
- One call links to one patient. Registering several people within one call can overwrite that call's patient association and is outside the intended flow.
- Transcription can mishear names/numbers. Prompt rules support spelling and corrections but cannot guarantee recognition or model compliance. Interruptions depend on Vapi speech settings.
- Phone validation checks structure, not ownership, carrier assignment, or reachability. Addresses/ZIP codes are not verified against postal records. Territories beyond the configured state-code list are unsupported.
- Soft deletion hides records but retains them and associated transcripts. There is no retention policy, purge workflow, or audit trail of every historical field change.
- No appointment scheduling, verified multilingual flow, audio archive, or automated test suite is included.
- Patient listing has no pagination; the dashboard uses manual refresh and has no editing or transcript UI.
- Schema setup uses `create_all`, not versioned migrations. Dependencies are not pinned in the initial requirements file.
- Routes and business operations share `main.py`; further service-layer separation would improve maintainability.
- SQLite is intended for local development; deployed persistence depends on a correctly configured PostgreSQL URL. Health checking currently verifies application liveness only.
- Funding, vendor access, and service uptime must be maintained until review.

## Next steps

Add authentication and webhook verification; extract a patient service layer; implement creation idempotency and durable intake drafts; add migration/version management, pagination, automated API/webhook tests, call-report reconciliation, transcript dashboard views, and a deliberate data-retention policy.
