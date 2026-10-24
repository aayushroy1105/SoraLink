// SoraLink Canonical Shared Types conforming strictly to Master Implementation Plan v1.1

export type RequestCategory = "water_request" | "blanket_request" | "pillow_request" | "accessibility_assist"

// Canonical Request Status vocabulary (Part 7.4: PENDING | ACKNOWLEDGED | COMPLETED | CANCELLED)
export type RequestStatus = "PENDING" | "ACKNOWLEDGED" | "COMPLETED" | "CANCELLED"

// Canonical Priorities (Part 7.4: URGENT | ROUTINE)
export type Priority = "URGENT" | "ROUTINE"

// Voice-preview outcomes (Part 7.4: SUGGESTED | REQUIRES_CHOICE | UNRELIABLE)
export type VoicePreviewOutcome = "SUGGESTED" | "REQUIRES_CHOICE" | "UNRELIABLE"

// PA announcement statuses (Part 7.4: ACTIVE | ENDED | EXPIRED)
export type PABroadcastStatus = "ACTIVE" | "ENDED" | "EXPIRED"

export type ConnectionState = "connected" | "reconnecting" | "offline"

// Supported languages: English, Japanese, Traditional Chinese, Hindi, Tamil, Marathi
export type Language = "en" | "ja" | "zh" | "hi" | "ta" | "mr"

export type AppScreen = "passenger-home" | "passenger-login" | "crew-login" | "crew-dashboard"

export interface PassengerRequest {
  id: string // Format: req_...
  seat_label: string // e.g. "18A"
  intent_id: string
  category?: RequestCategory
  priority: Priority
  title: string
  attributes: Record<string, string>
  created_at_ms: number
  updated_at_ms: number
  status: RequestStatus
  notes?: string
  crew_reply_id?: string
  crew_reply_text_en?: string
  crew_reply_text_ja?: string
  idempotency_key?: string
}

export interface PACard {
  pa_card_id: string
  category: "SAFETY" | "SERVICE" | "FLIGHT_STATUS" | "CABIN_NOTICE"
  title_en: string
  title_ja: string
  title_zh: string
  title_hi?: string
  title_ta?: string
  title_mr?: string
  text_en: string
  text_ja: string
  text_zh: string
  text_hi?: string
  text_ta?: string
  text_mr?: string
  default_duration_seconds: number
}

export interface PABroadcast {
  broadcast_id: string
  pa_card_id: string
  category: string
  title_en: string
  title_ja: string
  title_zh: string
  title_hi?: string
  title_ta?: string
  title_mr?: string
  text_en: string
  text_ja: string
  text_zh: string
  text_hi?: string
  text_ta?: string
  text_mr?: string
  created_at_ms: number
  expires_at_ms: number
  active_status: PABroadcastStatus
}

export interface CrewResponse {
  reply_id: string
  label_en: string
  label_ja: string
  label_zh: string
  label_hi?: string
  label_ta?: string
  label_mr?: string
  text_en: string
  text_ja: string
  text_zh: string
  text_hi?: string
  text_ta?: string
  text_mr?: string
}

export interface IntentMetadata {
  intent_id: string
  priority: Priority
  label_en: string
  label_ja: string
  label_zh: string
  label_hi?: string
  label_ta?: string
  label_mr?: string
  description_en: string
  description_ja: string
  description_zh: string
  description_hi?: string
  description_ta?: string
  description_mr?: string
}
