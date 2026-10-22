# SoraLink — Test Plan

**Project:** SoraLink  
**Purpose:** Validate the offline-first passenger–crew communication MVP  
**Test environment:** Local Flask host, SQLite, local Wi-Fi, passenger browser, crew browser

## 1. Testing Principles

- Test actual behavior rather than assuming a feature works because its code exists.
- Record PASS, FAIL, BLOCKED, or NOT RUN for every test.
- Never mark a test PASS without observing its result.
- Run the deterministic visual-request workflow before testing AI features.
- Repeat relevant tests with WAN access disabled.
- Never use real passenger information or real airline credentials.
- Use only approved demo data and fixed content dictionaries.

## 2. Test Environment

Prepare:
- One laptop running the SoraLink Flask application.
- One passenger phone or browser.
- One separate crew phone, tablet, or browser.
- A local Wi-Fi network or hotspot connecting all devices.
- An initialized SQLite database.
- Seeded demo seat invitations.
- Configured demo crew credentials.
- The approved intent and PA-card JSON catalogs.

For voice testing, additionally prepare:
- Installed local speech-to-text model weights.
- Installed audio-decoding dependencies.
- Test recordings covering supported languages.
- A working fallback for browsers that cannot record audio.

Record the operating system, Python version, dependency versions, model version, and test date before the final rehearsal.

## 3. Test Result Format

Record every test using this structure:

| Field | Description |
|---|---|
| Test ID | Unique test identifier |
| Feature | Function being tested |
| Preconditions | Required setup |
| Steps | Actions performed |
| Expected result | Required behavior |
| Actual result | Observed behavior |
| Status | PASS, FAIL, BLOCKED, or NOT RUN |
| Notes | Error details and follow-up actions |

## 4. Authentication Tests

### AUTH-01 — Valid passenger login

Precondition: A valid demo seat invitation exists.

Steps:
1. Open the passenger login page.
2. Enter the correct seat and demo code.
3. Submit the form.

Expected:
- Passenger login succeeds.
- The authenticated seat is shown.
- A server-side session is established.
- Passenger state loads successfully.

### AUTH-02 — Invalid passenger credentials

Steps:
1. Enter an invalid seat or demo code.
2. Submit the form.

Expected:
- Authentication is rejected.
- No authenticated passenger session is created.
- The interface shows a useful error.

### AUTH-03 — Valid crew login

Steps:
1. Open the login page.
2. Enter the configured demo crew credentials.

Expected:
- Crew login succeeds.
- The crew dashboard opens.
- The session has the crew role.

### AUTH-04 — Passenger cannot access crew endpoints

Steps:
1. Authenticate as a passenger.
2. Attempt to access a crew-only REST endpoint.

Expected:
- The backend returns an authorization error.
- No crew data is exposed.

### AUTH-05 — Session expiry and logout

Steps:
1. Authenticate.
2. Log out or revoke the session.
3. Attempt to access a protected endpoint.

Expected:
- The old session no longer grants access.
- The interface returns the user to an appropriate login screen.

## 5. Visual Request Tests

### REQ-01 — Create a water request

Steps:
1. Log in as passenger at seat 18A.
2. Select the water visual card.
3. Submit the request.

Expected:
- A request is created in SQLite.
- The request has the correct seat and intent.
- Its initial status is `PENDING`.
- The crew dashboard receives the request.

### REQ-02 — Create an urgent request

Steps:
1. Submit an approved urgent assistance request.

Expected:
- The backend assigns the catalog-defined urgent priority.
- The request appears above routine requests.

### REQ-03 — Reject a fabricated intent

Steps:
1. Submit an intent ID that does not exist in the approved catalog.

Expected:
- The backend rejects the request.
- No invalid request is persisted.

### REQ-04 — Duplicate submission

Steps:
1. Submit the same request twice rapidly from the same seat.

Expected:
- At most one active request exists for that seat and intent.
- The existing request ID is returned for the duplicate.
- No duplicate queue entry is created.

### REQ-05 — New request after completion

Steps:
1. Submit a water request.
2. Complete it through the crew workflow.
3. Submit another water request.

Expected:
- The second request can be created.
- The completed request remains in history.

## 6. Crew Queue and Request Lifecycle

