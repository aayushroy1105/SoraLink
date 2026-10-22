# SoraLink — Master Implementation Plan v1.0

Prepared: 22 October 2026
Purpose: Complete project specification, team workflow, implementation sequence, and testing contract.

This is the master specification for building SoraLink. It is intended to be the shared reference for all four teammates and their separate AI chats.

The goal is not merely to build four modules. The goal is to build one working, integrated application in which a passenger can communicate a request to cabin crew despite an accent or language barrier, the crew can respond, and both sides see the correct status—even when the internet is unavailable.

The project addresses Japan Airlines problem statement JAL-PS-02: “Enabling Effective Passenger-Crew Communication Across Accents & Language Barriers.” The in-person hackathon is listed for 24–25 October 2026. The organizer's final schedule and rules remain authoritative: https://hack.tslasconnect.com/

---

# PART 1 — RULES THAT GOVERN THE ENTIRE PROJECT

These rules apply to all teammates, all four AI chats, and every code change.

## 1.1 The final product we are building

SoraLink is a local-network, offline-first passenger-to-crew communication web application.

One laptop runs the server and all core processing. Passengers and crew use their phones or other devices to access the application through the same local Wi-Fi network.

The system has five central capabilities:

1. Passenger requests: A passenger can select a visual request card, type a request, or speak a request.
2. AI-assisted voice input: A local speech-recognition model transcribes speech, and a local intent classifier suggests the most likely request.
3. Crew dashboard: Cabin crew can see incoming requests, acknowledge them, send a predefined response, and mark requests complete.
4. Live updates: Changes are reflected across connected passenger and crew devices.
5. Cabin announcements: Crew can activate and end predefined bilingual announcement cards, and passenger devices recover the correct announcement state after reconnecting.

Voice input is an additional convenience, not a dependency for basic operation. If speech recognition fails or the AI model is unavailable, passengers must still be able to communicate using visual cards or typed input.

## 1.2 The golden rule: the backend is authoritative

Neither the frontend nor an AI model is allowed to make security-critical decisions.

- A passenger's seat: server-side authenticated session.
- Whether a user is passenger or crew: server-side authenticated session.
- Whether a passenger may access a request: backend ownership check.
- Whether a request is urgent: reviewed server-side intent rules.
- Whether a request was saved: SQLite database.
- Current request status: SQLite database.
- Whether a PA announcement is active: SQLite database and server expiry checks.
- What response text can be sent: reviewed response dictionary.
- What AI intent is selected: passenger confirmation, validated by backend.

The model may suggest `water_request`. It must not independently create a request, decide who receives it, invent a crew response, or mark it as completed.

## 1.3 Required versus optional scope

P0 — MUST WORK FOR THE DEMO
- Passenger and crew authentication.
- Visual request cards.
- Request creation and persistence.
- Live crew dashboard.
- Acknowledge, reply, and complete actions.
- Passenger request status.
- Server-side role and ownership checks.
- Local networking and offline operation.
- Reconnect recovery.
- One integrated, runnable application.

P1 — CORE DIFFERENTIATOR
- Local Whisper transcription.
- Local intent classification.
- Transcript review and editing.
- Suggested intent confirmation.
- Alternative intents for uncertain classifications.
- Predefined bilingual crew response cards.
- Persisted PA announcements and expiry recovery.

P2 — ADD ONLY AFTER P0 AND P1 ARE STABLE
- More polished visual design.
- Optional read-aloud of replies.
- Additional visual request cards.
- Better evaluation reports and demo diagnostics.
- Small usability improvements that do not threaten the core flow.

Do not sacrifice P0 security, persistence, or reliability to add another AI feature.

## 1.4 Explicit non-goals

Do not build these unless the core system is complete and the team explicitly agrees to the change:
- A cloud backend or cloud-dependent AI pipeline.
- A production airline passenger database integration.
- Real airline booking, seat assignment, or payment functionality.
- An open-ended AI chatbot that invents operational responses.
- Automatic generation of safety announcements.
- A complex frontend framework introduced late in the project.
- An external database service requiring internet access.
- A claim that every accent or language is supported.
- A claim that the prototype replaces actual cabin crew or airline safety procedures.

SoraLink is a hackathon prototype. High-priority requests are surfaced for crew attention, but actual emergency handling remains a crew responsibility.

---

# PART 2 — THE COMPLETE PRODUCT WORKFLOW

Build and test the application around these user journeys.

## 2.1 Passenger journey: visual request

1. The passenger opens the SoraLink passenger page.
2. They log in with their seat label and demo invitation code.
3. The homepage presents large visual request cards.
4. The passenger taps a card, such as Water.
5. The browser sends the selected intent to the backend.
6. The backend verifies the session, validates the intent, derives the priority, and creates a request in SQLite.
7. The backend commits the transaction.
8. The backend sends a Socket.IO notification to the crew dashboard.
9. The passenger sees the saved request and its current status.
10. Crew acknowledges the request, sends a predefined response, and eventually marks the request complete.
11. The passenger receives the update in real time or recovers it from the server after reconnecting.

This is the first end-to-end feature the team must complete. It must work before AI integration begins.

## 2.2 Passenger journey: voice request

1. The passenger taps Speak.
2. The browser asks for microphone permission if required.
3. The passenger records a short utterance.
4. The browser uploads the recording to `POST /api/voice/preview`.
5. The server validates the authenticated session, recording size, MIME type, and inference queue capacity.
6. A locally loaded Whisper model transcribes the recording.
7. A locally loaded SetFit classifier suggests one of the approved intent IDs.
8. The server returns a preview containing the transcript, proposed intent, relevant attributes, alternatives, and a flag indicating whether the passenger needs to choose.
9. The passenger reviews the result and may correct the transcript, choose an alternative, or cancel.
10. The passenger taps Confirm & Send.
11. The backend validates the preview, ownership, expiry, selected intent, and attributes.
12. The backend creates the request and its event history in a database transaction.
13. The backend marks the preview consumed and commits the transaction.
14. The server notifies the crew dashboard.
15. The passenger sees the request and follows its status.

Recording must never directly create a request without passenger confirmation.

## 2.3 Passenger journey: uncertain voice recognition

1. The server returns candidate intents instead of pretending that one is definitely correct.
2. The passenger sees the proposed interpretation and up to two alternatives, plus None of these.
3. The passenger can edit the transcript and classify it again.
4. If the result is still unreliable, the passenger can select a visual card or type a request.
5. No final request is sent until the passenger confirms their choice.

The interface must not show a raw model score as a guaranteed probability. A similarity score or uncalibrated classifier score is not the same thing as a calibrated probability.

## 2.4 Crew journey

1. The crew member opens the crew page and logs in through the crew authentication flow.
2. The crew page fetches the current request list from the backend.
3. New requests appear through Socket.IO.
4. Requests are ordered with urgent requests first, then older requests before newer requests within the same priority.
5. Crew acknowledges a request.
6. Crew selects a predefined response.
7. The passenger sees the response.
8. Crew marks the request completed when appropriate.
9. The updated state is persisted in SQLite.

The crew dashboard must also fetch a fresh snapshot after reconnection. Socket.IO events are a way to receive updates, not the only way to learn the current state.

## 2.5 PA announcement journey

1. A crew member selects a predefined announcement card.
2. The backend validates the crew session and card ID.
3. The backend creates an active announcement in SQLite.
4. The backend commits the transaction and broadcasts a notification to connected passenger devices.
5. Passenger pages show the announcement.
6. Crew can end the announcement manually, or it can become inactive when its expiry time passes.
7. When a passenger reconnects or returns to a suspended page, the page requests the active announcements again.
8. Ended or expired announcements are not shown as active.

An announcement's local browser timer is only for updating the user interface. It must not be the authority for changing the announcement's stored status.

---

# PART 3 — SYSTEM ARCHITECTURE

## 3.1 The architecture

Passenger phone and crew phone connect over the same local Wi-Fi/LAN to a SoraLink host laptop. The host runs Flask and Flask-SocketIO. The server connects to:
- Auth and API handlers.
- Request service.
- PA broadcast service.
- SQLite database.
- Local voice-preview pipeline: Whisper followed by SetFit classifier.

The server runs on one host laptop. Phones connect through a local network. The network needs to remain active even when the WAN connection is unavailable.

Architecture diagram:

```text
Passenger phone                  Crew phone
      |                               |
      +---------- Local Wi-Fi/LAN ----+
                      |
                      v
             SoraLink host laptop
           Flask + Flask-SocketIO
                      |
       +--------------+---------------+
       |              |               |
       v              v               v
  Auth & APIs     Request service   PA service
       |              |               |
       +--------------+---------------+
                      |
                      v
               SQLite database
                      ^
                      |
               Voice preview API
                      |
               Local voice pipeline
                      |
             Whisper -> SetFit classifier
```

Offline means no internet dependency; it does not mean the devices can have no network connection. Passenger devices still need the local network to reach the host laptop.

## 3.2 Technology choices

- Frontend: HTML, CSS, JavaScript — passenger and crew interfaces.
- Server: Python + Flask — routes, validation, authentication.
- Live communication: Flask-SocketIO — server-to-browser updates.
- Database: SQLite — sessions, requests, event history, PA state.
- Speech recognition: local Whisper implementation — audio to transcript.
- Intent classification: SetFit with a multilingual sentence-transformer — transcript to suggested intent.
- Storage format: JSON dictionaries — approved intents and fixed bilingual cards.
- Network: local Wi-Fi or hotspot — connect host and user devices.
- HTTPS: locally trusted certificate — secure browser context and microphone access.
- Test framework: pytest — backend, integration, and regression testing.

Start with a Python 3.11 virtual environment, and pin the dependency versions that are actually tested on the host computer. If one of the chosen AI libraries requires a different compatible Python version, resolve that before freezing dependencies.

For voice recognition, benchmark the actual host rather than promising speed in advance. `faster-whisper` is a portable candidate and uses PyAV for audio decoding; `mlx-whisper` is an alternative if the host is compatible Apple Silicon. Reference: https://github.com/SYSTRAN/faster-whisper

## 3.3 The request service is the shared core

All request creation methods must converge on the same backend request service:
- Visual card request.
- Typed request.
- Confirmed voice request.

Do not write three separate request-creation implementations. Create one request service responsible for validation, priority derivation, persistence, idempotency, event history, and notifications.

That decision prevents voice requests from bypassing the validation used by visual cards.

---

# PART 4 — REPOSITORY AND FILE STRUCTURE

Your leader should create one shared GitHub repository named `SoraLink` or `soralink`.

Proposed starting structure:

```text
SoraLink/
├── app.py
├── config.py
├── database.py
├── auth.py
├── voice.py
├── classifier.py
├── requests_service.py
├── broadcast_service.py
├── schema.sql
├── seed_db.py
├── requirements.txt
├── requirements-lock.txt
├── .gitignore
├── .env.example
├── README.md
├── docs/
│   ├── MASTER_IMPLEMENTATION_PLAN.md
│   ├── API_CONTRACT.md
│   ├── DATABASE_CONTRACT.md
│   ├── SOCKET_EVENTS.md
│   ├── INTENT_CATALOG.md
│   ├── TEST_PLAN.md
│   ├── NETWORK_SETUP.md
│   └── DECISIONS.md
├── data/
│   ├── intents.json
│   ├── pa_cards.json
│   └── crew_responses.json
├── models/
│   └── README.md
├── templates/
│   ├── login.html
│   ├── passenger.html
│   └── crew.html
├── static/
│   ├── css/
│   │   └── app.css
│   ├── js/
│   │   ├── passenger.js
│   │   ├── crew.js
│   │   └── socket.js
│   └── vendor/
│       └── socket.io.min.js
├── scripts/
│   ├── download_models.py
│   ├── train_classifier.py
│   └── evaluate_voice.py
├── tests/
│   ├── conftest.py
│   ├── test_auth.py
│   ├── test_requests.py
│   ├── test_voice.py
│   ├── test_broadcasts.py
│   ├── test_socket_reconnect.py
│   └── test_offline_readiness.py
└── instance/
    └── soralink.db
```

### Important directory rules

- `instance/soralink.db` is runtime data; it must not be committed.
- `.env` is local configuration and must not be committed.
- `.env.example` contains placeholder values only.
- Model weights are downloaded or copied to the host before the offline demo. Do not blindly commit large weights into ordinary Git history.
- The local Socket.IO JavaScript client must be vendored and tested before the event; the browser must not depend on a runtime CDN.
- Keep `docs/` files synchronized with actual implementation decisions.

### Minimum `.gitignore` entries

```gitignore
.env
.venv/
__pycache__/
.pytest_cache/
*.py[cod]

instance/*.db
instance/*.db-shm
instance/*.db-wal

models/*
!models/README.md

*.log
.DS_Store
```

Adapt this to the exact repository layout. Never add real credentials to the repository.

---

# PART 5 — FOUR TEAMMATES, FOUR RESPONSIBILITIES

This is the division of work. Each person should primarily change their assigned files, but everyone must follow the shared contracts.

## Teammate A — AI and audio

Owns:
- `voice.py`
- `classifier.py`
- `scripts/download_models.py`
- `scripts/train_classifier.py`
- `scripts/evaluate_voice.py`
- AI-specific tests in coordination with D

Responsible for:
1. Choosing and benchmarking the local Whisper implementation.
2. Loading model weights once at startup where practical.
3. Implementing transcription and transcript normalization.
4. Implementing the SetFit classifier.
5. Producing the candidate list and uncertainty outcome.
6. Mapping the classification to approved intent IDs.
7. Returning structured results; not directly creating requests.
8. Using unique temporary audio files.
9. Deleting audio files in a `finally` cleanup path, including error paths.
10. Controlling inference concurrency with a bounded queue or semaphore.
11. Documenting actual model dependencies and offline requirements.
12. Evaluating recognition on representative sample recordings.

A must not:
- Change authentication or request ownership rules.
- Create database requests directly.
- Invent new intent IDs without a shared-contract change.
- Invent crew responses.
- Claim support for accents or languages that have not been evaluated.

Definition of done: The backend can call a single voice-preview function and receive a normalized transcript, candidate intent list, uncertainty state, and any needed attributes. The function must not create a final passenger request.

## Teammate B — Backend, authentication, database, and realtime

Owns:
- `app.py`
- `config.py`
- `database.py`
- `auth.py`
- `requests_service.py`
- `broadcast_service.py`
- `schema.sql`
- `seed_db.py`

Responsible for:
1. Flask initialization and configuration.
2. Database schema, indexes, and initialization.
3. Passenger and crew login.
4. Session expiration and revocation.
5. Server-side role and ownership authorization.
6. All API endpoint contracts.
7. Request creation, state transitions, and event history.
8. Idempotency and safe error responses.
9. Socket.IO authentication and room assignment.
10. Broadcasting only after successful database commits.
11. PA persistence and server-side expiry checks.
12. Session and request data validation.
13. Stable interfaces for A and C to use.

B must not:
- Accept a client-supplied seat or priority as authoritative.
- Permit arbitrary room names from browsers.
- Hold a database write transaction while running AI inference.
- Delete request history when the demo seed script is rerun.
- Return stack traces, credentials, or local filesystem paths to clients.

Definition of done: Visual request, crew acknowledgement, fixed reply, completion, reconnect recovery, and PA persistence work without any AI component.

## Teammate C — Passenger and crew frontend

Owns:
- `templates/`
- `static/css/app.css`
- `static/js/passenger.js`
- `static/js/crew.js`
- `static/js/socket.js`

Responsible for:
1. Passenger login and request interface.
2. Visual request cards and typed input.
3. Microphone capture and permission handling.
4. Transcript-review interface.
5. The single explicit Confirm & Send action.
6. Alternative-intent and editing flow.
7. Passenger status and reply display.
8. Crew queue and status controls.
9. PA announcement cards.
10. Reconnection indicators and request snapshots.
11. Accessible mobile layout.
12. Handling loading, empty, network, model, and expiry states.

C must not:
- Trust browser data for role, seat, priority, or authorization.
- Directly modify the database.
- Mark requests complete without a backend confirmation.
- Send an unconfirmed voice preview as a final request.
- Automatically initiate speech playback from an incoming socket event.

Definition of done: Passenger and crew interfaces work against B's agreed API using realistic request payloads, with no hardcoded success states pretending the server saved data.

## Teammate D — Integration, QA, offline setup, and reliability

Owns:
- `tests/`
- `docs/TEST_PLAN.md`
- `docs/NETWORK_SETUP.md`
- `README.md`
- Integration fixes coordinated with module owners

D is not a late-stage-only tester. D must start as soon as the first API contract exists.

Responsible for:
1. Keeping the contract documentation up to date.
2. Testing the first vertical slice as soon as it exists.
3. Checking imports and configuration across modules.
4. Testing database contention and duplicate submissions.
5. Testing reconnects and stale browser state.
6. Checking role-based access and request ownership.
7. Verifying microphone access on actual devices.
8. Testing WebSocket operation and fallback behavior.
9. Testing offline startup with the WAN disconnected.
10. Verifying all models and assets are local.
11. Preparing the demo runbook.
12. Recording actual test results and unresolved issues.

D must not:
- Silently redefine APIs or intent IDs.
- Make a passing test out of an untested feature.
- Wait until the last hours to try integrating the modules.
- Treat “it works on my laptop” as proof that phone access works.

Definition of done: The integrated application can be launched by following the README, the priority acceptance tests pass, and every known limitation is documented.

---

# PART 6 — TEAM WORKFLOW AND GITHUB OPERATING PROCEDURE

## 6.1 Why there are four separate AI chats

Each teammate gets a branched chat containing the same master specification plus their role assignment.

The chats are separate workspaces, not a synchronized shared memory system. A decision made in Teammate A's chat does not automatically update B, C, D, or the master specification.

Therefore:
- All chats follow the same master plan.
- All chats follow the same API, database, intent, and event contracts.
- A material design change must be written into the GitHub `docs/` files.
- The change must be communicated to all affected teammates.
- No AI chat is allowed to unilaterally override a frozen shared contract.

## 6.2 Repository setup

The leader creates the repository and adds all four teammates as collaborators.

Recommended first files:
1. `README.md`
2. `docs/MASTER_IMPLEMENTATION_PLAN.md`
3. `docs/API_CONTRACT.md`
4. `docs/DATABASE_CONTRACT.md`
5. `docs/SOCKET_EVENTS.md`
6. `.gitignore`
7. `.env.example`
8. `requirements.txt`

The repository, not any individual AI chat, becomes the source of truth for actual code and accepted technical decisions.

## 6.3 Branch and commit conventions

Use `main` as the stable integrated branch.

Recommended feature branches:

```text
main
├── feature/ai-audio
├── feature/backend
├── feature/frontend
└── feature/integration-qa
```

Suggested commit names:

```text
feat: add passenger authentication
feat: add request creation endpoint
feat: add local voice preview
feat: add passenger request cards
test: add request ownership checks
fix: restore active announcements after reconnect
docs: clarify socket event contract
```

A simple collaboration loop is enough:
1. A teammate makes changes only in their working branch.
2. They run the relevant tests.
3. They commit and push.
4. The team checks the diff and interface compatibility.
5. The change is merged into `main`.
6. D runs integration checks on the merged code.

If time is extremely short, the leader can approve a smaller, direct merge process. Do not give up knowing which files changed, what tests ran, or how to restore a working version.

## 6.4 The rule for cross-owner files

“Do not edit another member's files” is a useful default, not an absolute rule.

Sometimes a cross-module fix is necessary. In that case:
1. Explain why the change is necessary.
2. Notify the file owner.
3. Keep the change narrowly scoped.
4. Update any affected contract.
5. Run both the module's tests and the integrated test.

Changing a shared contract is a bigger decision than fixing a bug in one module.

## 6.5 Definition of a frozen contract

Before independent implementation, freeze these items:
- The 15 intent IDs.
- The priority mapping.
- The request statuses and legal transitions.
- The database columns and timestamp conventions.
- Endpoint paths and HTTP methods.
- JSON request and response shapes.
- Socket.IO event names and payload shapes.
- Fixed response-card IDs.
- Fixed PA-card IDs.
- Preview TTL and audio upload limits.
- The folder and module ownership boundaries.

A change after freeze requires a documented decision in `docs/DECISIONS.md` and an update to the affected contract.

---

# PART 7 — FREEZE THE SHARED DATA CONTRACTS

This is the most important agreement between the four developers. A writes the voice pipeline, B writes the backend, C writes the frontend, and D integrates them. All four must agree on the same vocabulary and formats.

## 7.1 Intent catalog: 15 bounded intents

The project requires 15 bounded intents: four urgent and eleven routine. The following IDs are the proposed canonical v1 set for the implementation. If your previously submitted solution deck or an existing project file has a different approved catalog, reconcile it before coding, then freeze one catalog. Do not let each teammate invent their own IDs.

URGENT:
- `medical_emergency` — Medical help is needed.
- `breathing_difficulty` — Trouble breathing.
- `injury_or_bleeding` — Injury, bleeding, or significant pain.
- `safety_security_concern` — Immediate safety or security concern.

ROUTINE:
- `water_request` — Request water or another approved drink.
- `meal_request` — Meal or food request.
- `blanket_request` — Request a blanket.
- `pillow_request` — Request a pillow.
- `restroom_assistance` — Help related to restroom use.
- `seat_assistance` — Help with seat, tray, or seat controls.
- `baggage_assistance` — Help with cabin baggage.
- `temperature_comfort` — Too hot, too cold, or comfort adjustment.
- `entertainment_help` — Help with the entertainment system.
- `language_assistance` — Help communicating across a language barrier.
- `other_request` — Request not represented by another approved intent.

The IDs are permanent for this version once the contract is frozen. Display labels, translations, and phrases can be updated without changing the IDs.

These are routing labels for a prototype, not a medical diagnosis. Any possible urgent input should remain available for crew review. Do not let the classifier silently drop a potentially urgent request because it scores below a threshold.

## 7.2 What goes in `data/intents.json`

