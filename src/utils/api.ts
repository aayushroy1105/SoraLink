import {
  PassengerRequest,
  RequestCategory,
  RequestStatus,
  PABroadcast,
  CrewResponse,
} from "../types"
import {
  APPROVED_PA_CARDS,
  APPROVED_CREW_RESPONSES,
  INTENT_CATALOG,
} from "../data/canonicalData"
import { translations } from "./translations"

const META_STORAGE_KEY = "soralink_request_meta_v1"

export interface RequestExtraMeta {
  attributes?: Record<string, string>
  notes?: string
  crew_reply_id?: string
  crew_reply_text_en?: string
  crew_reply_text_ja?: string
  cancelled?: boolean
}

const syncChannel =
  typeof window !== "undefined" && "BroadcastChannel" in window
    ? new BroadcastChannel("soralink_sync_channel")
    : null

export function onCrossTabSync(callback: () => void): () => void {
  if (!syncChannel) return () => {}
  const handler = () => callback()
  syncChannel.addEventListener("message", handler)
  return () => syncChannel.removeEventListener("message", handler)
}

export function notifyCrossTabSync() {
  try {
    syncChannel?.postMessage({ ts: Date.now() })
  } catch {}
}

export function getRequestMetaMap(): Record<string, RequestExtraMeta> {
  try {
    const raw = localStorage.getItem(META_STORAGE_KEY)
    if (raw) return JSON.parse(raw)
  } catch {}
  return {}
}

export function saveRequestMeta(id: string, patch: Partial<RequestExtraMeta>) {
  try {
    const map = getRequestMetaMap()
    map[id] = { ...(map[id] || {}), ...patch }
    localStorage.setItem(META_STORAGE_KEY, JSON.stringify(map))
    notifyCrossTabSync()
  } catch {}
}

// Map Figma PA Card IDs <-> Backend PA Card IDs
const FIGMA_TO_BACKEND_PA: Record<string, string> = {
  fasten_seatbelt: "turbulence",
  service_starting: "meal_service",
  initial_descent: "arrival_preparation",
  lavatory_limited: "lavatory_queue",
}

const BACKEND_TO_FIGMA_PA: Record<string, string> = {
  turbulence: "fasten_seatbelt",
  meal_service: "service_starting",
  arrival_preparation: "initial_descent",
  lavatory_queue: "lavatory_limited",
  boarding_update: "service_starting",
  cabin_crew_assistance: "fasten_seatbelt",
}

// Map Figma Crew Reply IDs <-> Backend Crew Response IDs
const FIGMA_TO_BACKEND_REPLY: Record<string, string> = {
  reply_water_coming: "crew_on_the_way",
  reply_on_the_way: "crew_on_the_way",
  reply_shortly: "request_received",
  reply_assist_coming: "request_acknowledged",
}

const BACKEND_TO_FIGMA_REPLY: Record<string, string> = {
  crew_on_the_way: "reply_on_the_way",
  request_received: "reply_shortly",
  request_acknowledged: "reply_assist_coming",
  request_completed: "reply_on_the_way",
}

export async function apiFetch<T = any>(
  path: string,
  options: RequestInit = {},
): Promise<{
  ok: boolean
  status: number
  data?: T
  error?: { code: string; message: string }
}> {
  try {
    const headers: Record<string, string> = {
      ...(options.headers as Record<string, string>),
    }
    if (
      options.body &&
      !(options.body instanceof FormData) &&
      !headers["Content-Type"]
    ) {
      headers["Content-Type"] = "application/json"
    }
    const resp = await fetch(path, {
      ...options,
      credentials: "include",
      headers,
    })
    const json = await resp.json().catch(() => null)
    if (json && typeof json.ok === "boolean") {
      return {
        ok: json.ok,
        status: resp.status,
        data: json.data,
        error: json.error,
      }
    }
    return {
      ok: resp.ok,
      status: resp.status,
      data: json,
    }
  } catch (err: any) {
    return {
      ok: false,
      status: 0,
      error: {
        code: "NETWORK_ERROR",
        message: err?.message || "Network error",
      },
    }
  }
}

