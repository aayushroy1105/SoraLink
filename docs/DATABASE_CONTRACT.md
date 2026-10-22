# SoraLink — Database Contract

**Database:** SQLite  
**Storage authority:** Backend  
**Operating mode:** Offline-first, single-host deployment

This document defines the canonical database schema for the SoraLink MVP. The backend must validate every state-changing operation and persist changes before notifying connected clients.

## 1. Database Configuration

- Database file: `instance/soralink.db`
- Enable SQLite WAL mode.
- Set a connection timeout of 20 seconds.
- Use parameterized SQL queries.
- Keep write transactions short.
- Enable foreign-key enforcement on every connection.
- Store timestamps as UTC Unix timestamps in milliseconds using INTEGER columns.
- Never use SQLite text comparison to determine expiry when timestamps use a different format.
- Create tables and indexes through `schema.sql`.
- Populate demo data using `seed_db.py`.

## 2. `seat_invites`

Stores authorized demo seat invitations.

| Column | Type | Rules |
|---|---|---|
| seat_label | TEXT | Primary key, e.g. `18A` |
| demo_code_hash | TEXT | Required |
| enabled | INTEGER | NOT NULL, default 1 |
| created_at | INTEGER | UTC Unix milliseconds |

Rules:
- Seed the demo seats required for testing.
- Store a hash of the demo code rather than the plaintext code.
- A passenger's seat must be obtained from the validated invitation and authenticated session.
- Never trust a seat label supplied in a request body as authentication.

## 3. `sessions`

Stores authenticated passenger and crew sessions.

| Column | Type | Rules |
|---|---|---|
| session_id | TEXT | Primary key, cryptographically random |
| role | TEXT | `passenger` or `crew` |
| seat_label | TEXT | Nullable; required for passenger sessions |
| crew_id | TEXT | Nullable; used for crew identity |
| created_at | INTEGER | UTC Unix milliseconds |
| expires_at | INTEGER | UTC Unix milliseconds |
| revoked_at | INTEGER | Nullable; UTC Unix milliseconds |

Rules:
- Validate session expiry and revocation on protected requests.
- Passenger sessions must be bound to one seat.
- Crew sessions must not be assigned a passenger seat.
- Enforce role authorization on both REST and Socket.IO connections.
- Never expose session secrets to other users.

## 4. `requests`

Stores passenger service and assistance requests.

| Column | Type | Rules |
|---|---|---|
| request_id | TEXT | Primary key |
| seat_label | TEXT | Required |
| intent_id | TEXT | Required; references the approved intent catalog at application level |
| priority | TEXT | `URGENT` or `ROUTINE` |
| status | TEXT | `PENDING`, `ACKNOWLEDGED`, or `COMPLETED` |
| created_at | INTEGER | UTC Unix milliseconds |
| updated_at | INTEGER | UTC Unix milliseconds |
| acknowledged_at | INTEGER | Nullable |
| completed_at | INTEGER | Nullable |
| acknowledged_by | TEXT | Nullable crew identifier |

Rules:
- Generate request IDs on the server.
- Derive priority from approved server-side intent metadata.
- Sort urgent requests before routine requests, then by creation time.
- Merge duplicate active requests for the same seat and intent.
- A completed request must not prevent a later new request for the same intent.
- Use transactions to prevent simultaneous duplicate submissions.

## 5. Active-Request Deduplication

An active request is a request whose status is `PENDING` or `ACKNOWLEDGED`.

Before creating a request:
1. Start a database transaction.
2. Check for an active request matching the authenticated seat and intent.
3. If one exists, return that existing request.
4. Otherwise, create a new request.
5. Commit the transaction.
6. Emit the appropriate Socket.IO notification after commit.

Use an index to support efficient active-request lookups.

Do not rely exclusively on a browser-side disabled button to prevent duplicates.

## 6. `request_events`

Stores an audit trail of request changes.

| Column | Type | Rules |
|---|---|---|
| event_id | TEXT | Primary key |
| request_id | TEXT | Required; foreign key to `requests` |
| actor_role | TEXT | `passenger`, `crew`, or `system` |
| actor_id | TEXT | Nullable |
| event_type | TEXT | Required |
| event_data_json | TEXT | Valid JSON |
| created_at | INTEGER | UTC Unix milliseconds |