Each intent should include:
- Stable `intent_id`.
- Display labels in supported languages.
- Priority defined by the server-approved catalog.
- Description.
- Training examples for classification.
- Allowed attribute keys and allowed values, where applicable.
- Optional reviewed examples of alternative phrasing.

Conceptual entry:

```json
{
  "intent_id": "water_request",
  "priority": "ROUTINE",
  "labels": {
    "en": "Water",
    "ja": "水"
  },
  "allowed_attributes": {
    "temperature": ["COLD", "ROOM", "WARM"]
  }
}
```

This example illustrates the format; finalize translations and all entries in the actual file.

Keep the catalog valid JSON. The backend should validate it at startup and fail clearly if a required ID is missing, duplicated, or has an unsupported priority.

## 7.3 Attribute contract

Attributes are optional structured details attached to a request.

Example:

```json
{
  "intent_id": "water_request",
  "attributes": {
    "temperature": "WARM"
  }
}
```

Rules:
- Attributes must be JSON objects, not arbitrary executable data.
- The backend validates keys and values against the approved intent schema.
- The frontend cannot submit new arbitrary attribute keys and assume that the server will accept them.
- Unknown attributes are rejected or removed according to one documented server policy; use rejection for invalid values during v1.
- Keep the attribute payload small.
- Never use attributes to override the server-derived role, seat, priority, owner, or request status.

## 7.4 Status and priority vocabulary

Request statuses:
```text
PENDING
ACKNOWLEDGED
COMPLETED
CANCELLED
```

Priorities:
```text
URGENT
ROUTINE
```

Voice-preview outcomes:
```text
SUGGESTED
REQUIRES_CHOICE
UNRELIABLE
```

These voice outcomes describe the model's result, not the request's status.

PA announcement statuses:
```text
ACTIVE
ENDED
EXPIRED
```

Do not invent synonyms such as `DONE`, `RESOLVED`, `HIGH`, `NORMAL`, `IN_PROGRESS`, or `FINISHED` in one module. If a new state is truly necessary, update the shared contract first.

## 7.5 Valid request state transitions

- New request → backend creates request → `PENDING`.
- `PENDING` → crew acknowledges → `ACKNOWLEDGED`.
- `ACKNOWLEDGED` → crew completes → `COMPLETED`.
- `PENDING` → passenger cancels own request → `CANCELLED`.
- `ACKNOWLEDGED` → passenger cancellation is rejected in v1.
- `COMPLETED` → any status change is rejected.
- `CANCELLED` → any status change is rejected.

Sending a crew reply does not automatically complete the request. It can remain `ACKNOWLEDGED` until the crew explicitly completes it.

Every accepted transition must update the request and create a request-event record. Invalid transitions return a defined error and do not mutate the stored request.

---

# PART 8 — DATABASE CONTRACT

## 8.1 SQLite is the source of truth

Use SQLite on the host laptop's local disk.

Do not place the database on a network drive. All users access the same database through the Flask server, not by opening the database file themselves.

Enable foreign-key enforcement on each database connection, and initialize WAL mode once during database setup.

## 8.2 Timestamp convention — critical

All persisted timestamps use UTC Unix epoch milliseconds stored as SQLite integers.

Use explicit names:
```text
created_at_ms
updated_at_ms
expires_at_ms
ended_at_ms
consumed_at_ms
revoked_at_ms
```

Python current timestamp:

```python
import time

now_ms = time.time_ns() // 1_000_000
```

Use the same convention in every module.

Do not compare ISO timestamp strings from Python with SQLite's `CURRENT_TIMESTAMP` strings. Mixed string formats and time zones can produce incorrect expiry decisions.

The frontend receives integer milliseconds and can use `new Date(timestamp_ms)` to display a human-readable date. Any browser timer must still check the absolute expiry timestamp before changing the UI.

## 8.3 Table 1: `sessions`

Purpose: track authenticated passenger and crew sessions.

- `session_id` — unique random session identifier; primary key.
- `role` — `passenger` or `crew`.
- `seat_label` — seat label for passengers; null for crew.
- `token_hash` — unique hash of the opaque session token.
- `created_at_ms` — session creation time.
- `expires_at_ms` — session expiry time.
- `revoked_at_ms` — null unless revoked.
- `last_seen_at_ms` — last successful activity, if tracked.

Rules:
- The raw token is not stored in SQLite.
- The raw token is placed in an HttpOnly cookie after login.
- The backend checks expiry and revocation on every protected request.
- Expiring a session must not erase that user's prior requests or event history.

## 8.4 Table 2: `seat_invites`

Purpose: control demo seat registration.

- `invite_id` — unique primary key.
- `seat_label` — intended seat.
- `code_hash` — hash of the invitation code.
- `expires_at_ms` — optional expiry.
- `used_at_ms` — set when a single-use code is redeemed.
- `is_reusable` — whether the code may be used more than once.
- `is_active` — whether the invite remains valid.

For a demo, a shared code such as `DEMO26` can be used as a convenience. It is not strong identity authentication. Prefer unique per-seat codes or QR links when practical.

The server must check that the seat exists in the seed data and that its invitation code is valid. Do not trust a seat label submitted by the browser after login.

## 8.5 Table 3: `requests`

Purpose: store every passenger request and its current state.

- `request_id` — unique request ID; primary key.
- `client_request_id` — idempotency ID generated by the browser.
- `owner_session_id` — authenticated session that created it.
- `seat_label` — server-captured seat snapshot.
- `intent_id` — one of the approved intent IDs.
- `attributes_json` — validated structured attributes.
- `priority` — server-derived `URGENT` or `ROUTINE`.
- `status` — one approved request status.
- `created_at_ms` — creation time.
- `updated_at_ms` — last update time.
- `acknowledged_by` — crew session ID, if acknowledged.
- `completed_at_ms` — completion time, if completed.
- `crew_reply_id` — latest predefined reply ID, if any.
- `crew_reply_text_en` — latest English reply text, if any.
- `crew_reply_text_ja` — latest Japanese reply text, if any.

Constraints:
- Primary key on `request_id`.
- Unique constraint on `(owner_session_id, client_request_id)`.
- Foreign key to the owning session.
- Allowed values for `priority` and `status` should be constrained.
- Index status/priority/time for the crew queue.
- Index owner/time for passenger history.

The backend snapshots the seat label when creating the request. Do not retrieve a passenger's current seat from a later browser payload.

## 8.6 Table 4: `request_events`

Purpose: record the history of request actions.

- `event_id` — unique event ID.
- `request_id` — related request.
- `actor_session_id` — session that performed the action, if applicable.
- `event_type` — approved event type.
- `payload_json` — small validated event details.
- `created_at_ms` — event timestamp.

Allowed `event_type` values:
```text
CREATED
ACKNOWLEDGED
REPLY_SENT
COMPLETED
CANCELLED
```

Event rows are created in the same transaction as the associated request mutation. Never create a success notification first and then attempt to save the database change.

## 8.7 Table 5: `voice_previews`

Purpose: temporarily store an authenticated voice-preview result until it is confirmed or expires.

- `preview_id` — unique preview ID.
- `owner_session_id` — session that created the preview.
- `transcript` — recognized transcript.
- `suggested_intent_id` — suggested intent, if available.
- `confidence_score` — raw model score or measured confidence, documented clearly.
- `candidates_json` — candidate intent IDs and scores.
- `created_at_ms` — creation time.
- `expires_at_ms` — expiry time.
- `consumed_at_ms` — null until successfully used to create a request.

The preview TTL is 30 minutes.

Rules:
- It is owner-bound.
- It expires after the TTL.
- It can be consumed once.
- The server rejects expired or consumed previews.
- The raw audio is deleted immediately after inference.
- The transcript and preview metadata may persist until expiry.
- An expired preview should not force the passenger to record again if the transcript is still visible. Allow text reclassification or visual-card selection.

## 8.8 Table 6: `pa_broadcasts`

Purpose: persist active announcements and their lifecycle.

- `broadcast_id` — unique broadcast ID.
- `pa_card_id` — ID from the approved PA dictionary.
- `active_status` — `ACTIVE`, `ENDED`, or `EXPIRED`.
- `created_at_ms` — creation time.
- `expires_at_ms` — optional expiry time.
- `ended_at_ms` — time the announcement ended.
- `created_by_session_id` — crew session that activated it.

An active announcement is returned only if its status is `ACTIVE` and it has not expired.

No permanent background cron job is required for the prototype. The server must filter expired announcements whenever it serves the active-announcements endpoint, and may lazily mark expired rows as `EXPIRED`.

## 8.9 Database connection rules

In `database.py`:
- Create a new connection per operation/request as appropriate.
- Do not share one SQLite connection across unrelated request threads.
- Use a connection timeout of 20 seconds.
- Set `PRAGMA foreign_keys = ON` on every connection.
- Set `PRAGMA busy_timeout = 20000` on every connection.
- Initialize WAL once and verify the returned journal mode.
- Set `synchronous = NORMAL` consistently if the team accepts the corresponding durability trade-off.
- Keep transactions short.
- Never hold a database write transaction while Whisper or SetFit runs.
- Commit before emitting Socket.IO events.
- Handle lock contention with bounded, controlled retry behavior or a retriable error.
- Do not blindly replay an operation whose transaction outcome is unknown.

WAL improves reader/writer coexistence; it does not make SQLite a multi-writer database. The design must still keep writes short and avoid unnecessary contention.

---

# PART 9 — API CONTRACT

The routes below are the agreed API interface. B implements them; C consumes them; A provides the voice/classification functions called by the relevant route; D verifies the contracts.

Every API response must be JSON unless the route explicitly serves an HTML page or an audio upload.

## 9.1 Common response and error format

Successful response:

```json
{
  "ok": true,
  "data": {}
}
```

Error response:

```json
{
  "ok": false,
  "error": {
    "code": "PREVIEW_EXPIRED",
    "message": "Your voice preview expired. Please classify the text again or select a request card."
  }
}
```

Do not expose tracebacks, environment variables, session tokens, model cache paths, raw server filesystem paths, or database internals in client-facing errors.

HTTP status codes:
- `200` — successful read or update.
- `201` — resource created.
- `400` — malformed request.
- `401` — no valid authenticated session.
- `403` — authenticated but not authorized for the operation.
- `404` — resource not found or not available to this caller.
- `409` — duplicate/state conflict where appropriate.
- `413` — upload exceeds the permitted size.
- `422` — valid JSON but invalid data/state transition.
- `503` — model unavailable or inference queue full.

Use stable machine-readable `error.code` values. Frontend logic should not parse human-readable error messages to decide what happened.

## 9.2 Route list

