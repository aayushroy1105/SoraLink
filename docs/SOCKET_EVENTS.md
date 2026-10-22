# SoraLink — Socket.IO Events Contract

**Transport:** Flask-SocketIO  
**Deployment:** Single-host application over local Wi-Fi  
**Purpose:** Real-time notifications between passenger devices and the crew dashboard

## 1. Core Rules

1. SQLite is the authoritative source of application state.
2. Socket.IO delivers notifications; it does not replace REST APIs or database persistence.
3. Every connection and reconnection must be authenticated and authorized.
4. Clients must retrieve authoritative state through REST after reconnecting.
5. A client must never assume an operation succeeded merely because it emitted a socket event.
6. Passenger clients may receive only their own request updates and passenger-visible announcements.
7. Only authenticated crew clients may join the crew dashboard room or initiate crew actions.
8. All timestamps are UTC Unix milliseconds.
9. The core workflow must function on the local network without internet access.

## 2. Authorized Rooms

### `crew:dashboard`

Purpose: deliver request updates and crew-visible notifications.

Access: authenticated crew sessions only.

### `passenger:<session_id>`

Purpose: deliver request status updates and crew replies to one passenger session.

Access: the server derives the session ID from the authenticated session. Never accept a client-supplied room name as authorization.

## 3. Connection and Reconnection

On every Socket.IO connection:

1. Read the authenticated server-side session.
2. Verify that it exists, has not expired, and has not been revoked.
3. Verify the user's role.
4. Join `crew:dashboard` if the user is crew.
5. Join `passenger:<session_id>` if the user is a passenger.
6. Reject invalid sessions.
7. Send a connection-ready notification only after authorization succeeds.

On reconnection:

1. Repeat the complete authentication and room-assignment procedure.
2. Do not rely on the old Socket.IO socket ID.
3. Fetch fresh state through the relevant REST endpoint.
4. Refresh the passenger's active announcements and request statuses.
5. Refresh the crew's request queue.

The server must not trust room names, roles, seat labels, or session IDs provided in arbitrary socket payloads.

## 4. Server-to-Client Events

### `connection_ready`

Sent to an authenticated client after successful room assignment.

Payload:

```json
{
  "role": "passenger",
  "server_time": 1792700000000
}
```

For passengers, include their authenticated seat label if useful. Never expose session secrets.

### `request_created`

Recipient: `crew:dashboard`

Purpose: notify crew that a new request has been committed to SQLite.

Payload:

```json
{
  "request": {
    "request_id": "request-id",
    "seat_label": "18A",
    "intent_id": "water_request",
    "priority": "ROUTINE",
    "status": "PENDING",
    "created_at": 1792700000000
  }
}
```

The crew client should refresh or reconcile the relevant queue entry using the server's authoritative state.

### `request_updated`

Recipients: `crew:dashboard` and the relevant passenger room.

Purpose: notify clients that a request's status has changed.

Payload:

```json
{
  "request_id": "request-id",
  "seat_label": "18A",
  "status": "ACKNOWLEDGED",
  "updated_at": 1792700001000
}
```

The server must determine the authorized recipients. Do not broadcast passenger-specific information to every passenger.

### `crew_reply`

Recipient: the relevant passenger room.

Purpose: deliver a fixed, reviewed crew response.

Payload:

```json
{
  "request_id": "request-id",
  "response_id": "on_my_way",
  "labels": {
    "en": "A crew member is on the way.",
    "ja": "乗務員が伺います。"
  },
  "created_at": 1792700001000
}
```

All response labels must come from the approved static response catalog. Do not generate response text with AI.

### `follow_up_requested`

Recipient: the relevant passenger room.

Purpose: show a structured follow-up question.

Payload:

```json
{
  "request_id": "request-id",
  "follow_up_id": "water_temperature",
  "options": [
    {
      "id": "warm",
      "label_en": "Warm",
      "label_ja": "温かい"
    },
    {
      "id": "room_temp",
      "label_en": "Room temperature",
      "label_ja": "常温"
    },
    {
      "id": "ice",
      "label_en": "With ice",
      "label_ja": "氷入り"
    }
  ]
}
```

The passenger selects an option through an authenticated REST endpoint. Never let the client directly change request state by emitting an arbitrary socket event.

### `pa_broadcast_created`

Recipient: all currently connected, authorized passenger clients.

Purpose: display a persisted cabin announcement.

Payload:

```json
{
  "broadcast_id": "broadcast-id",
  "pa_card_id": "fasten_seatbelt",
  "labels": {
    "en": "Fasten your seatbelt.",
    "ja": "シートベルトをお締めください。"
  },
  "created_at": 1792700000000,
  "expires_at": null
}
```

Rules:
- Persist the broadcast before emitting the event.
- Broadcast only approved card IDs and reviewed translations.
- Do not send crew-only controls or internal metadata to passenger clients.
- Newly connected passengers must retrieve active broadcasts through the REST state endpoint.

### `pa_broadcast_ended`

Recipient: all authorized passenger clients.

Payload:

```json
{
  "broadcast_id": "broadcast-id",
  "ended_at": 1792700001000
}
```

The client must dismiss the matching announcement.

### `state_resync_required`

Recipient: the affected client.

Purpose: tell the client to retrieve authoritative state after a detected consistency issue.

Payload:

```json
{
  "reason": "reconnect_or_state_mismatch"
}
```

The client should call its relevant REST state endpoint and replace stale local state.

## 5. Client-to-Server Operations

State-changing operations must use the REST endpoints defined in `API_CONTRACT.md`.

Examples:
- Create a request using `POST /api/requests`.
- Confirm a voice preview using `POST /api/voice_request/confirm`.
- Acknowledge a request using the crew acknowledgement endpoint.
- Complete a request using the crew completion endpoint.
- Start or end a PA announcement using the crew PA endpoints.

The browser must not emit `request_created`, `request_updated`, `crew_reply`, or PA broadcast events as if they were authoritative server events.

## 6. Priority and Ordering

Priority is calculated by the backend using the approved intent catalog.

The crew queue must sort:
1. `URGENT` before `ROUTINE`.
2. Older requests before newer requests within the same priority.
3. A stable request ID as a final deterministic tie-breaker if timestamps match.

Socket.IO delivery order must not be used as the priority algorithm.

When requests are deduplicated, the server should notify clients only of meaningful changes and preserve the existing request's identity.

## 7. Duplicate Events and Idempotency

Socket.IO events may be delayed, repeated, or missed during disconnection.

Clients must:
- Identify requests by `request_id`.
- Update existing records instead of blindly appending duplicates.
- Reconcile their state with REST responses.
- Avoid changing request status solely because an event was received.

The backend must:
- Persist changes before emitting events.
- Use database transactions for state changes.
- Enforce idempotency for repeated acknowledgement, completion, and request-creation operations.
- Reject invalid state transitions.

## 8. Announcement Expiry

When a broadcast includes `expires_at`:

1. The passenger client schedules local dismissal for that timestamp.
2. The client recalculates the remaining time when the page resumes from the background.
3. The backend excludes expired broadcasts from active-state responses.
4. Explicit crew termination persists the ended state and emits `pa_broadcast_ended`.
5. Client-side timers must not be treated as the authoritative record of broadcast status.

If the client receives an already-expired announcement, it must not display it as active.

## 9. Mobile Browser Lifecycle

Mobile browsers can suspend background pages and drop WebSocket connections.

Therefore:
- Enable Socket.IO reconnection.
- Show a clear disconnected or reconnecting indicator.
- Rejoin authorized rooms after every reconnection.
- Fetch authoritative state after reconnection.
- Do not lose pending user input merely because a socket disconnects.
- Keep visual request submission available through REST while the local server is reachable.
- If authentication expires, redirect to the appropriate login screen with a clear message.

## 10. Error Handling and Security

- Reject unauthenticated or unauthorized connections.
- Never expose another passenger's requests, replies, or session data.
- Validate all event payloads and expected data types.
- Do not trust client-supplied priority, role, seat identity, or room membership.
- Do not include credentials, cookies, or session tokens in event payloads.
- Log meaningful server-side failures without exposing sensitive information to clients.
- Avoid sending raw audio or unnecessary transcript details over the crew-wide room.

## 11. Acceptance Tests

The implementation must demonstrate that:

1. An authenticated crew client joins `crew:dashboard`.
2. A passenger joins only their own session room.
3. A newly created request appears in the crew queue.
4. Acknowledgement and completion reach the correct passenger.
5. Passenger A never receives Passenger B's private request updates.
6. Invalid sessions cannot reconnect to authorized rooms.
7. A reconnecting client recovers current state from REST.
8. Active PA announcements appear for late connections.
9. Ended and expired announcements are dismissed.
10. Duplicate notifications do not create duplicate queue entries.
11. Priority ordering remains correct even when events arrive out of order.
12. All of the above can be tested without WAN access.
