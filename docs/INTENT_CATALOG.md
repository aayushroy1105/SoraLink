# SoraLink — Canonical Intent Catalog

**Status:** Proposed v1 catalog  
**Total intents:** 15  
**Urgent:** 4  
**Routine:** 11

All intent IDs are canonical identifiers shared by the frontend, backend, and AI classifier. Do not rename or invent IDs without an agreed update to this document.

## 1. Urgent intents

| Intent ID | Priority |
|---|---|
| `medical_help` | Urgent |
| `accessibility_assist` | Urgent |
| `safety_concern` | Urgent |
| `motion_sickness` | Urgent |

Urgent requests must appear ahead of routine requests in the crew queue. A low-confidence or failed voice classification must never silently discard an urgent need. Provide a direct visual assistance option independently of the AI pipeline.

## 2. Routine intents

| Intent ID | Priority |
|---|---|
| `water_request` | Routine |
| `blanket_request` | Routine |
| `pillow_request` | Routine |
| `bag_help` | Routine |
| `headphone_request` | Routine |
| `meal_inquiry` | Routine |
| `tea_coffee` | Routine |
| `lavatory_assist` | Routine |
| `seat_issue` | Routine |
| `customs_form` | Routine |
| `baby_care` | Routine |

Routine requests are ordered by creation time after urgent requests.

## 3. Shared rules

1. The classifier may return only an ID from this catalog.
2. The backend validates every submitted intent ID against this catalog.
3. The frontend uses these IDs when submitting requests.
4. Crew-facing English and Japanese labels come from reviewed static dictionaries, not AI-generated text.
5. If confidence is below the agreed threshold, show the top two candidate intents and a `None of these` option. That option opens visual categories or provides a direct crew-assistance path.
6. The visual assistance control must work without speech recognition or AI.
7. Any catalog changes must be agreed upon and reflected in the master implementation plan, API contract, data files, and tests.

**Implementation note:** The exact user-facing labels, translations, follow-up options, and classifier training examples must be defined and validated before integration.