- `GET /healthz` — basic server health.
- `POST /api/auth/passenger` — passenger login.
- `POST /api/auth/crew` — crew login.
- `GET /api/auth/me` — return authenticated user's safe profile.
- `POST /api/auth/logout` — revoke current session.
- `POST /api/voice/preview` — transcribe audio and suggest intents.
- `GET /api/voice/previews/<preview_id>` — recover a valid current user's preview.
- `POST /api/classify` — optional typed-text classification.
- `POST /api/requests` — create a final confirmed request.
- `GET /api/my-requests` — list current passenger's requests.
- `GET /api/crew/requests` — crew queue snapshot.
- `PATCH /api/crew/requests/<request_id>` — acknowledge or complete a request.
- `POST /api/crew/requests/<request_id>/reply` — send a fixed response.
- `POST /api/requests/<request_id>/cancel` — cancel eligible request owned by passenger.
- `GET /api/pa/active` — return active unexpired PA cards.
- `POST /api/crew/pa/broadcast` — activate a PA card.
- `PATCH /api/crew/pa/broadcast/<broadcast_id>` — end a PA broadcast.

All routes under `/api/crew/` require a crew session. Passenger-specific routes require a passenger session. The backend performs authorization before reading or mutating the relevant resource.

## 9.3 Login contracts

Passenger login: `POST /api/auth/passenger`

Request:
```json
{
  "seat_label": "18A",
  "invite_code": "DEMO26"
}
```

Successful response:
```json
{
  "ok": true,
  "data": {
    "user": {
      "role": "passenger",
      "seat_label": "18A"
    }
  }
}
```

The session token is set in a cookie; it is not returned in the JSON body.

Crew login: `POST /api/auth/crew`

Request:
```json
{
  "crew_pin": "demo-pin-from-local-config"
}
```

Do not literally commit `demo-pin-from-local-config` as a live credential. Actual demo credentials must be kept in local configuration and documented safely.

After successful login, the backend creates a session and sends the cookie. The frontend redirects to the relevant page.

`GET /api/auth/me` returns the role and safe profile fields. It never returns the session token or token hash.

`POST /api/auth/logout` revokes the current session, clears the cookie, and causes protected requests and Socket.IO reconnections using that session to be rejected.

## 9.4 Voice-preview contract

`POST /api/voice/preview` receives multipart form data, not a JSON-only body.

Required field:
```text
audio: recorded audio file
```

The browser must send the actual media type recorded by the device. The backend maps supported, allowlisted media types to its own internal extension; it must not trust the uploaded filename.

Example successful result:

```json
{
  "ok": true,
  "data": {
    "preview_id": "random-preview-id",
    "transcript": "Could I have warm water, please?",
    "language": "en",
    "suggested_intent": {
      "intent_id": "water_request",
      "score": 0.88
    },
    "attributes": {
      "temperature": "WARM"
    },
    "candidates": [],
    "outcome": "SUGGESTED",
    "requires_choice": false,
    "expires_at_ms": 1792670000000
  }
}
```

The transcript, intent, score, and timestamp above are illustrative values, not claims about model performance.

Example uncertain result:

```json
{
  "ok": true,
  "data": {
    "preview_id": "random-preview-id",
    "transcript": "example transcript",
    "suggested_intent": null,
    "candidates": [
      {
        "intent_id": "water_request",
        "score": 0.54
      },
      {
        "intent_id": "meal_request",
        "score": 0.51
      }
    ],
    "outcome": "REQUIRES_CHOICE",
    "requires_choice": true,
    "expires_at_ms": 1792670000000
  }
}
```

All scores are examples. A's classifier must provide its documented score type, and the outcome thresholds must be selected using validation data rather than arbitrary confidence claims.

Voice failures should return a precise error code for at least:
- `AUDIO_MISSING`
- `AUDIO_TOO_LARGE`
- `AUDIO_TOO_LONG`
- `UNSUPPORTED_AUDIO_TYPE`
- `SILENCE_OR_NO_SPEECH`
- `MODEL_UNAVAILABLE`
- `MODEL_BUSY`
- `PREVIEW_EXPIRED`
- `PREVIEW_CONSUMED`
- `SESSION_INVALID`

## 9.5 Typed-text classification

`POST /api/classify` is optional but recommended if the team wants typed input to receive the same AI intent suggestions as voice input.

Request:
```json
{
  "text": "I need a blanket, please."
}
```

The backend returns intent suggestions and candidates using the same intent catalog. Typed-text classification must not create a request by itself.

The passenger selects the proposed intent or a visual card and then confirms. If the team elects not to implement typed classification in v1, typed input may instead be a fallback that asks the passenger to choose a visual request card. Do not leave C guessing which behavior is intended: select one before implementation and write it in `docs/API_CONTRACT.md`.

## 9.6 Final request creation

`POST /api/requests`

Confirmed voice request:
```json
{
  "client_request_id": "unique-id-for-this-user-action",
  "source": "VOICE",
  "preview_id": "random-preview-id",
  "intent_id": "water_request",
  "attributes": {
    "temperature": "WARM"
  }
}
```

Visual-card request:
```json
{
  "client_request_id": "unique-id-for-this-user-action",
  "source": "CARD",
  "preview_id": null,
  "intent_id": "water_request",
  "attributes": {}
}
```

In both cases, the server derives the user's seat from the authenticated session. It does not trust the browser to set the seat or priority.

The server must:
1. Require the correct role.
2. Validate `client_request_id`.
3. Apply idempotency checks.
4. If the source is `VOICE`, check the preview exists, belongs to the caller, has not expired, and has not been consumed.
5. Validate the intent ID.
6. Validate allowed attributes.
7. Derive priority from the trusted intent catalog.
8. Begin a short database transaction.
9. Insert the request and its `CREATED` event.
10. Mark the voice preview consumed, if applicable.
11. Commit the transaction.
12. Emit the relevant Socket.IO event.
13. Return the saved request.

If the same session repeats the same `client_request_id`, return the previously created request rather than creating a duplicate. If the same key is incorrectly reused for a different logical request, return a documented conflict instead of silently merging unrelated requests.

## 9.7 Passenger request history

`GET /api/my-requests` returns only requests owned by the current passenger session, ordered newest first. If the product needs history across re-login, the authentication/session model must explicitly support it; do not bypass ownership checks simply to make history appear.

The response should include request ID, intent, attributes, priority, status, creation/update timestamps, and the latest crew reply if one exists.

## 9.8 Crew queue snapshot

`GET /api/crew/requests` returns the current queue to an authenticated crew session.

Sort order:
1. Urgent before routine.
2. Older requests first within each priority.
3. Stable tie-breaking by request ID or another documented rule.

The crew dashboard should display at least request ID, seat, intent label, priority, created time, status, attributes, and latest reply.

## 9.9 Crew status changes

`PATCH /api/crew/requests/<request_id>`

Acknowledge:
```json
{
  "action": "ACKNOWLEDGE"
}
```

Complete:
```json
{
  "action": "COMPLETE"
}
```

The backend validates the current request state and performs an authorized state transition. Only crew may use this route. A passenger cannot make a request complete by changing browser data.

Each successful transition updates the request, inserts a corresponding event, commits, and then notifies relevant clients.

## 9.10 Crew reply contract

`POST /api/crew/requests/<request_id>/reply`

Request:
```json
{
  "reply_id": "reply_water_coming"
}
```

The backend looks up the ID in `data/crew_responses.json`, validates the request and the crew role, records the reply in request history, and updates the latest reply fields.

Do not accept arbitrary AI-generated response text from a browser. In v1, the crew selects a predefined reviewed response card.

## 9.11 PA contracts

`GET /api/pa/active` returns only announcements whose persisted status is active and whose expiry is absent or still in the future.

`POST /api/crew/pa/broadcast` request:
```json
{
  "pa_card_id": "seatbelt_reminder",
  "duration_seconds": 120
}
```

The backend validates the card, derives the expiry timestamp using server time, writes the announcement, commits, then emits the event.

`PATCH /api/crew/pa/broadcast/<broadcast_id>` request:
```json
{
  "action": "END"
}
```

Only crew can activate or end an announcement. The backend must not accept arbitrary PA text supplied by a passenger or generated by the model.

---

# PART 10 — SOCKET.IO CONTRACT AND LIVE UPDATES

B owns the server-side event handlers and rooms. C owns browser connection handling and UI updates. D verifies actual behavior after disconnects and reconnects.

## 10.1 Event names are fixed

- `new_request` — audience: `crew:dashboard` — a request was created.
- `request_updated` — audience: crew dashboard and request owner — request state changed.
- `crew_reply` — audience: request owner — crew response was recorded.
- `pa_broadcast_created` — audience: `passengers:all` — announcement became active.
- `pa_broadcast_ended` — audience: `passengers:all` — announcement ended.

Do not independently rename these in A, B, C, or D's code.

## 10.2 Connection authentication

The browser connects with the session cookie established by the login endpoint.

When a socket connection is attempted, the backend must:
1. Read the cookie.
2. Hash the raw token in the same way used by authentication.
3. Look up the matching session.
4. Check the session is not expired or revoked.
5. Assign the socket's room based on the verified role and session.
6. Reject unauthenticated connections.

Room assignment is server-controlled:
- Crew session: `crew:dashboard`.
- Passenger session: `passenger:<session_id>` and `passengers:all`.

The server must never accept a client-supplied room name as authority.

For rejected sessions, B and C must agree on the chosen Flask-SocketIO connection rejection mechanism and error-code semantics. For example, a connection may be rejected with `SESSION_INVALID` or `SESSION_EXPIRED`.

## 10.3 Event payload policy

Use a small, versioned, predictable payload. Example:

```json
{
  "request_id": "request-id",
  "event_type": "UPDATED",
  "request": {
    "request_id": "request-id",
    "seat_label": "18A",
    "intent_id": "water_request",
    "priority": "ROUTINE",
    "status": "ACKNOWLEDGED",
    "updated_at_ms": 1792670000000
  }
}
```

This is illustrative. Final field names must match the API contract.

The event may contain a normalized request summary, but it must not be treated as the permanent source of truth. SQLite remains authoritative.

## 10.4 Never lose the current state

When a browser initially connects or reconnects:
- Passenger fetches `GET /api/my-requests` and `GET /api/pa/active`.
- Crew fetches `GET /api/crew/requests`.
- The UI merges the snapshot with subsequent events.
- Requests and broadcasts are deduplicated by their stable IDs.

Socket.IO notifications can be delayed, missed, or arrive more than once. The client must not create duplicate request rows just because it receives the same event twice.

## 10.5 Network failure is not automatically session expiry

C's connection handling must distinguish:
- Confirmed authentication failure: redirect to login when a request confirms `401`, or when the socket reports the agreed explicit session error.
- Temporary network failure: show “Reconnecting…” and retain draft UI state.
- Model failure: keep visual and typed request options available.
- Request submission uncertainty: retry with the same idempotency key or query server state; do not generate a new request ID for every retry.

Do not redirect a passenger to login merely because the socket reports a generic transport error.

The documented Flask-SocketIO threading mode supports WebSocket functionality with compatible dependencies. Include `simple-websocket==1.0.0` as agreed for the project's intended threading setup, then test the actual server/client versions and transports on the real demo network. Reference: https://flask-socketio.readthedocs.io/en/latest/deployment.html

---

# PART 11 — AUTHENTICATION AND SECURITY REQUIREMENTS

Authentication is part of the functional implementation, not optional polish.

## 11.1 Passenger login

