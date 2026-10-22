# SoraLink — API Contract

**Status:** Hackathon MVP  
**Architecture:** Offline-first, single-host Flask application  
**Transport:** HTTP REST + Socket.IO over a local Wi-Fi network  
**Source of truth:** SQLite database

This document defines the API contract shared by the frontend, backend, and AI components. All implementations must follow these endpoint names, payloads, response formats, and authorization rules.

## 1. Global Rules

- All endpoints use the same Flask server and origin.
- REST request and response bodies use JSON unless the endpoint explicitly accepts audio uploads.
- All timestamps are UTC Unix timestamps in milliseconds.
- The backend and SQLite database are authoritative for request status and priority.
- Socket.IO is used for notifications; it is not the source of truth.
- The complete core workflow must function without internet access or AI inference.
- Never trust a seat label, role, priority, or session ID supplied by the browser without server-side validation.
- Never expose crew-only endpoints to passenger sessions.

### Standard success response

```json
{
  "ok": true,
  "data": {}
}
```

### Standard error response

```json
{
  "ok": false,
  "error": {
    "code": "ERROR_CODE",
    "message": "Human-readable explanation"
  }
}
```

Use appropriate HTTP status codes: `400` invalid input, `401` unauthenticated, `403` unauthorized, `404` not found, `409` conflicting state, `413` upload too large, `429` rate limited, and `500` unexpected server error.

## 2. Authentication and Sessions

### `POST /api/auth/passenger`

Authenticate a passenger using a server-issued seat invitation.

Request:

```json
{
  "seat_label": "18A",
  "demo_code": "0000"
}
```

Success:

```json
{
  "ok": true,
  "data": {
    "role": "passenger",
    "seat_label": "18A",
    "session_id": "server-generated-session-id"
  }
}
```

Requirements:
- Validate the seat and demo code against `seat_invites`.
- Reject invalid or disabled invitations.
- Create a server-side passenger session and set an HTTP-only session cookie.
- Bind the authenticated session to its authorized seat.
- Return any currently active passenger-visible PA announcement in the initial state response.
- Do not accept a passenger's claimed seat as proof of identity.

### `POST /api/auth/crew`

Authenticate an authorized crew member using the configured demo credentials.

Request:

```json
{
  "username": "crew_demo",
  "password": "configured-demo-password"
}
```

Success:

```json
{
  "ok": true,
  "data": {
    "role": "crew",
    "crew_id": "server-generated-crew-id"
  }
}
```

Requirements:
- Use a server-configured demo credential, not a hardcoded production password.
- Set an HTTP-only session cookie.
- Enforce crew authorization on every crew-only route and Socket.IO room.
- Never grant crew access based only on a URL or browser-supplied role.

### `GET /api/auth/me`

Return the authenticated user's role and permitted identity information.

### `POST /api/auth/logout`

Invalidate the current session and clear its cookie.

## 3. Passenger State

### `GET /api/passenger/state`

Passenger-only endpoint.

Returns the authenticated passenger's seat, their active requests, relevant request history, and active PA announcements.

Example:

```json
{
  "ok": true,
  "data": {
    "seat_label": "18A",
    "requests": [],
    "active_broadcasts": []
  }
}
```

The response must be generated from current database state so a refreshed or reconnected browser can recover without relying on missed Socket.IO events.

## 4. Voice Request Pipeline

### `POST /api/voice_request`

Passenger-only endpoint. This combines speech transcription and intent classification into a single request.

Request: multipart form-data containing:
- `audio`: the recorded audio file.
- Optional `language_hint`: one of the supported voice language codes.

Supported voice MVP scope: English, Hindi, Punjabi, and Hinglish/code-switching, subject to local model performance.

Success when a usable transcript and intent candidate are available:

```json
{
  "ok": true,
  "data": {
    "preview_id": "server-generated-preview-id",
    "transcript": "Can I have some water?",
    "intent_id": "water_request",
    "confidence": 0.88,
    "needs_confirmation": true,
    "alternatives": []
  }
}
```

When classification is ambiguous:

```json
{
  "ok": true,
  "data": {
    "preview_id": "server-generated-preview-id",
    "transcript": "I need something",
    "intent_id": null,
    "confidence": 0.51,
    "needs_confirmation": true,
    "alternatives": [
      {
        "intent_id": "water_request",
        "label": "I need water"
      },
      {
        "intent_id": "blanket_request",
        "label": "I need a blanket"
      }
    ],
    "allow_none_of_these": true
  }
}
```

Requirements:
- Validate MIME type and file size before processing.
- Accept supported browser formats, including `audio/webm` and `audio/mp4`, if the installed decoder supports them.
- Run local Whisper transcription and then local bounded intent classification.
- Return the transcript and proposed intent together so the passenger only needs one confirmation.
- Keep AI inference off the main request-handling path when necessary by using a worker or background executor.
- Store the preview for 30 minutes; enforce expiry server-side.
- Delete temporary audio files after inference, including on failure.
- If speech processing fails, preserve the visual-card and typed-request workflows.
- Never generate free-form safety announcements or crew responses with AI.

## 5. Confirm a Voice Preview

### `POST /api/voice_request/confirm`

Passenger-only endpoint.

Request:

```json
{
  "preview_id": "server-generated-preview-id",
  "intent_id": "water_request"
}
```

Success:

```json
{
  "ok": true,
  "data": {
    "request_id": "server-generated-request-id",
    "seat_label": "18A",
    "intent_id": "water_request",
    "status": "PENDING",
    "created_at": 1792700000000
  }
}
```

Requirements:
- Verify that the preview belongs to the authenticated session.
- Reject expired or already-invalid previews.
- Validate the selected intent against `data/intents.json`.
- Permit selection of a valid visual recovery candidate.
- Create or merge the request transactionally.
- Apply deduplication to prevent repeated active requests for the same seat and intent.
- Emit a Socket.IO notification only after the database transaction commits.

### `POST /api/voice_request/none_of_these`

Passenger-only endpoint.

Request:

```json
{
  "preview_id": "server-generated-preview-id"
}
```

Return the visual category grid or a safe crew-assistance fallback. Never force the passenger to repeat speech.

## 6. Visual and Typed Requests

### `POST /api/requests`

Passenger-only endpoint.

Request:

```json
{
  "intent_id": "water_request"
}
```

Success:

```json
{
  "ok": true,
  "data": {
    "request_id": "server-generated-request-id",
    "seat_label": "18A",
    "intent_id": "water_request",
    "status": "PENDING",
    "priority": "ROUTINE",
    "created_at": 1792700000000
  }
}
```

Requirements:
- Validate the intent ID against the canonical catalog.
- Derive seat identity from the authenticated session.
- Derive priority from server-controlled intent metadata.
- Apply transactional deduplication.
- Return the existing active request if an equivalent request is already pending or acknowledged, rather than creating duplicate queue entries.
- Never allow the passenger to set their own priority or status.

## 7. Crew Request Management

All endpoints in this section require an authenticated crew session.

### `GET /api/crew/requests`

Returns requests sorted by:
1. Urgent before routine.
2. FIFO within the same priority.

Example request record:

```json
{
  "request_id": "request-id",
  "seat_label": "32D",
  "intent_id": "medical_help",
  "status": "PENDING",
  "priority": "URGENT",
  "created_at": 1792700000000,
  "labels": {
    "en": "I need assistance now",
    "ja": "至急サポートが必要です"
  }
}
```

Labels must come from fixed, reviewed dictionaries.

### `POST /api/crew/requests/<request_id>/acknowledge`

Request:

```json
{
  "response_id": "on_my_way"
}
```

Success changes the request from `PENDING` to `ACKNOWLEDGED` and records the event.

### `POST /api/crew/requests/<request_id>/complete`

Marks an acknowledged request as `COMPLETED`.

Requirements:
- Verify the request exists.
- Validate its current status.
- Record the status transition and timestamp.
- Notify the passenger's authenticated session.
- Reject invalid state transitions without silently overwriting state.

### `POST /api/crew/requests/<request_id>/follow_up`

Request:

```json
{
  "follow_up_id": "water_temperature",
  "option_id": "warm"
}
```

Only allow follow-up IDs and options defined in the reviewed catalog. Send the selected fixed response to the passenger as a visual, one-tap option.

