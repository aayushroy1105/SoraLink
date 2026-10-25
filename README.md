# SoraLink

**Offline-First In-Flight Passenger–Crew Communication & Assistance Platform**

SoraLink provides resilient, accessible, cabin-local communication between airline passengers and flight attendants without requiring in-flight internet access. It features dual responsive web portals (Passenger & Crew), local speech-to-text recognition (Faster-Whisper), fine-tuned multilingual intent classification (SetFit MiniLM), transactional SQLite persistence with WAL mode, and real-time bidirectional WebSocket synchronization (Flask-SocketIO).

---

## Architecture Overview

```
                      +---------------------------------------+
                      |       Cabin Local Network (LAN)       |
                      +---------------------------------------+
                                    |           |
            +-----------------------+           +----------------------+
            |                                                          |
            v                                                          v
+-----------------------+                                  +-----------------------+
|   Passenger Portal    |                                  |      Crew Portal      |
|  (Seat Card / Voice)  |                                  |   (Request Queue &    |
|   /passenger Route    |                                  |    PA Broadcasts)     |
+-----------------------+                                  +-----------------------+
            |                                                          |
            | HTTP / WebSockets                                        | HTTP / WebSockets
            v                                                          v
+----------------------------------------------------------------------------------+
|                              SoraLink Flask Server                                |
|                                                                                  |
|   /api/auth/*         Independent session management (passenger vs. crew)        |
|   /api/requests/*     Request lifecycle (SUBMITTED -> ACKNOWLEDGED -> COMPLETED) |
|   /api/voice/preview  Audio upload, Faster-Whisper ASR & SetFit Classification    |
|   /api/broadcasts/*   Cabin-wide public announcements (PA cards)                 |
|   /api/health         Runtime status, SetFit model readiness, loaded directory   |
+----------------------------------------------------------------------------------+
          |                         |                                |
          v                         v                                v
+------------------+     +--------------------+            +--------------------+
|  Faster-Whisper  |     |   SetFit MiniLM    |            |   SQLite (WAL)     |
|   ASR Engine     |     | Intent Classifier  |            |   Database         |
| (models/whisper) |     |  (15 Canonical)    |            | (instance/*.db)    |
+------------------+     +--------------------+            +--------------------+
```

---

## Key Features

1. **Independent Role Authentication**:
   - Role-segregated session cookies (`soralink_passenger_session` and `soralink_crew_session`) allow crew and passenger portals to operate simultaneously in the same browser without session overwrite.
   - Crew access is protected by an authenticated crew passkey.
   - Passenger seats are verified against the cabin seating manifest.

2. **Multilingual Intent Classification**:
   - 15 frozen canonical flight intents categorized into **URGENT** (safety, medical, motion sickness, accessibility) and **ROUTINE** (water, meal, blanket, pillow, etc.).
   - Multilingual support for **English**, **Japanese**, **Hindi** (Devanagari & Hinglish), and **Punjabi** (Gurmukhi & Romanized).
   - Indic script character harmonization (`fix_mixed_indic`), Gurmukhi/Devanagari function-word coverage, and nukta-tolerant phrase matching.

3. **Robust Confidence & Out-Of-Domain (OOD) Guardrails**:
   - Closed-set models are guarded by a vocabulary coverage check (`min_vocab_coverage = 0.34`).
   - Unrecognized noise and unsupported commands safely resolve to `UNRELIABLE`, directing passengers to clear visual request cards.
   - Strong urgent signals (e.g. cabin smoke, severe bleeding, breathing distress, wheelchairs) are promoted to Candidate #1 and force user confirmation.

4. **Real-Time State Resynchronization**:
   - Powered by Flask-SocketIO with isolated room targeting (`seat:<id>` for passengers, `crew` for flight attendants).
   - Reconnection handshake triggers missed request and active broadcast synchronization across connection drops or browser refreshes.

5. **PA Announcements**:
   - Cabin-wide broadcasts with pre-approved safety and service announcements, auditory chimes, and automatic TTL expiration.

---

## Prerequisites & Installation

- **Python**: 3.10 to 3.14 (tested and verified on macOS/Linux).
- **FFmpeg**: Required for audio decoding (`brew install ffmpeg` on macOS, `apt-get install ffmpeg` on Ubuntu).

### 1. Clone & Set Up Virtual Environment

```bash
cd SoraLink
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

### 2. Download or Verify Model Weights

SoraLink operates fully offline. Model assets must be present in the `models/` or `Updated_Model/models/` directory.

To verify or download weights from Hugging Face (one-time setup with internet):

```bash
# Verify existing offline weights
python scripts/download_models.py --verify-only