1. Passenger submits a seat label and demo invite code.
2. Backend normalizes the seat label using one agreed rule, such as uppercase with surrounding whitespace removed.
3. Backend validates the seat and invitation.
4. Backend generates a random session ID and opaque session token.
5. Backend stores only a hash of the opaque token.
6. Raw token is placed in a cookie.
7. Browser navigates to passenger dashboard.

The seed data should include all agreed demo seats. If using a simulated 32-row, six-seat layout, labels run from `1A` through `32F`. At a minimum, seed and test `18A` and `32D` as required demo seats.

Do not let a passenger change their seat merely by editing local JavaScript or changing a POST payload after logging in.

## 11.2 Crew login

Crew logs in separately with a crew PIN.

A single demo PIN is acceptable for a prototype, but it must be documented as a demo shortcut rather than a production authentication design.

Keep the secret in local configuration, not source code. Do not log PINs or session tokens.

## 11.3 Cookie configuration

For local HTTPS:
- `HttpOnly = True`
- `Secure = True`
- `SameSite = Lax`
- Reasonable session expiry
- Server-side session validation on each protected route
- CSRF/origin protections appropriate to the cookie-based setup

HTTPS must be configured before final microphone testing. Merely setting `Secure=True` does not create HTTPS.

## 11.4 Ownership authorization

For every passenger-specific resource request:
- Authenticate the caller.
- Verify that the caller has the passenger role.
- Verify that the resource belongs to that caller.
- Reject unauthorized access without revealing private details.

For every crew-only action:
- Authenticate the caller.
- Verify the crew role.
- Validate allowed actions and state transitions.
- Record the actor in event history where appropriate.

Test direct URL access to another passenger's request ID. A random ID is not a replacement for an ownership check.

## 11.5 Authentication of WebSockets

A browser being able to open the page does not prove its socket is authenticated.

Socket connections must validate the session and obtain their rooms from the server-side session. When the session is revoked or expires, a subsequent connection must fail.

Clients can issue UI actions through the documented HTTP endpoints. Avoid implementing a second, loosely validated mutation API through arbitrary client Socket.IO events.

---

# PART 12 — LOCAL AI AND AUDIO IMPLEMENTATION

A owns the model pipeline. B exposes it through one endpoint. C implements recording and review. D benchmarks and tests.

## 12.1 The recommended voice flow

Record audio → validate size, MIME type, and session → bounded inference queue → local Whisper transcription → normalize transcript → SetFit intent classification → validate against approved intents → determine suggestion/choice/unreliable outcome → save temporary preview → return preview to passenger → passenger reviews and confirms → shared request service creates final request.

Do not allow the AI function to bypass the final confirmation step or call `requests_service.py` to create a request.

## 12.2 Browser recording and MIME types

Do not hardcode WebM as the only possible recording format. Browsers may support different recording formats.

C should implement MIME feature detection:

```javascript
const candidates = [
  "audio/webm;codecs=opus",
  "audio/webm",
  "audio/mp4",
];

const supportedType = candidates.find(
  (type) => MediaRecorder.isTypeSupported(type)
);

const recorder = supportedType
  ? new MediaRecorder(stream, { mimeType: supportedType })
  : new MediaRecorder(stream);
```

In production code, also check whether `MediaRecorder` itself exists, catch constructor and recording errors, and upload the actual resulting media type rather than assuming the requested MIME type was used.

The supported-MIME check is a necessary safeguard but not a guarantee that every recording will succeed. MDN documents `MediaRecorder.isTypeSupported()` for determining whether the browser should be able to record the requested media type; Safari's MediaRecorder documentation also describes its MP4/AAC support. Reference: https://developer.mozilla.org/en-US/docs/Web/API/MediaRecorder/isTypeSupported_static

Mandatory: Test real iPhone Safari and at least one Android browser. Do not rely only on desktop simulation.

## 12.3 Audio size and duration

Agree on explicit server-side limits:
- Target recording duration: up to 15 seconds.
- Server-side maximum duration: 20 seconds.
- Maximum upload size: 10 MB.
- Reject empty uploads.
- Reject media types that are not on the server's allowlist.

The browser may stop a recording after the target duration, but the backend must independently enforce the upload and duration limits. Client-side restrictions alone are not security controls.

Return a clear error when an upload is too large, too long, silent, or unsupported.

## 12.4 Temporary audio files

For each upload:
1. Generate a unique, server-controlled temporary filename.
2. Store the upload in a controlled temporary directory.
3. Validate and decode it with the selected local inference backend.
4. Run transcription and classification.
5. Save the text preview if processing succeeds.
6. Delete the raw audio in a `finally` block.

Never reuse one global file called `temp.wav`; simultaneous uploads could overwrite one another.

Do not save audio recordings to the long-term request history. If an inference error occurs, clean up the file before returning the error.

## 12.5 Whisper backend selection

Choose the backend based on the actual host and measured results.
- Use `faster-whisper` as the portable baseline candidate.
- Consider `mlx-whisper` only if the host is compatible Apple Silicon and its measured performance is better for the demo workload.
- Load model weights from a local path or a verified local cache.
- Cache all weights and required dependencies before the WAN is disconnected.
- Keep model binaries out of normal Git history; copy them to the host or use a deliberate large-file distribution strategy.

A must record:
- Model name/version.
- Backend and runtime dependencies.
- Model directory.
- Approximate memory usage on the actual host.
- Transcription latency on test clips.
- Languages and example accents tested.
- Known failures.

Do not decide that a model is “fast enough” from a generic benchmark. Test the actual laptop, the actual model size, and the expected number of users.

## 12.6 SetFit intent classifier

The classifier maps transcripts to the approved 15 intents.

A suitable multilingual sentence-transformer starting candidate is `paraphrase-multilingual-MiniLM-L12-v2`, subject to compatibility and performance testing. Train or fine-tune the classifier using labeled examples from the frozen intent catalog.

Use examples that vary in:
- Wording.
- Sentence length.
- Politeness.
- Common non-native English patterns.
- Background noise and imperfect transcription.
- Supported languages actually intended for the demo.

A useful early milestone is a balanced small dataset with multiple examples per intent. Increase the amount as time allows. Dataset size alone does not guarantee accuracy.

## 12.7 Classification outcomes

The classifier must produce three behavioral outcomes.

Outcome A — Clear suggestion: Return the top suggested intent and allow the passenger to confirm it. A clear suggestion is still not a final request.

Outcome B — Requires choice: Return the leading candidates and tell the frontend that the passenger must choose. Include a “None of these” option.

Outcome C — Unreliable: Show that the voice request could not be classified reliably, retain the transcript when available, and allow typed input or visual cards.

Tune classification thresholds and candidate-margin rules using a validation set. Do not make up a confidence threshold because it looks plausible.

## 12.8 Urgency handling

Urgency must not be determined from model score alone.

The backend uses the reviewed intent catalog to derive priority. A potential urgent phrase may trigger an additional conservative warning or crew-review flag if the team implements that path. It must not silently disappear just because the ordinary classifier cannot confidently place it.

The frontend should make clear when it is unsure, and the visual fallback must remain accessible at all times.

## 12.9 Concurrency

Audio inference can consume substantial CPU and memory.

Use a bounded inference queue or semaphore to control how many model operations run at once. If the queue is full, return a clear retriable `503 MODEL_BUSY` response instead of exhausting the host.

Do not hold a database write transaction while waiting for the model. Load the models once during startup if practical, expose a model-readiness status, and test how the selected inference library behaves under concurrent requests.

---

# PART 13 — FRONTEND IMPLEMENTATION REQUIREMENTS

C owns the actual passenger and crew screens, but all UI behavior must follow the backend contract.

## 13.1 Passenger screens

### Screen A — Login

Required:
- Seat label field.
- Demo invite-code field.
- Clear validation errors.
- Loading state during login.
- No successful redirect until the backend confirms login.
- Visible network/server failure message.

### Screen B — Passenger homepage

Required:
- Prominent Speak action.
- A grid/list of large visual request cards.
- Optional typed input.
- A current-requests/status section.
- Active PA announcements.
- Reconnecting/offline status indicator.
- A way to cancel eligible pending requests.

Keep the primary request actions usable on mobile screens. Do not make voice the only way to make a request.

### Screen C — Voice review

Required:
- Recognized transcript.
- Suggested intent card.
- Any validated attributes.
- Up to two alternative intents when needed.
- Editable transcript.
- Clear cancellation action.
- One primary Confirm & Send action.
- Visible expiry and model-error handling.

If the transcript is edited, reclassify the edited text before creating the request. If the passenger chooses a different intent, submit that selected allowed intent and let the backend validate it.

Prevent multiple taps from creating duplicate requests: disable the primary button while a submission is in progress, and reuse the same idempotency key for a retry of that same logical request.

### Screen D — Request status

Show:
- Request ID.
- Intent label.
- Current status.
- Time submitted.
- Crew reply, if any.
- Reconnecting state, if applicable.

Status changes should come from successful API responses and server updates. Do not fake a successful acknowledgement locally.

## 13.2 Crew screens

### Crew login
- Separate login flow.
- No passenger-only routes exposed as crew actions.
- Clear login errors.

### Crew dashboard

Show:
- Request ID.
- Seat label.
- Intent and attributes.
- Priority.
- Request time.
- Current status.
- Fixed response selector.
- Acknowledge and complete actions.
- PA announcement cards and active announcement status.

Requirements:
- Urgent requests appear first.
- The list is refreshed from the server after reconnecting.
- Invalid state transitions show an error instead of changing the display permanently.
- Crew actions remain tied to request IDs and use backend authorization.
- Active announcements survive page reloads because they are fetched from persisted server state.

## 13.3 Fixed crew responses

`data/crew_responses.json` should hold reviewed replies.

Each entry should have:
- `reply_id`.
- English display text.
- Japanese display text.
- Optional short display label.
- Optional category.

The backend accepts the ID, looks it up, and records the corresponding fixed text. It does not blindly store arbitrary text sent by the browser.

## 13.4 Optional read-aloud feature

When a crew reply arrives, display its text immediately.

If you implement browser text-to-speech, show an explicit “🔊 Tap to hear reply” button. Invoke `speechSynthesis.speak()` directly from the user's tap handler. Do not automatically start speech from the Socket.IO reply handler, because browser autoplay restrictions—particularly on iOS—can block that behavior.

Test on a physical iPhone. If no suitable voice exists or the speech API fails, the text remains fully usable.

---

# PART 14 — PA ANNOUNCEMENTS: PERSISTENCE, EXPIRY, AND RECOVERY

B owns the database/API behavior. C owns the announcement display. D tests the expiry edge cases.

## 14.1 Approved PA cards

`data/pa_cards.json` contains the exact predefined announcement cards the crew is allowed to activate.

Each card should have:
- Stable `pa_card_id`.
- English text.
- Japanese text.
- A human-readable category.
- Optional allowed duration or duration policy.
- A status indicating whether the card is available to crew.

Only reviewed card IDs can be activated. Do not let the voice model or the browser create new PA text.

## 14.2 Activation

When crew activates a card:
1. Validate the crew session.
2. Validate the card ID against `pa_cards.json`.
3. Validate any requested duration against allowed bounds.
4. Generate `broadcast_id`.
5. Calculate `created_at_ms` and `expires_at_ms` on the server.
6. Insert the active announcement into SQLite.
7. Commit.
8. Emit `pa_broadcast_created`.
9. Return the saved announcement.