## 8. Passenger Replies and Fixed Content

### `GET /api/content/catalog`

Returns the reviewed intent labels, permitted follow-ups, and supported visual categories needed by the passenger UI.

### `GET /api/content/pa_cards`

Returns the fixed, reviewed passenger-announcement cards.

### `GET /api/passenger/replies`

Returns the authenticated passenger's current request statuses and available fixed crew responses.

Crew response text, Japanese translations, and PA text must come from reviewed JSON dictionaries. AI must not generate them.

## 9. Cabin Announcement Management

### `GET /api/crew/pa/cards`

Returns the approved announcement cards available to crew.

### `POST /api/crew/pa/broadcast`

Crew-only endpoint.

Request:

```json
{
  "pa_card_id": "fasten_seatbelt"
}
```

Success:

```json
{
  "ok": true,
  "data": {
    "broadcast_id": "server-generated-broadcast-id",
    "pa_card_id": "fasten_seatbelt",
    "active_status": true,
    "created_at": 1792700000000,
    "expires_at": null
  }
}
```

Requirements:
- Accept only a known, approved card ID.
- Store active broadcast state in SQLite before emitting an event.
- Broadcast only fixed reviewed content.
- Ensure late-loading and reconnecting passengers retrieve active broadcasts from the database.
- If an announcement has an expiry, the UI must dismiss it at expiry and the backend must exclude it from active-state responses.

### `POST /api/crew/pa/end`

Crew-only endpoint. Ends a specified active broadcast, persists the change, and emits `pa_broadcast_ended`.

## 10. Socket.IO Events

Socket.IO notifications are delivered over the local network.

### Authorized rooms

- `crew:dashboard`: authenticated crew only.
- `passenger:<session_id>`: the authenticated passenger session only.

### Server-to-client events

| Event | Recipient | Purpose |
|---|---|---|
| `request_created` | Crew dashboard | New request is available |
| `request_updated` | Crew dashboard and relevant passenger | Request status changed |
| `crew_reply` | Relevant passenger | Acknowledgement or fixed response |
| `pa_broadcast_created` | Authorized passenger clients | Display active announcement |
| `pa_broadcast_ended` | Authorized passenger clients | Dismiss announcement |
| `state_resync_required` | Relevant client | Reload authoritative state |

Requirements:
- Authenticate connections and authorize rooms on every connection and reconnection.
- Rejoin the correct room after reconnection.
- Reject invalid or expired sessions.
- Re-fetch authoritative REST state after reconnecting or detecting missed events.
- Never rely on Socket.IO delivery as proof that a database operation succeeded.

## 11. Authentication, Validation and Reliability

- Use HTTP-only session cookies and appropriate `SameSite` settings.
- Protect state-changing routes against CSRF as required by the chosen session configuration.
- Validate all request bodies and reject unknown intent, response, and PA card IDs.
- Apply reasonable upload size and processing time limits.
- Use parameterized SQL queries.
- Use SQLite transactions for request creation, deduplication, state transitions, and broadcasts.
- Enable SQLite WAL mode and a suitable busy timeout.
- Use one unique temporary audio file per inference request if disk storage is required.
- Do not expose stack traces, credentials, session tokens, or raw uploaded audio in client responses.
- Provide accessible visual and typed alternatives when microphone permissions or AI inference are unavailable.

## 12. Offline Acceptance Criteria

The MVP is acceptable when all of the following are demonstrated with WAN access disabled:

1. A passenger can authenticate and submit a visual request.
2. A crew member can authenticate and see the request on another device.
3. Requests are persisted and sorted by server-controlled priority.
4. Crew acknowledgement and completion update passenger status.
5. Duplicate active requests are merged safely.
6. A passenger can recover their state after a refresh or reconnect.
7. Active PA announcements survive page refreshes and late connections.
8. Voice transcription and classification work locally when supported model dependencies are installed.
9. Voice failure does not block visual requests.
10. Unauthorized users cannot access crew routes or another passenger's session.

## 13. Implementation Rule

If an implementation detail conflicts with this contract, the team must agree on and document the change before implementing it across multiple modules. Update this file and any affected database or Socket.IO contracts together.