export async function apiLoginPassenger(seatLabel: string, inviteCode: string) {
  const normSeat = seatLabel.trim().toUpperCase()
  const normCode = inviteCode.trim()

  return apiFetch("/api/auth/passenger", {
    method: "POST",
    body: JSON.stringify({ seat_label: normSeat, demo_code: normCode }),
  })
}

export async function apiLoginCrew(pinOrPassword: string) {
  const trimmed = pinOrPassword.trim()
  let res = await apiFetch("/api/auth/crew", {
    method: "POST",
    body: JSON.stringify({ username: "crew_demo", password: trimmed }),
  })

  // Support the Figma UI documented Demo PIN ("1234") against the backend's configured crew password
  if (!res.ok && res.status === 401 && trimmed === "1234") {
    res = await apiFetch("/api/auth/crew", {
      method: "POST",
      body: JSON.stringify({ username: "crew_demo", password: "soralink-crew" }),
    })
  }

  return res
}

export async function apiLogout() {
  return apiFetch("/api/auth/logout", { method: "POST" })
}

export async function apiGetMe() {
  return apiFetch<{
    role: "passenger" | "crew"
    session_id: string
    seat_label?: string
    crew_id?: string
  }>("/api/auth/me")
}

export function deduplicateRequests(
  items: PassengerRequest[],
): PassengerRequest[] {
  const seen = new Set<string>()
  const out: PassengerRequest[] = []
  for (const item of items) {
    if (!item.id || seen.has(item.id)) continue
    seen.add(item.id)
    out.push(item)
  }
  return out
}

export function mapBackendRequestToFigma(raw: any): PassengerRequest {
  const metaMap = getRequestMetaMap()
  const id = raw.id || raw.request_id
  const meta = metaMap[id] || {}
  const category = (
    [
      "water_request",
      "blanket_request",
      "pillow_request",
      "accessibility_assist",
    ].includes(raw.intent_id)
      ? raw.intent_id
      : "water_request"
  ) as RequestCategory

  const catInfo = translations.en.categories[category]
  const intentMeta = INTENT_CATALOG[category]
  const rawStatus = (raw.status || "PENDING").toUpperCase() as RequestStatus
  const status: RequestStatus =
    meta.cancelled && rawStatus === "PENDING" ? "CANCELLED" : rawStatus

  return {
    id,
    seat_label: raw.seat_label || "18A",
    intent_id: raw.intent_id || category,
    category,
    priority:
      raw.priority?.toUpperCase() === "URGENT" ||
      intentMeta?.priority === "URGENT"
        ? "URGENT"
        : "ROUTINE",
    title: `${catInfo.label} (${catInfo.subLabel})`,
    attributes: meta.attributes || raw.attributes || {},
    created_at_ms: raw.created_at_ms || raw.created_at || Date.now(),
    updated_at_ms: raw.updated_at_ms || raw.updated_at || Date.now(),
    status,
    notes: meta.notes ?? raw.notes ?? "",
    crew_reply_id: meta.crew_reply_id,
    crew_reply_text_en: meta.crew_reply_text_en,
    crew_reply_text_ja: meta.crew_reply_text_ja,
  }
}

export function mapBackendBroadcastToFigma(raw: any): PABroadcast | null {
  if (!raw) return null
  const isActive =
    raw.active_status === true ||
    raw.active_status === "ACTIVE" ||
    raw.is_active === true
  const expiresAtMs = raw.expires_at_ms || raw.expires_at || 0
  if (!isActive || expiresAtMs <= Date.now()) return null

  const backendCardId = raw.pa_card_id || ""
  const figmaCardId =
    BACKEND_TO_FIGMA_PA[backendCardId] ||
    (APPROVED_PA_CARDS.some((c) => c.pa_card_id === backendCardId)
      ? backendCardId
      : APPROVED_PA_CARDS[0].pa_card_id)

  const card =
    APPROVED_PA_CARDS.find((c) => c.pa_card_id === figmaCardId) ||
    APPROVED_PA_CARDS[0]

  return {
    broadcast_id: raw.id || raw.broadcast_id || `pa_${Date.now()}`,
    pa_card_id: card.pa_card_id,
    category: card.category,
    title_en: card.title_en,
    title_ja: card.title_ja,
    title_zh: card.title_zh,
    title_hi: card.title_hi,
    title_ta: card.title_ta,
    title_mr: card.title_mr,
    text_en: card.text_en,
    text_ja: card.text_ja,
    text_zh: card.text_zh,
    text_hi: card.text_hi,
    text_ta: card.text_ta,
    text_mr: card.text_mr,
    created_at_ms: raw.created_at_ms || raw.created_at || Date.now(),
    expires_at_ms: expiresAtMs,
    active_status: "ACTIVE",
  }
}