The server's response must contain the authoritative expiry timestamp.

## 14.3 Ending

When crew ends a card:
1. Validate crew role.
2. Check that the broadcast exists and is active.
3. Set status to `ENDED`.
4. Set `ended_at_ms`.
5. Commit.
6. Emit `pa_broadcast_ended`.

Repeated attempts to end an already ended card should be handled consistently, preferably idempotently where safe.

## 14.4 Expiry while a page is visible

The frontend receives `expires_at_ms` and schedules a local timer to remove the card from the visible active area.

When the timer runs, it must compare the current time against the absolute expiry timestamp. If the timer fired early, reschedule it.

The browser timer is not permission to update the database.

## 14.5 Expiry while a page is suspended

Mobile browsers can suspend background pages and throttle timers. Therefore C must refresh active broadcasts when:
- The Socket.IO connection is established.
- The page becomes visible again.
- A `pageshow` or appropriate focus/resume event occurs.
- The app returns after a potentially long suspension.

The refresh endpoint decides which announcements remain active. An expired announcement must not reappear simply because its browser timer did not run while the page was suspended.

## 14.6 Late-joining passengers

A passenger who joins after a PA card was activated must see it if it is still active.

That is why the initial active-PA API snapshot is required, even if every real-time broadcast event is functioning correctly.

---

# PART 15 — OFFLINE NETWORKING AND DEPLOYMENT

This section is essential. The application must work on the actual devices used in the demo, not only on the host laptop.

## 15.1 Network design

The host laptop runs Flask and exposes it on the local network. Passenger and crew devices connect to the same local Wi-Fi network or tested hotspot.

The network must permit local device-to-device communication. Some managed, guest, or isolated networks block communication between clients; do not assume that joining the same SSID is sufficient.

Do not use a loopback URL such as `localhost` on a passenger's phone. On a phone, `localhost` refers to that phone, not the host laptop.

## 15.2 Trusted local HTTPS

Microphone capture generally requires a secure browser context. For phone testing over a LAN, prepare a trusted local HTTPS certificate before the event.

The setup must:
1. Choose the actual hostname or LAN IP that devices will use.
2. Generate a certificate whose Subject Alternative Name covers that address.
3. Install and trust the signing certificate on every test phone.
4. Launch Flask-SocketIO behind the HTTPS configuration selected by the team.
5. Verify the browser reports a secure context.
6. Verify microphone permission works on the physical device.

A self-signed certificate that the phone does not trust may show warnings or cause features to fail. A URL starting with `https://` alone does not prove the certificate is trusted.

For a development setup, a local CA tooling approach such as `mkcert` may be used, but trust installation and actual browser behavior must be tested on each target device.

## 15.3 Local assets and packages

The final runtime must not depend on:
- Google Fonts or another remote font CDN.
- External CSS or JavaScript CDNs.
- Runtime downloads of model weights.
- A cloud speech-to-text service.
- A cloud intent-classification API.
- External authentication services.
- A remote database.

Vendor the correct compatible Socket.IO JavaScript client and all required assets locally before the WAN is disconnected.

## 15.4 Host launch

Use a single application process for the prototype. Do not run multiple processes that separately modify the same SQLite database or maintain inconsistent in-memory session state.

General launch call:

```python
socketio.run(
    app,
    host="0.0.0.0",
    port=5000,
    debug=False,
    use_reloader=False,
)
```

This is the application launch pattern, not a complete HTTPS configuration. B and D must wire in the chosen tested TLS serving arrangement. Never leave the reloader enabled for the demo; it can unexpectedly create another process or reload models.

## 15.5 Local setup guide

The README must provide the real, tested commands for the chosen host.

Sequence:
1. Install the supported Python version.
2. Clone the SoraLink repository.
3. Create and activate a virtual environment.
4. Install the locked dependencies.
5. Create `.env` from `.env.example`.
6. Download or copy model files while internet access is available.
7. Verify local model loading.
8. Run the seed script.
9. Run backend tests.
10. Launch the HTTPS-enabled application.
11. Check `/healthz`.
12. Connect a passenger device.
13. Connect a crew device.
14. Disconnect the WAN while keeping the LAN active.
15. Repeat the end-to-end request, reply, and PA tests.

The README must not contain placeholders presented as real commands or IP addresses.

## 15.6 Model readiness

At startup, the app should know whether the required model files are available and can be loaded.

Use `/healthz` for a basic server health check. If useful, add a model-readiness field such as:

```json
{
  "ok": true,
  "data": {
    "server": "READY",
    "voice_model": "READY",
    "classifier": "READY"
  }
}
```

Do not expose local filesystem paths or internal stack traces in health responses. If a model is not ready, the core app can still run, and visual request cards must remain operational.

---

# PART 16 — SEED DATA AND REPEATABLE SETUP

B owns `seed_db.py`; D verifies it.

## 16.1 Normal seed run

The normal seed operation must:
- Create required tables and indexes if missing.
- Apply documented, non-destructive schema migrations where required.
- Add missing invitation entries.
- Validate the intent, PA, and crew-response dictionaries.
- Keep existing request history.
- Keep current announcement history.
- Avoid invalidating active demo sessions unnecessarily.
- Print a concise readiness report without logging secrets.

Running it twice must not duplicate rows or wipe data.

## 16.2 Reset run

A destructive reset must require an explicit action, for example:

```bash
python seed_db.py --reset
```

It should show a destructive warning and require confirmation. A noninteractive `--yes` option may be implemented if the team needs an intentional scripted demo reset.

Normal startup must never silently execute the destructive reset path.

## 16.3 Seed tests

D should verify that:
- The first seed run creates the expected tables and demo seats.
- The second seed run preserves prior requests.
- Fixed dictionaries load successfully.
- Reset works only when explicitly requested.
- A missing mandatory intent or malformed PA dictionary causes a clear startup/seed error.

---

# PART 17 — IMPLEMENTATION SEQUENCE

Build the features in this order. The order is intentional: each stage gives the team a working base for the next stage.

## Stage 0 — Before independent coding

All four teammates:
- [ ] Create the repository.
- [ ] Add all four collaborators.
- [ ] Add the master plan and initial contracts.
- [ ] Confirm the 15 intent IDs and priorities.
- [ ] Confirm request statuses and legal transitions.
- [ ] Freeze API routes and JSON shapes.
- [ ] Freeze Socket.IO event names and payloads.
- [ ] Agree the database schema and timestamp convention.
- [ ] Agree who owns each module.
- [ ] Agree how shared files and contract changes are reviewed.
- [ ] Make sure all four can clone the repository and create a branch.

Exit condition: All four can describe the same request flow and use the same endpoint and payload definitions. Do not start incompatible implementations while these are still unsettled.

## Stage 1 — Establish the application skeleton

B leads; D verifies; C prepares basic page structure.

Implement:
- Flask application and configuration.
- SQLite database initialization.
- The agreed database schema and indexes.
- Seed script.
- `/healthz`.
- Environment configuration.
- Login page templates and initial routes.
- A working local development launch.

Run the app on the host, open the health route, seed the database, and confirm the data file appears in the correct local directory.

Exit condition: The app starts on the chosen host and can initialize its database without manual table editing.

## Stage 2 — Authentication and roles

Implement passenger and crew login.

Verify:
- Passenger can authenticate for a valid seeded seat.
- Passenger cannot authenticate with an invalid invite.
- Crew can log in through the crew route.
- Cookie and server session are created correctly.
- Protected endpoints reject unauthenticated users.
- Passenger cannot call a crew route.
- Passenger seat is taken from the authenticated session.
- Logout/revocation invalidates the session.

Exit condition: Every protected route can rely on a consistent backend identity and role.

## Stage 3 — First vertical slice: visual request to crew to passenger

This is the highest priority.

Implement:
- Visual request cards.
- `POST /api/requests`.
- Request persistence and event history.
- `GET /api/my-requests`.
- `GET /api/crew/requests`.
- Crew acknowledgement and completion.
- Fixed crew replies.
- Socket.IO notifications.
- Snapshot refresh on reconnect.

At this stage, AI is not required.

Exit condition: A passenger selects Water, crew sees it, acknowledges it, sends a fixed reply, and completes it. The passenger sees the correct status. Refreshing either page does not lose the saved request.

Do not proceed merely because one success path works on one screen. Test the normal login roles and at least one unauthorized request.

## Stage 4 — Stabilize authentication and recovery

Before adding model complexity, test:
- Cookie validity.
- Session expiry.
- Session revocation.
- Request ownership.
- WebSocket authentication.
- Room assignment.
- Reconnect snapshots.
- Duplicate event handling.
- Duplicate request submissions.
- Error handling during network loss.

Exit condition: An unauthorized or reconnecting user cannot corrupt state, read another passenger's request, or create duplicates through retries.

## Stage 5 — Add the local AI voice pipeline

A builds model wrappers; B integrates the preview endpoint; C builds recording and review; D tests real audio and concurrency.

Recommended order:
1. Load the local transcription model.
2. Transcribe a small recorded sample with an offline model.
3. Normalize the returned text.
4. Verify the classifier can produce only approved intent IDs.
5. Implement the preview API and temporary preview records.
6. Add confidence/uncertainty outcomes.
7. Add microphone capture with MIME negotiation.
8. Add transcript review and alternative choices.
9. Add final preview validation and one-time consumption.
10. Test upload limits, cleanup, queue behavior, and error states.

Exit condition: A passenger can speak, review the result, correct it if necessary, confirm, and create a single persisted request. When AI fails, visual requests continue to work.

## Stage 6 — Add PA persistence and expiry recovery

Implement:
- Approved PA dictionary.
- Activation endpoint.
- Active PA endpoint.
- End endpoint.
- Persistence and indexes.
- Real-time notification.
- UI expiry timer.
- Refresh after page resume/reconnect.
- Expiry filtering and recovery tests.

Exit condition: Active announcements persist across refresh, late-arriving passengers see unexpired announcements, and ended or expired announcements do not reappear.

## Stage 7 — Real-device and offline hardening

Test with the actual host and at least one actual passenger phone and crew device.

Check:
- Microphone permission over trusted local HTTPS.
- iPhone recording MIME type and upload.
- Android recording MIME type and upload.
- Socket.IO WebSocket upgrade and fallback behavior.
- Host firewall and local IP accessibility.
- Page suspension and reconnect recovery.
- Model behavior with concurrent audio submissions.
- SQLite lock handling under concurrent operations.
- All CSS, fonts, JavaScript, and models work without WAN access.
- Visual requests and crew responses still work if voice inference is unavailable.

Exit condition: The demo can be conducted with the WAN disconnected and LAN active, with evidence from actual devices.

## Stage 8 — Freeze and rehearse

At this point:
- Stop starting optional features.
- Fix critical bugs first.
- Freeze the intent catalog and data contracts.
- Run the acceptance suite.
- Clear demo test data only through the documented reset process.
- Rehearse the same demo sequence the team will use at submission.
- Record unresolved limitations honestly.
- Keep a known-good commit that can be restored.