### QUEUE-01 — Priority sorting

Steps:
1. Create multiple routine requests.
2. Create an urgent assistance request.
3. Observe the crew queue.

Expected:
- Urgent requests appear before routine requests.
- Requests within the same priority are sorted FIFO.
- The server, not the browser, determines priority.

### QUEUE-02 — Acknowledge request

Steps:
1. Select a pending request in the crew dashboard.
2. Click `Acknowledge · On my way`.

Expected:
- Status changes to `ACKNOWLEDGED`.
- The database is updated.
- The passenger receives the status update.

### QUEUE-03 — Complete request

Steps:
1. Acknowledge a pending request.
2. Mark it complete.

Expected:
- Status changes to `COMPLETED`.
- Completion time is recorded.
- The passenger receives the update.

### QUEUE-04 — Invalid status transition

Steps:
1. Attempt to complete a pending request without acknowledgement.

Expected:
- The backend rejects the invalid transition.
- The database remains consistent.

### QUEUE-05 — Fixed follow-up options

Steps:
1. Submit a water request.
2. Have crew send a temperature follow-up.
3. Select one of the displayed options.

Expected:
- Only approved options are available.
- The selected option reaches the backend.
- The passenger does not need to repeat the request verbally.

## 7. Voice and AI Tests

Run these tests only after the deterministic visual workflow passes.

### VOICE-01 — Supported audio upload

Steps:
1. Record or select a supported audio sample.
2. Submit it through the passenger voice interface.

Expected:
- The backend validates the file.
- Local Whisper returns a transcript if processing succeeds.
- The intent classifier returns a proposed intent or ambiguity alternatives.

### VOICE-02 — Single confirmation workflow

Steps:
1. Speak a supported request.
2. Wait for the transcript and proposed intent.
3. Confirm once.

Expected:
- The transcript and proposed intent are shown together.
- One confirmation creates or merges the request.
- No second mandatory confirmation screen is required.

### VOICE-03 — Ambiguous speech

Steps:
1. Submit a vague or ambiguous sample.

Expected:
- The UI presents candidate intents where available.
- `None of these` opens visual categories or a safe crew-assistance fallback.
- The request is not silently discarded.

### VOICE-04 — Failed transcription

Steps:
1. Submit invalid, silent, or unsupported audio.

Expected:
- A useful error is shown.
- The visual and typed request options remain available.
- No invalid request is created.

### VOICE-05 — Concurrent audio uploads

Steps:
1. Submit two different recordings at approximately the same time.

Expected:
- Each recording is processed independently.
- Transcripts are not mixed.
- Temporary files are cleaned up if disk storage is used.

### VOICE-06 — Language and accent evaluation

Steps:
1. Test representative English, Hindi, Punjabi, and Hinglish recordings.
2. Include different speakers, paraphrases, and noisy samples.
3. Compare predictions with manually labeled expected intents.

Expected:
- Actual results are recorded.
- Routine-intent accuracy is calculated on the untouched holdout set.
- Uncertain and incorrect classifications are documented.

Do not claim an accuracy percentage until the evaluation has actually been run.

## 8. PA Broadcast Tests

### PA-01 — Broadcast approved announcement

Steps:
1. Log in as crew.
2. Select an approved PA card.
3. Broadcast it.

Expected:
- The broadcast is persisted in SQLite.
- Connected passenger clients display the approved content.

### PA-02 — Announcement after refresh

Steps:
1. Broadcast an announcement.
2. Refresh the passenger page.

Expected:
- The still-active announcement is retrieved from the server and displayed.

### PA-03 — Announcement for a late connection

Steps:
1. Broadcast an announcement.
2. Connect another authorized passenger client.

Expected:
- The new client retrieves the active announcement through the REST state endpoint.

### PA-04 — End announcement

Steps:
1. End an active announcement from crew mode.

Expected:
- The database records the end state.
- Connected passenger clients dismiss the announcement.

### PA-05 — Expiring announcement

Steps:
1. Create a test broadcast with a short expiry.
2. Keep the passenger page open until expiry.
3. Refresh another passenger page after expiry.

Expected:
- The open page dismisses the announcement.
- The expired announcement is not returned as active.
- The server remains authoritative about broadcast state.