Examples of `event_type`:
- `REQUEST_CREATED`
- `REQUEST_DEDUPLICATED`
- `REQUEST_ACKNOWLEDGED`
- `REQUEST_COMPLETED`
- `FOLLOW_UP_SENT`

Record state transitions and significant actions in the same transaction as the associated database update.

## 7. `voice_previews`

Stores temporary transcription and classification previews.

| Column | Type | Rules |
|---|---|---|
| preview_id | TEXT | Primary key |
| session_id | TEXT | Required; foreign key to `sessions` |
| transcript | TEXT | Required |
| proposed_intent_id | TEXT | Nullable |
| confidence | REAL | Between 0 and 1 |
| alternatives_json | TEXT | Valid JSON |
| created_at | INTEGER | UTC Unix milliseconds |
| expires_at | INTEGER | UTC Unix milliseconds |
| consumed_at | INTEGER | Nullable; UTC Unix milliseconds |

Rules:
- Set preview expiry to 30 minutes after creation.
- Verify session ownership and expiry before confirmation.
- Validate the selected intent against the approved catalog.
- Prevent a preview from creating multiple independent requests.
- Delete expired previews periodically or during routine cleanup.
- Temporary audio files must be deleted after inference, even on failure.
- Never store raw audio permanently in this table.

## 8. `active_broadcasts`

Stores cabin announcements so passengers can recover active announcements after refreshes or reconnections.

| Column | Type | Rules |
|---|---|---|
| broadcast_id | TEXT | Primary key |
| pa_card_id | TEXT | Required; references an approved PA card at application level |
| active_status | INTEGER | NOT NULL, default 1 |
| created_by | TEXT | Required crew identifier |
| created_at | INTEGER | UTC Unix milliseconds |
| expires_at | INTEGER | Nullable; UTC Unix milliseconds |
| ended_at | INTEGER | Nullable; UTC Unix milliseconds |
| ended_by | TEXT | Nullable crew identifier |

Rules:
- Only crew may start or end broadcasts.
- Validate the PA card ID against the approved static dictionary.
- Persist the broadcast before emitting a Socket.IO event.
- Return only active, non-expired broadcasts to passengers.
- When ending a broadcast, update SQLite before notifying clients.
- The passenger client must dismiss a broadcast at its expiry time.
- A refreshed or newly connected passenger must fetch current active broadcasts from the server.

## 9. Indexes

Create indexes for:
- `requests(status, priority, created_at)`
- `requests(seat_label, intent_id, status)`
- `request_events(request_id, created_at)`
- `voice_previews(session_id, expires_at)`
- `active_broadcasts(active_status, expires_at)`
- `sessions(expires_at, revoked_at)`

Use partial unique indexes where supported and appropriate, but ensure the deduplication design does not prevent a new request after completion.

## 10. Request Lifecycle

Valid transitions:

`PENDING → ACKNOWLEDGED → COMPLETED`

Rules:
- Only authorized crew may acknowledge or complete a request.
- A request cannot be completed before acknowledgement.
- Repeated acknowledgement or completion requests must be handled idempotently.
- Invalid transitions must return a conflict response without changing stored state.
- Every successful transition must update `updated_at` and append a `request_events` record.

## 11. Demo Database Seeding

`seed_db.py` must:
1. Initialize the schema.
2. Populate the agreed demo seat invitations.
3. Create or configure the demo crew credentials securely.
4. Ensure approved JSON catalogs are available.
5. Avoid destructive database resets during normal application startup.

Any destructive reset must require an explicit development/demo-reset option.

## 12. Integration Requirements

- `database.py` owns database connection and transaction helpers.
- `auth.py` owns session validation and role enforcement.
- `requests_service.py` owns request creation, deduplication, prioritization, and state transitions.
- `broadcast_service.py` owns PA broadcast persistence and expiry.
- `voice.py` owns voice preview persistence and confirmation integration.
- `app.py` wires routes and Socket.IO events; it must not duplicate business rules.

All modules must use these shared table names, column names, status values, and timestamp formats.

## 13. Acceptance Criteria

- Database initialization succeeds from a clean checkout.
- Foreign-key enforcement is active.
- Concurrent duplicate requests do not create multiple active records for the same seat and intent.
- Urgent requests sort before routine requests.
- Status transitions and event records remain consistent.
- Expired voice previews cannot be confirmed.
- Active PA announcements survive page refreshes.
- Session expiry and revocation prevent further access.
- The core workflow remains available without internet access.

