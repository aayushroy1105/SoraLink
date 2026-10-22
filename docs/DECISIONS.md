# SoraLink — Architecture Decision Record

**Project:** SoraLink  
**Status:** Hackathon MVP  
**Architecture:** Offline-first, single-host application

## 1. Core Product Decision

SoraLink provides an accessible communication bridge between airline passengers and cabin crew.

The MVP prioritizes a complete, reliable request lifecycle over a large feature set.

The required workflow is:

1. Passenger authenticates.
2. Passenger submits a visual, typed, or voice-assisted request.
3. Backend validates and persists the request.
4. Crew sees the request in a priority-sorted queue.
5. Crew acknowledges or completes the request.
6. Passenger receives the updated status or a fixed crew response.

The system must remain usable without AI inference or microphone permission.

## 2. Offline-First Architecture

- One host device runs the Flask application, database, and available local AI models.
- Passenger phones and the crew device connect to that host through a local Wi-Fi network.
- The core request, crew queue, status, and announcement workflows must not require internet access.
- Model weights and required dependencies must be prepared before the offline demonstration.
- Vercel or another cloud host is not required for the live offline MVP.
- Socket.IO notifications are local-network notifications, not cloud messaging.

**Important:** Offline-first means the application does not require WAN access during the demonstration. It does not automatically guarantee that every browser, certificate, microphone, or model will work without prior configuration.

## 3. Technology Decisions

| Component | Decision |
|---|---|
| Backend | Python Flask |
| REST API | Flask routes returning JSON |
| Real-time communication | Flask-SocketIO |
| WebSocket support | `simple-websocket` with the threading backend |
| Database | SQLite |
| Database concurrency | WAL mode, foreign keys, and a 20-second connection timeout |
| Frontend | HTML5, CSS3, and JavaScript |
| Speech-to-text | Local Whisper implementation, subject to benchmarking |
| Intent classification | Local SetFit model where feasible |
| Phonetic matching | `thefuzz` and `jellyfish`, with multilingual limitations tested explicitly |
| Session signing | Flask session mechanisms and/or `itsdangerous` for explicitly defined signed tokens |
| Reviewed content | Static JSON dictionaries |

Use only dependencies listed in the shared requirements file. Do not independently introduce another backend framework or database.

## 4. AI Boundary

AI is limited to:
- Transcribing passenger speech.
- Suggesting one of the 15 approved service intents.
- Producing a confidence score and candidate alternatives.

AI must not:
- Generate free-form safety announcements.
- Invent Japanese translations or crew instructions.
- Set request priority independently of the approved intent catalog.
- Bypass authentication, request validation, or database rules.
- Silently discard an uncertain urgent request.

All request labels, crew responses, follow-up options, and PA cards must come from reviewed static dictionaries.

## 5. Intent Catalog

The canonical intent catalog is `data/intents.json`.

The planned MVP contains:
- 4 urgent intents.
- 11 routine intents.

Intent IDs, labels, priorities, and follow-up options must remain consistent across the AI model, backend, passenger interface, crew interface, and tests.

Do not invent new intent IDs inside individual modules. If a new intent is necessary, update the canonical catalog and all dependent contracts together.

## 6. Request Priority and Lifecycle

The backend is authoritative for priority and status.

Priority ordering:
1. Urgent requests first.
2. Routine requests second.
3. FIFO within each priority group.

Valid lifecycle:

`PENDING → ACKNOWLEDGED → COMPLETED`

The backend must reject invalid state transitions and persist each valid transition before sending notifications.

Clients must not determine priority or change status merely by editing browser-side data.

## 7. Request Deduplication

An active request is one whose status is `PENDING` or `ACKNOWLEDGED`.

For an identical active request from the same seat:
- Return the existing request instead of creating a duplicate.
- Preserve the existing request ID.
- Record meaningful deduplication events where appropriate.

A new request for the same intent is permitted after the earlier request reaches `COMPLETED`.

The database transaction, not the frontend button state, enforces this behavior.

## 8. Authentication and Roles

Two roles exist:
- `passenger`
- `crew`

Passenger identity is bound to a validated seat invitation and server-side session.

Crew access requires a valid crew session.

Rules:
- Never trust a client-supplied role or seat label.
- Never treat an unguessable URL as authentication.
- Protect crew endpoints and crew Socket.IO rooms.
- Authenticate every connection and reconnection.
- Passenger sessions may receive only their own private request events.
- Expired or revoked sessions must lose access.