# Or download required Whisper + embeddings weights if setting up a fresh machine
python scripts/download_models.py --whisper-model small
```

### 3. Initialize & Seed Database

```bash
python seed_db.py
```

This creates `instance/soralink.db` with WAL mode enabled, tables, indices, and demo seat allocations (including crew code `CREW777`).

---

## Configuration & Environment Variables

SoraLink can be configured via environment variables or a `.env` file:

| Variable | Default | Purpose |
| :--- | :--- | :--- |
| `SORALINK_ENV` | `development` | Environment mode (`development`, `test`, `production`). |
| `SORALINK_SECRET_KEY` | *(dev fallback)* | Secret key for session signing (mandatory in production). |
| `SORALINK_HOST` | `0.0.0.0` | Host interface to bind server. |
| `SORALINK_PORT` | `5000` | Port to bind server. |
| `SORALINK_DB_PATH` | `instance/soralink.db` | Filesystem path for SQLite database. |
| `SORALINK_CREW_CODE` | `CREW777` | Passkey required for crew portal login. |
| `SORALINK_MODEL_DIR` | `Updated_Model/models/setfit_intent_classifier` | Explicit path override for SetFit intent classifier. |
| `SORALINK_CLASSIFIER_DIR` | *(same as above)* | Alternative alias for classifier directory override. |
| `SORALINK_MIN_VOCAB_COVERAGE` | `0.34` | Minimum fraction of catalog words required to avoid OOD fallback. |
| `SORALINK_SUGGESTED_THRESHOLD`| `0.60` | Minimum score for single-tap `SUGGESTED` outcome. |
| `SORALINK_MARGIN_THRESHOLD` | `0.05` | Minimum margin between top-1 and top-2 candidates for confident auto-suggestion. |

---

## Starting the Application

```bash
python app.py
```

Once started:
- **Login Portal**: `http://localhost:5000/` or `http://localhost:5000/login`
- **Passenger Portal**: `http://localhost:5000/passenger` (Login with seat `12A` or demo token)
- **Crew Dashboard**: `http://localhost:5000/crew` (Login with Crew Passkey: `CREW777`)
- **Health & Readiness Endpoint**: `http://localhost:5000/api/health`

---

## Testing & Quality Checks

Run the automated test suite with pytest:

```bash
# Run all unit, integration, and guardrail tests
python3 -m pytest -v

# Run test suite quietly with summary
python3 -m pytest -q
```

### Running Model Evaluation

To benchmark the multilingual classifier on the 950-example curated test suite:

```bash
python scripts/evaluate_voice.py
```

Or run the model comparison script:
```bash
python scripts/build_test_suite.py
```

---

## Intent Catalog (15 Frozen Canonical Categories)

| Intent ID | Priority | Primary Action | Allowed Attributes |
| :--- | :--- | :--- | :--- |
| `medical_help` | **URGENT** | Crew medical dispatch / first aid | - |
| `accessibility_assist`| **URGENT** | Mobility, wheelchair, aisle chair assistance | - |
| `safety_concern` | **URGENT** | Cabin hazards, seatbelt, turbulence safety | - |
| `motion_sickness` | **URGENT** | Sick bag, nausea relief, cleanup | - |
| `water_request` | ROUTINE | Drink service (Water) | `temperature`: `COLD`, `ROOM`, `WARM` |
| `blanket_request` | ROUTINE | Comfort amenity delivery | - |
| `pillow_request` | ROUTINE | Comfort amenity delivery | - |
| `bag_help` | ROUTINE | Overhead bin luggage assistance | - |
| `headphone_request` | ROUTINE | Audio jack / headphone delivery | - |
| `meal_inquiry` | ROUTINE | Catering & meal inquiry | `dietary`: `VEG`, `NON_VEG`, `SNACK` |
| `tea_coffee` | ROUTINE | Hot beverage service | - |
| `lavatory_assist` | ROUTINE | Restroom queue / accessibility direction | - |
| `seat_issue` | ROUTINE | Recline, tray table, IFE hardware issue | - |
| `customs_form` | ROUTINE | Arrival / immigration declaration card | - |
| `baby_care` | ROUTINE | Infant bassinet, diaper disposal, formula water | - |

---

## Security & Operational Guardrails

- **Zero Data Leakage**: Passenger seat tokens and crew sessions are validated on every state-changing route and WebSocket connection.
- **Seat Spoofing Prevention**: Requests can only be created for the authenticated seat.
- **Offline Assurance**: All inference (Whisper STT and SetFit NLU) is strictly local. No outbound network requests are initiated at runtime.
- **Crash Immunity**: Malformed audio, unparseable payloads, or missing model files fail gracefully into safe client-side choices rather than unhandled 500 exceptions.