If time runs out, retain the working visual request loop, authentication, persistence, reconnect recovery, and crew reply. A stable working product is more valuable than several half-integrated features.

---

# PART 18 — SUGGESTED HACKATHON TIME BUDGET

The organizer's final on-site schedule is authoritative. The plan below budgets approximately 19 hours and 45 minutes of coding-window time, based on the schedule previously identified by the team. Confirm the exact opening and submission times from the organizer before relying on this as a clock.

- First 2 hours — Foundation and login. Required milestone: app starts; DB initializes; passenger and crew login work.
- Next 3 hours — Basic request flow. Required milestone: visual request reaches crew and returns a reply.
- Next 2 hours — Authentication and recovery. Required milestone: role checks, ownership checks, reconnect snapshot.
- Next 4 hours — Voice and intent pipeline. Required milestone: one full voice-preview-confirm path works locally.
- Next 2 hours — PA announcements and polish. Required milestone: active announcement persists and expires correctly.
- Next 3 hours — Testing and hardening. Required milestone: offline, real-device, security, and recovery tests.
- Final 3 hours 45 minutes — Freeze, rehearsal, submission. Required milestone: stable demo; no risky new features.

This schedule is a budget, not a guarantee that every feature can be completed in its allocation. The first working request loop is the most important milestone.

## If the schedule slips

Prioritize in this order:
1. Passenger login, crew login, visual requests, persistence, crew response.
2. Ownership and role checks.
3. Reconnect recovery and duplicate-submission protection.
4. Local voice pipeline and transcript confirmation.
5. PA persistence and expiry recovery.
6. Optional read-aloud and extra UI polish.

If AI setup takes too long, do not remove the visual fallback to compensate. If the voice pipeline must be reduced, make the fallback obvious and keep the rest of SoraLink functional.

## What to prepare before the coding window

The team should not waste the limited on-site window downloading model weights or discovering whether phones can reach the laptop.

Before the event, when permitted:
- Ensure all four teammates can work from the repository.
- Install and validate compatible Python and package versions.
- Test a small voice recording end-to-end on the intended host.
- Cache all model weights and Python dependencies.
- Establish a trusted HTTPS setup for the test devices.
- Test the local network and firewall.
- Test the microphone on iPhone and Android if available.
- Prepare the fixed response and PA dictionaries.
- Prepare a short set of labeled speech examples for classification.
- Ensure the model starts successfully without internet.
- Confirm that the selected model licensing and use conditions are suitable for the project.

Use the actual permitted hackathon preparation rules as the authority for what can be prebuilt before the event.

---

# PART 19 — ERROR HANDLING AND RECOVERY MATRIX

The application should have a predictable response to every common failure. A failure must not silently turn into a wrong request or a false success message.

- Invalid passenger login — show login error; do not create a session.
- Invalid crew PIN — show login error; do not create a crew session.
- Session expired — protected route returns `401`; offer login again.
- Temporary network failure — show reconnecting state; retain drafts.
- Request submission times out — retry with same idempotency key or reconcile from server.
- Passenger lacks microphone permission — show explanation and visual/typed fallback.
- MediaRecorder unavailable — use fallback input.
- Unsupported audio type — reject cleanly; do not process as another format.
- Silent or empty recording — ask for another recording or use cards.
- Audio exceeds size/duration limit — reject with a specific user-facing error.
- Voice model unavailable — keep visual requests usable.
- Inference queue full — show temporary busy state and allow retry.
- Classifier uncertain — show candidates and require selection.
- Preview expired — reject final submission; permit reclassification or card selection.
- Preview consumed — return conflict/appropriate error; do not create another request.
- Database lock contention — bounded retry or controlled error; no false success.
- Duplicate request submission — return original request for the same idempotency key.
- Socket event missed — re-fetch authoritative server snapshot.
- Duplicate Socket.IO event — update the existing row rather than adding a duplicate.
- PA expires in a background tab — refresh on resume and hide expired broadcast.
- PA is ended during refresh — trust the latest authoritative state from the API.
- Crew attempts invalid transition — return error; keep correct stored state.
- Passenger queries another user's request — reject based on ownership.
- WAN disappears — app continues on LAN with local assets and cached models.

D should turn these rows into automated tests when feasible and manual test cases where automation is impractical.

---

# PART 20 — ACCEPTANCE TEST PLAN

Do not mark features complete because code was written. Mark them complete when the behavior was tested.

## 20.1 P0 functional tests

- [ ] A valid passenger can log in.
- [ ] A valid crew user can log in.
- [ ] An invalid user cannot authenticate.
- [ ] A passenger submits a Water card.
- [ ] The request is stored in SQLite.
- [ ] Crew sees the request.
- [ ] Crew acknowledges it.
- [ ] Passenger sees the acknowledgement.
- [ ] Crew sends a fixed response.
- [ ] Passenger sees the correct reply.
- [ ] Crew completes the request.
- [ ] Passenger sees `COMPLETED`.
- [ ] Refreshing the passenger page preserves current request state.
- [ ] Refreshing the crew page restores the correct queue.
- [ ] Re-running the ordinary seed command does not wipe the request.
- [ ] The core visual path works without the AI model.

## 20.2 Security tests

- [ ] Unauthenticated users cannot access protected APIs.
- [ ] Passenger cannot call crew-only APIs.
- [ ] Passenger cannot retrieve another user's request using its ID.
- [ ] Passenger cannot set a different seat in the request body.
- [ ] Passenger cannot set priority to `URGENT` for a routine intent.
- [ ] Invalid intent IDs are rejected.
- [ ] Invalid attributes are rejected.
- [ ] Expired and revoked sessions are rejected.
- [ ] Socket.IO rejects invalid sessions.
- [ ] Socket.IO rooms are assigned by the backend.
- [ ] A client cannot choose its own room.
- [ ] Invalid status transitions are rejected.
- [ ] Session tokens and credentials do not appear in application logs.

## 20.3 Voice tests

- [ ] A real recording produces a transcript.
- [ ] The browser sends its actual recording MIME type.
- [ ] At least one physical iPhone test is completed, if available.
- [ ] At least one physical Android test is completed, if available.
- [ ] The classifier returns only IDs from the catalog.
- [ ] A clear suggestion still requires passenger confirmation.
- [ ] Ambiguous requests show candidates.
- [ ] An unreliable result allows visual or typed fallback.
- [ ] An edited transcript is reclassified.
- [ ] A manually selected intent is validated by the backend.
- [ ] An expired preview is rejected.
- [ ] A consumed preview cannot create another request.
- [ ] Repeated taps do not create duplicate requests.
- [ ] Two concurrent uploads cannot overwrite each other's temporary files.
- [ ] Temporary audio is removed following successful inference.
- [ ] Temporary audio is removed following failed inference.
- [ ] Oversized files and long recordings are rejected.
- [ ] A full inference queue returns a usable retriable error.
- [ ] The model works without internet after all dependencies are cached.

## 20.4 PA tests

- [ ] Crew can activate an approved PA card.
- [ ] An active announcement appears on connected passenger devices.
- [ ] A late-arriving passenger sees an active announcement.
- [ ] Refreshing a passenger page restores active announcements.
- [ ] Manually ending an announcement removes it from the active view.
- [ ] The stored state records the end action.
- [ ] An expired announcement is omitted from `/api/pa/active`.
- [ ] A suspended page hides an expired announcement after it resumes.
- [ ] An ended broadcast does not return after a reconnect.
- [ ] A passenger cannot activate or end an announcement.
- [ ] An unknown PA card ID is rejected.

## 20.5 Reconnect and concurrency tests

- [ ] Temporarily disconnect a passenger device and reconnect it.
- [ ] Confirm the passenger's request state is restored.
- [ ] Disconnect and reconnect the crew dashboard.
- [ ] Confirm the latest queue is restored.
- [ ] Confirm a missed event does not lose a saved request.
- [ ] Confirm repeated events do not duplicate request rows.
- [ ] Submit requests from multiple clients in quick succession.
- [ ] Test SQLite lock contention.
- [ ] Confirm a model inference never runs while a database write transaction is held open.
- [ ] Confirm the server reports failures rather than displaying false success.

## 20.6 Offline test

This is a mandatory acceptance test:
1. Start the app while internet access is available.
2. Confirm models and assets are loaded locally.
3. Connect the passenger and crew devices to the local LAN.
4. Disconnect the WAN while leaving the LAN operational.
5. Log in.
6. Submit a visual request.
7. Acknowledge, reply, and complete the request.
8. Activate and end a PA announcement.
9. Test voice input if model readiness and local HTTPS are verified.
10. Refresh both interfaces and confirm persisted state is restored.

Record which steps passed and failed. Do not report “offline support passed” unless this test was actually conducted.

---

# PART 21 — DEMO RUNBOOK

This is the intended demo sequence. Rehearse it repeatedly, and keep the fallback ready.

## Before the presentation

1. Launch the app on the host laptop using the documented HTTPS command.
2. Check `/healthz` and model readiness.
3. Connect the crew device and log in.
4. Connect the passenger device and log in as a seeded seat.
5. Verify the local network is working.
6. Confirm that no external internet service is needed for the demo.
7. Reset test data only through the explicit seed reset operation.
8. Check that the request queue and PA view start in the expected state.

## Demo sequence

Step 1 — Visual request: Passenger selects a Water card. Crew receives it.

Step 2 — Live acknowledgement: Crew acknowledges the request. Passenger sees the changed status.

Step 3 — Fixed response: Crew sends the approved response. Passenger sees the response.

Step 4 — Voice-assisted request: Passenger speaks a short supported test phrase. Show the transcript and proposed intent. Review the suggestion and tap Confirm & Send.

Step 5 — Uncertainty handling: Show a prepared ambiguous phrase or a controlled test where the classifier requests confirmation. Demonstrate that the passenger can select an alternative or fall back to a card. Do not manufacture an accuracy claim.

Step 6 — PA announcement: Crew activates a bilingual card. Passenger sees it. Crew ends it or lets its expiry elapse.

Step 7 — Recovery: Refresh or reconnect a page and show that the current database state—not a stale browser display—is restored.

Step 8 — Offline proof: If permitted and practical, disconnect the WAN while preserving the LAN and demonstrate that the core loop continues.

The demo should be based on real persisted state. Do not use fake frontend-only data to simulate a backend feature that is not working.

---

# PART 22 — EXACT INSTRUCTIONS FOR THE FOUR BRANCHED AI CHATS

Once this master message has been branched into four chats, each teammate should use the matching role instructions below. The entire master plan is the shared context; the role-specific instructions constrain what that teammate should do.

## Chat A — AI & Audio

You are the AI and Audio implementation owner for SoraLink.

Follow the SoraLink Master Implementation Plan v1.0 and the repository's current `docs/API_CONTRACT.md`, `docs/INTENT_CATALOG.md`, and `docs/DECISIONS.md`.

Your primary files are `voice.py`, `classifier.py`, and the AI evaluation and model-preparation scripts under `scripts/`. Coordinate tests with the integration owner.