Demo credentials are for the prototype only and must not be presented as production airline authentication.

## 9. Real-Time Communication

SQLite is the source of truth. Socket.IO is the notification layer.

For every state-changing operation:
1. Validate authorization and input.
2. Update SQLite transactionally.
3. Commit the transaction.
4. Emit the appropriate notification.

On reconnect:
1. Reauthenticate.
2. Rejoin the authorized room.
3. Fetch fresh state through REST.
4. Reconcile the interface with the server response.

Clients must tolerate duplicate, delayed, and missed events.

## 10. PA Broadcast Persistence

PA announcements must be persisted in `active_broadcasts` before notification.

A passenger who opens or refreshes the application must receive the current active announcements from the server.

The client dismisses expiring announcements at the appropriate time, while the backend remains authoritative about whether a broadcast is active.

Only approved PA card IDs and reviewed translations may be broadcast.

## 11. Voice Pipeline

The voice workflow is a single logical request:

1. Browser records audio.
2. Server validates the upload.
3. Local Whisper transcribes the audio.
4. The local intent engine classifies the transcript.
5. The UI receives the transcript and proposed intent together.
6. Passenger confirms once.
7. Backend validates and persists the request.

For ambiguous speech, show visual candidate cards and a `None of these` recovery option.

If voice inference fails, the passenger can still submit visual or typed requests.

Use a unique temporary audio file per inference when disk storage is necessary, and delete it in a `finally` block.

For iOS Safari, negotiate a supported recording MIME type and provide an accessible fallback if recording is unavailable.

## 12. Read-Aloud Accessibility

Do not assume that mobile browsers permit automatic speech synthesis whenever a socket event arrives.

Provide a visible, user-initiated **Tap to hear reply** control for responses that must be read aloud. Keep the text response visible even if speech synthesis is unavailable.

## 13. Multilingual Scope

Voice MVP targets:
- English
- Hindi
- Punjabi
- Hinglish/code-switching

Japanese, Thai, and Vietnamese are supported through reviewed visual phrase and announcement packs where applicable.

Do not claim that every language or accent has been validated until recorded evaluation results support the claim.

## 14. Model and Confidence Decisions

The initial intent classification design uses:
- SetFit with the agreed multilingual sentence-transformer model.
- Normalized confidence scores.
- Phonetic matching as a tie-breaker where supported.
- A configurable initial confidence threshold of `0.72`.
- A weighted scoring experiment of `0.85 × semantic + 0.15 × phonetic`, enabled only after evaluation.

The threshold and weights are starting configurations, not validated accuracy guarantees.

Urgent-assistance recovery must remain available even when speech confidence is low.

The evaluation holdout set must not be used as training data. Record actual results and limitations.

## 15. Timestamp and Database Rules

- Store timestamps as UTC Unix milliseconds in INTEGER columns.
- Use consistent timestamp units across Python, SQLite, REST responses, and Socket.IO events.
- Do not compare ISO timestamp strings with SQLite `CURRENT_TIMESTAMP` when formats differ.
- Enable WAL mode and foreign keys on database connections.
- Keep write transactions short.
- Persist state before emitting notifications.

## 16. GitHub Collaboration Rules

The repository is the shared source of truth.

Every teammate and AI assistant must:
1. Read the master implementation plan and relevant contracts before editing.
2. Modify only the files assigned to their role unless the team explicitly coordinates a shared change.
3. Avoid rewriting another teammate's files without permission.
4. Never independently redefine API payloads, database columns, intent IDs, or socket events.
5. Document proposed contract changes before implementing them across modules.
6. Check the latest committed repository state before integration.
7. Commit focused changes with descriptive messages.
8. Test the changes and record actual results.

A file ownership boundary is a coordination rule, not a substitute for reviewing integration dependencies.

## 17. Scope Control

Implement the minimum complete workflow first:

1. Passenger login.
2. Crew login.
3. Visual request creation.
4. SQLite persistence and deduplication.
5. Priority-sorted crew queue.
6. Acknowledgement and completion.
7. Passenger status updates.
8. Active PA broadcast persistence.
9. Local-network reconnection and recovery.
10. Local speech-to-text and intent classification if time and hardware permit.

Do not delay the deterministic workflow to perfect the AI model or implement optional features.

## 18. Production Boundary

The hackathon prototype is not certified airline software.

Actual airline deployment would require additional security review, operational validation, accessibility testing, network integration, reviewed localization, and airline approval.

Do not describe proposed features or untested performance targets as achieved results.