export async function apiCreateRequest(data: {
  category: RequestCategory
  notes: string
  attributes?: Record<string, string>
}): Promise<{ ok: boolean; status: number; request?: PassengerRequest }> {
  const clientRequestId = `req_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`
  const res = await apiFetch("/api/requests", {
    method: "POST",
    body: JSON.stringify({
      intent_id: data.category,
      client_request_id: clientRequestId,
    }),
  })

  if (res.ok && res.data) {
    const reqObj = res.data.request || res.data
    const reqId = reqObj.id || reqObj.request_id
    if (reqId) {
      saveRequestMeta(reqId, {
        attributes: data.attributes || {},
        notes: data.notes || "",
        cancelled: false,
      })
      if (data.notes) {
        apiFetch(`/api/crew/requests/${reqId}/follow_up`, {
          method: "POST",
          body: JSON.stringify({ message: data.notes }),
        }).catch(() => {})
      }
    }
    return {
      ok: true,
      status: res.status,
      request: mapBackendRequestToFigma(reqObj),
    }
  }
  return { ok: false, status: res.status }
}

export async function apiAcknowledgeRequest(id: string) {
  const res = await apiFetch(`/api/crew/requests/${id}/acknowledge`, {
    method: "POST",
    body: JSON.stringify({}),
  })
  notifyCrossTabSync()
  return res
}

export async function apiCompleteRequest(id: string) {
  const res = await apiFetch(`/api/crew/requests/${id}/complete`, {
    method: "POST",
    body: JSON.stringify({}),
  })
  notifyCrossTabSync()
  return res
}

export async function apiSendCrewReply(id: string, reply: CrewResponse) {
  saveRequestMeta(id, {
    crew_reply_id: reply.reply_id,
    crew_reply_text_en: reply.text_en,
    crew_reply_text_ja: reply.text_ja,
  })
  const backendResponseId =
    FIGMA_TO_BACKEND_REPLY[reply.reply_id] || "crew_on_the_way"
  const res = await apiFetch(`/api/crew/requests/${id}/acknowledge`, {
    method: "POST",
    body: JSON.stringify({ response_id: backendResponseId }),
  })
  notifyCrossTabSync()
  return res
}

export function applySocketCrewReply(payload: {
  request_id: string
  response_id: string
  labels?: Record<string, string>
}) {
  if (!payload?.request_id) return
  const existing = getRequestMetaMap()[payload.request_id]
  if (existing?.crew_reply_text_en) return
  const figmaReplyId =
    BACKEND_TO_FIGMA_REPLY[payload.response_id] || "reply_on_the_way"
  const matched =
    APPROVED_CREW_RESPONSES.find((r) => r.reply_id === figmaReplyId) ||
    APPROVED_CREW_RESPONSES[0]
  saveRequestMeta(payload.request_id, {
    crew_reply_id: matched.reply_id,
    crew_reply_text_en: payload.labels?.en || matched.text_en,
    crew_reply_text_ja: payload.labels?.ja || matched.text_ja,
  })
}

export async function apiStartBroadcast(
  figmaCardId: string,
  durationSeconds: number,
) {
  const backendCardId = FIGMA_TO_BACKEND_PA[figmaCardId] || "turbulence"
  const res = await apiFetch("/api/crew/pa/broadcast", {
    method: "POST",
    body: JSON.stringify({
      pa_card_id: backendCardId,
      duration_seconds: durationSeconds,
    }),
  })
  notifyCrossTabSync()
  return res
}

export async function apiEndBroadcast(broadcastId: string) {
  const res = await apiFetch("/api/crew/pa/end", {
    method: "POST",
    body: JSON.stringify({ broadcast_id: broadcastId }),
  })
  notifyCrossTabSync()
  return res
}