First inspect the actual repository and current contracts. Report which files exist, which are missing, what dependencies are already installed, and what is currently implemented. Do not assume the repository is empty or claim to have run tests unless you did.

Your responsibilities are local Whisper transcription, SetFit intent classification, transcript normalization, candidate ranking, uncertainty handling, local model readiness, bounded inference concurrency, unique temporary audio files, cleanup on every path, and voice evaluation.

You must return structured voice-preview results to the backend. You must not create final requests, write request rows directly, bypass passenger confirmation, redefine the frozen intent IDs, invent priorities, or invent crew responses.

Test the actual inference code, document the supported model and local model directory, and preserve offline operation. Do not claim universal accent support or quote unmeasured accuracy and latency figures.

Work incrementally. Before editing, state the exact files you intend to change and why. Do not change another owner's files without coordinating. If you discover a necessary contract change, describe the proposal and affected modules first rather than silently changing it.

Every implementation response should report: files changed, behavior added, dependencies or setup needed, tests run and their actual results, known issues, and the next specific integration step.

Follow the shared master specification even when a different implementation seems easier. The aim is one integrated SoraLink application, not an independent AI demo.

## Chat B — Backend

You are the Backend implementation owner for SoraLink.

Follow the SoraLink Master Implementation Plan v1.0 and the frozen API, database, and Socket.IO contracts in the repository.

Your primary files are `app.py`, `config.py`, `database.py`, `auth.py`, `requests_service.py`, `broadcast_service.py`, `schema.sql`, and `seed_db.py`.

First inspect the actual repository. Identify existing code and configuration, then propose a small implementation sequence. Do not assume missing files or claim tests have passed without running them.

You own authentication, session validation, role and ownership checks, database initialization, request persistence, event history, idempotency, valid state transitions, API validation, PA persistence, and server-side Socket.IO authentication and rooms.

SQLite is the source of truth. Use the agreed Unix epoch millisecond timestamp convention. Follow the database connection and WAL rules. Keep write transactions short and never hold them while AI inference runs. Commit the database mutation before emitting a success notification.

Do not trust browser values for seat, role, priority, owner, room, or announcement text. Use the approved intent and response dictionaries. Do not expose secrets or internal stack traces.

Your APIs must match the shared contracts exactly. If a new route or payload is genuinely needed, propose the contract change and identify the effect on A, C, and D before implementation.

Do not change another owner's files without coordination. Every implementation response must report files changed, endpoints implemented, authorization behavior, tests actually run, unresolved errors, and the next integration step.

The first milestone is a complete no-AI visual request flow from passenger to crew and back to passenger. Preserve that working path while adding AI later.

## Chat C — Frontend

You are the Frontend implementation owner for SoraLink.

Follow the SoraLink Master Implementation Plan v1.0 and the repository's frozen API, data, and Socket.IO contracts.

Your primary files are the templates under `templates/`, styles under `static/css/`, and client scripts under `static/js/`.

First inspect the actual repository and document what is already implemented. Do not invent API responses or mark a feature complete because a static mockup looks correct.

Build a mobile-first passenger interface and crew dashboard. Implement login, visual request cards, optional typed input, MIME-aware voice recording, transcript review, one explicit Confirm & Send action, alternatives for uncertain classification, request status, crew actions, fixed replies, and PA display.

All final operations must use B's agreed backend endpoints. Do not trust frontend role, seat, ownership, or priority values. Do not use fake success responses, bypass the voice-preview confirmation step, or directly mutate server state outside the contract.

Handle microphone denial, absent recording support, unsupported media types, empty recordings, model busy/unavailable errors, preview expiry, 401 responses, reconnects, and duplicate events without losing valid drafts or showing false success.

Keep all assets local for offline use. Do not add runtime CDN dependencies. Do not automatically invoke speech synthesis when a socket event arrives; if implemented, use an explicit user-triggered read-aloud button.

Do not edit another owner's files without coordination. Every implementation response must report files changed, the connected backend endpoints, tested devices/browsers, tests actually run, observed issues, and the next integration step.

Prioritize a functioning, accessible visual request loop before visual polish or optional interactions.

## Chat D — Integration & QA

You are the Integration, QA, and Offline Reliability owner for SoraLink.

Follow the SoraLink Master Implementation Plan v1.0 and current repository contracts. Your primary responsibilities are `tests/`, `docs/TEST_PLAN.md`, `docs/NETWORK_SETUP.md`, `README.md`, and coordinated integration fixes.

Start by inspecting the actual repository, current application startup path, dependencies, contracts, and existing tests. Do not assume a test passed just because a test file exists.

You must integrate continuously—not wait until the final hours. After each important module is merged or updated, verify imports, runtime configuration, API compatibility, database assumptions, Socket.IO events, and the core request flow.

Prioritize authorization, idempotency, database persistence, reconnection recovery, voice-preview expiry, temporary-file cleanup, PA expiry, and real-device/offline behavior.

Treat SQLite as authoritative. Check timestamp consistency, short write transactions, bounded inference concurrency, and the behavior of duplicate or missed socket events. Distinguish a temporary transport failure from confirmed session expiry.

Produce reproducible test commands and record actual outcomes. For manual tests, note the device, browser, network condition, expected behavior, actual behavior, and defect. Do not claim offline or mobile microphone support without testing it on actual devices.

Do not redefine APIs, intent IDs, statuses, or event names unilaterally. If a contract is blocking integration, document the conflict and coordinate a decision.

Every update must identify the current working milestone, tests run and results, blockers, cross-module defects, and the smallest next integration step. Your goal is a stable, demo-ready single application, not merely a large test folder.

## Shared instruction for all four chats

Before editing code, inspect the current repository state and the relevant contracts. Keep changes small enough to review. Never claim a file was changed, a test passed, or a feature works unless that action actually occurred. If code conflicts with the master plan, point out the conflict and propose the smallest safe resolution. Do not silently introduce a new framework, a new intent ID, a new endpoint, a new status, or a new dependency. Treat the shared GitHub repository and committed contract documents as the source of truth.

---

# PART 23 — THE DOCUMENTATION THAT KEEPS EVERYONE ALIGNED

The docs are not extra paperwork. They prevent four separate AI chats from drifting into incompatible implementations.

## `docs/MASTER_IMPLEMENTATION_PLAN.md`

Store the agreed master plan in this file. Update it when a fundamental project decision changes. It should include the goals, architecture, responsibilities, dependencies, build stages, and acceptance requirements.

## `docs/API_CONTRACT.md`

Record each API method and route, its required request fields, successful response schema, error codes, authorization requirements, and relevant idempotency rules. Every changed API must be reflected in this file.

## `docs/DATABASE_CONTRACT.md`

Record all table names, columns, primary and foreign keys, uniqueness constraints, indexes, status values, timestamp conventions, and migration behavior.

## `docs/SOCKET_EVENTS.md`

Record every allowed event name, who may receive it, its exact payload, room assignment rules, and what the client must fetch on reconnect.

## `docs/INTENT_CATALOG.md`

Record all approved intent IDs, priorities, display labels, attributes, and classifier behavior for clear, ambiguous, and unreliable outputs.

## `docs/TEST_PLAN.md`

Record acceptance tests, test commands, actual results, failures, and known limitations. Separate automated tests from tests that require a physical phone or the actual LAN.

## `docs/NETWORK_SETUP.md`

Record the actual tested host configuration, IP/hostname procedure, HTTPS setup, certificate trust steps, firewall rules, local model locations, offline startup command, and recovery steps.

## `docs/DECISIONS.md`

Use this small log to record significant decisions. Example:

```text
Decision ID: D-001
Date: 2026-10-22
Decision: Use integer Unix epoch milliseconds for persisted timestamps.
Reason: Avoid mixed timestamp representations and ambiguous expiry comparisons.
Affected modules: Backend, frontend, database, tests.
Status: Accepted.
```

This is a format example. The team should record its actual decisions in the repository.

---

# PART 24 — FINAL DEFINITION OF DONE

SoraLink is ready for its demo only when the following conditions are satisfied:

- The repository has one working integrated application.
- Passenger and crew authentication work.
- Visual requests persist and move through valid states.
- Crew replies reach the correct passenger.
- Request ownership and role restrictions are enforced by the server.
- Reconnects restore current request and PA state.
- Voice preview, review, and confirmation work if the AI stage is included.
- Raw audio is cleaned up on success and failure.
- PA activation, manual end, and expiry behave correctly.
- The application works without WAN access while the LAN remains active.
- Models and static assets are available locally.
- Real-device HTTPS and microphone behavior have been tested.
- The demo runbook has been rehearsed.
- Known limitations and actual test results are documented.

Check an item only after it has actually been verified. This checklist is for tracking the release, not evidence that the feature already works.

## What counts as a critical defect?

Do not call the build ready while any of these remains unresolved:
- A passenger can access another passenger's request.
- A passenger can perform crew-only actions.
- A request appears successful but was not saved.
- Repeated submission creates duplicate requests.
- Voice recording submits a final request without confirmation.
- The server trusts a client-supplied priority or seat.
- An active or expired PA announcement returns the wrong state after reconnect.
- The core visual request path breaks when the model is unavailable.
- The offline demo depends on a runtime CDN or a remote model download.

Minor visual imperfections can be accepted if the interface remains understandable. These data-integrity, authorization, and core-flow defects cannot.

---

# PART 25 — THE EXACT ORDER IN WHICH YOUR TEAM SHOULD START

Follow this practical starting sequence rather than having all four teammates independently ask their AI chats to build the entire app at once.

1. Leader creates the shared repository. Add the four teammates, create `docs/`, add `.gitignore`, and commit the master specification.
2. All four freeze the contracts. Confirm the approved 15 intents, statuses, database schema, API payloads, Socket.IO events, timestamp format, and file ownership.
3. B and D establish the running foundation. Get Flask, database initialization, seed data, and login working. C can prepare the interface structure against the frozen API contract.
4. C and B build the visual request loop. Connect passenger card → saved request → crew dashboard → reply → passenger status.
5. D tests the integrated loop immediately. Fix missing routes, mismatched field names, session errors, state issues, and duplicate submissions before adding AI.
6. A integrates the local voice pipeline through B's preview API. C connects its recording/review interface to that API. D validates inference failures, audio cleanup, and physical-device behavior.
7. B and C finish the PA lifecycle. Activate, persist, end, expire, and recover announcements. D tests expiry during refresh and page suspension.
8. All four perform the release tests and rehearse. Freeze the feature set, verify offline operation, fix critical defects, and preserve a known-good commit.

## The core strategy

ONE MASTER SPECIFICATION.
FOUR FOCUSED AI CHATS.
ONE SHARED GITHUB REPOSITORY.
FROZEN INTERFACE CONTRACTS.
CONTINUOUS INTEGRATION.
ONE FINAL TESTED APPLICATION.

The master plan provides the common direction; each teammate implements a bounded part of the system; the repository and its contracts keep the work aligned; and continuous integration catches incompatibilities before the final demo.

IMPORTANT: This plan is the specification, not a claim that any code has already been implemented or tested. The next step is to set up the repository and begin Stage 0, then work through the stages in order.