## 9. Socket.IO and Reconnection Tests

### SOCKET-01 — Passenger receives private update

Steps:
1. Log in as passenger A.
2. Create a request.
3. Acknowledge it from crew mode.

Expected:
- Passenger A receives the appropriate update.

### SOCKET-02 — Passenger isolation

Steps:
1. Log in as passengers A and B in separate sessions.
2. Update passenger A's request.

Expected:
- Passenger B does not receive passenger A's private request or reply.

### SOCKET-03 — Reconnection after suspension

Steps:
1. Connect a passenger.
2. Suspend the browser or temporarily disconnect the device.
3. Update the request through crew mode.
4. Reconnect the passenger.

Expected:
- The client reauthenticates and rejoins the correct room.
- REST state recovery displays the current status.
- Missed socket events do not leave the interface permanently stale.

### SOCKET-04 — Duplicate event handling

Steps:
1. Deliver or simulate the same notification twice.

Expected:
- The client updates the existing request instead of displaying duplicate requests.

### SOCKET-05 — Unauthorized socket connection

Steps:
1. Attempt a connection without a valid session.
2. Attempt to access a crew room as a passenger.

Expected:
- Unauthorized access is rejected.

## 10. Database and Reliability Tests

### DB-01 — Clean initialization

Steps:
1. Initialize a fresh test database.
2. Run the schema and seed utility.

Expected:
- Tables, indexes, foreign keys, and demo data are initialized successfully.

### DB-02 — Persistence after restart

Steps:
1. Create and acknowledge a request.
2. Restart the Flask application.
3. Reopen the dashboard.

Expected:
- Persisted requests retain their state.
- The dashboard can reconstruct the current queue.

### DB-03 — Concurrent duplicate requests

Steps:
1. Submit identical requests concurrently.
2. Inspect the database.

Expected:
- Only one active request exists for the same seat and intent.

### DB-04 — Database contention

Steps:
1. Run a voice inference while submitting visual requests.
2. Inspect logs and request outcomes.

Expected:
- The database remains consistent.
- Temporary lock contention is handled within the configured timeout.
- No committed request is silently lost.

### DB-05 — Demo reset

Steps:
1. Use the explicit demo-reset option on a disposable test database.

Expected:
- The reset initializes the documented seed data.
- Normal application startup does not unexpectedly wipe existing requests.

## 11. Offline Acceptance Test

### OFFLINE-01 — Complete workflow without WAN

Precondition: Required dependencies, model weights, and browser assets have been prepared locally.

Steps:
1. Start the host application.
2. Disable WAN/internet connectivity while keeping the local network available.
3. Connect the passenger and crew devices to the host's local network.
4. Authenticate the passenger.
5. Submit a visual request.
6. Confirm the request appears in crew mode.
7. Acknowledge and complete it.
8. Confirm the passenger receives the final status.
9. Broadcast an approved PA announcement.
10. Refresh the passenger page and verify the active announcement remains visible.
11. If local AI is configured, test a voice request.

Expected:
- The deterministic workflow succeeds without WAN access.
- Requests and announcements persist in SQLite.
- Socket.IO notifications and REST state recovery work locally.
- Voice works only if its model and dependencies are correctly installed; otherwise, the visual fallback remains usable.

## 12. Final Demonstration Checklist

Before presenting:
- [ ] Passenger login works.
- [ ] Crew login works.
- [ ] Visual request submission works.
- [ ] Priority sorting works.
- [ ] Deduplication works.
- [ ] Acknowledgement and completion work.
- [ ] Passenger status updates work.
- [ ] Active announcements survive refreshes.
- [ ] Reconnection restores current state.
- [ ] The offline workflow succeeds.
- [ ] Voice has been tested on the actual demonstration hardware, or is clearly treated as an optional feature.
- [ ] No unverified performance or accuracy claims appear in the presentation.
- [ ] Logs contain no unresolved critical errors.

## 13. Reporting Results

After each test run, record:
- Test ID
- Date and environment
- Actual result
- PASS, FAIL, BLOCKED, or NOT RUN
- Error details
- Corrective action
- Retest result

Do not mark a test as passing based on code inspection alone when the test requires actual execution.

