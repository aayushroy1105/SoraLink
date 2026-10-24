import React, { useState, useEffect, useCallback, useRef } from "react"
import {
  PassengerRequest,
  RequestCategory,
  Language,
  AppScreen,
  PABroadcast,
  CrewResponse,
} from "./types"
import { translations } from "./utils/translations"
import { APPROVED_PA_CARDS, INTENT_CATALOG } from "./data/canonicalData"
import { Header } from "./components/Header"
import { RequestGrid } from "./components/RequestGrid"
import { RequestModal } from "./components/RequestModal"
import { VoiceModal } from "./components/VoiceModal"
import { TypedRequestModal } from "./components/TypedRequestModal"
import { ActiveRequests } from "./components/ActiveRequests"
import { ActivePABanner } from "./components/ActivePABanner"
import { PassengerLogin } from "./components/PassengerLogin"
import { CrewLogin } from "./components/CrewLogin"
import { CrewDashboard } from "./components/CrewDashboard"
import { Mic, Edit3, WifiOff } from "lucide-react"
import { playCabinChime, playSoftTap } from "./utils/audio"
import {
  apiFetch,
  apiGetMe,
  apiLogout,
  apiCreateRequest,
  apiAcknowledgeRequest,
  apiCompleteRequest,
  apiSendCrewReply,
  apiStartBroadcast,
  apiEndBroadcast,
  mapBackendRequestToFigma,
  mapBackendBroadcastToFigma,
  saveRequestMeta,
  applySocketCrewReply,
  deduplicateRequests,
  onCrossTabSync,
} from "./utils/api"

const INITIAL_REQUESTS: PassengerRequest[] = []

/**
 * Dedicated Crew Route Detection
 * Conforms to Master Implementation Plan Section 11.2 and Rule 5.
 * Supported entry points:
 *   - Hash: #crew, #/crew, #crew-login, #crew-dashboard
 *   - Path: /crew, /crew/login, /crew/dashboard, or any sub-path ending in /crew
 *   - Query: ?portal=crew, ?role=crew, ?crew=true, ?crew
 */
export const isCrewRoute = (): boolean => {
  if (typeof window === "undefined") return false
  const hash = (window.location.hash || "").toLowerCase()
  const path = (window.location.pathname || "").toLowerCase()
  const search = (window.location.search || "").toLowerCase()

  return (
    hash.includes("crew") ||
    path.endsWith("/crew") ||
    path.endsWith("/crew/") ||
    path.includes("/crew/") ||
    search.includes("portal=crew") ||
    search.includes("role=crew") ||
    search.includes("crew=true") ||
    search === "?crew" ||
    search.startsWith("?crew&") ||
    search.includes("&crew")
  )
}

export const isExplicitLoginRoute = (): boolean => {
  if (typeof window === "undefined") return false
  const path = (window.location.pathname || "").toLowerCase()
  return path === "/login" || path === "/login/"
}

export default function App() {
  // Language state with localStorage persistence for EN, JA, ZH, HI, TA, MR
  const [currentLanguage, setCurrentLanguage] = useState<Language>(() => {
    try {
      const saved = localStorage.getItem("soralink_language")
      if (saved && ["en", "ja", "zh", "hi", "ta", "mr"].includes(saved)) {
        return saved as Language
      }
    } catch {}
    return "en"
  })

  useEffect(() => {
    try {
      localStorage.setItem("soralink_language", currentLanguage)
    } catch {}
  }, [currentLanguage])

  // Authentication & session state
  const [passengerSeat, setPassengerSeat] = useState<string>(() => {
    try {
      return localStorage.getItem("soralink_passenger_seat") || ""
    } catch {
      return ""
    }
  })

  const [isCrewAuthenticated, setIsCrewAuthenticated] = useState<boolean>(
    () => {
      try {
        return sessionStorage.getItem("soralink_crew_auth") === "true"
      } catch {
        return false
      }
    },
  )

  // Truthful connectivity tracking
  const [isOnline, setIsOnline] = useState<boolean>(() => {
    return typeof navigator !== "undefined" ? navigator.onLine : true
  })

  useEffect(() => {
    const handleOnline = () => setIsOnline(true)
    const handleOffline = () => setIsOnline(false)

    window.addEventListener("online", handleOnline)
    window.addEventListener("offline", handleOffline)

    return () => {
      window.removeEventListener("online", handleOnline)
      window.removeEventListener("offline", handleOffline)
    }
  }, [])

  // App screen state determined strictly by dedicated URL route and auth
  const [currentScreen, setCurrentScreen] = useState<AppScreen>(() => {
    if (isCrewRoute()) {
      try {
        if (sessionStorage.getItem("soralink_crew_auth") === "true") {
          return "crew-dashboard"
        }
      } catch {}
      return "crew-login"
    }
    if (isExplicitLoginRoute()) {
      return "passenger-login"
    }
    const savedSeat = (() => {
      try {
        return localStorage.getItem("soralink_passenger_seat")
      } catch {
        return null
      }
    })()
    return savedSeat ? "passenger-home" : "passenger-login"
  })

  // Listen to hash, popstate, and pushstate changes for dedicated crew routing
  useEffect(() => {
    const handleLocationChange = () => {
      if (isCrewRoute()) {
        try {
          const isAuth = sessionStorage.getItem("soralink_crew_auth") === "true"
          setCurrentScreen(isAuth ? "crew-dashboard" : "crew-login")
        } catch {
          setCurrentScreen("crew-login")
        }
      } else if (isExplicitLoginRoute()) {
        setCurrentScreen("passenger-login")
      } else {
        try {
          const savedSeat = localStorage.getItem("soralink_passenger_seat")
          setCurrentScreen(savedSeat ? "passenger-home" : "passenger-login")
        } catch {
          setCurrentScreen("passenger-login")
        }
      }
    }

    window.addEventListener("hashchange", handleLocationChange)
    window.addEventListener("popstate", handleLocationChange)

    return () => {
      window.removeEventListener("hashchange", handleLocationChange)
      window.removeEventListener("popstate", handleLocationChange)
    }
  }, [isCrewAuthenticated, passengerSeat])

  // Accessibility / staff keyboard shortcut (Alt+C or Ctrl+Shift+C) to switch route
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (
        (e.altKey && (e.key === "c" || e.key === "C")) ||
        (e.ctrlKey && e.shiftKey && (e.key === "c" || e.key === "C"))
      ) {
        e.preventDefault()
        if (isCrewRoute()) {
          window.location.hash = ""
        } else {
          window.location.hash = "crew"
        }
      }
    }
    window.addEventListener("keydown", handleKeyDown)
    return () => window.removeEventListener("keydown", handleKeyDown)
  }, [])

  // Programmatic helpers exposed on window for testing or script verification
  useEffect(() => {
    if (typeof window !== "undefined") {
      ;(window as any).navigateToCrew = () => {
        window.location.hash = "crew"
      }
      ;(window as any).navigateToPassenger = () => {
        window.location.hash = ""
      }
    }
  }, [])

  // Requests state adhering strictly to canonical RequestStatus (PENDING, ACKNOWLEDGED, COMPLETED, CANCELLED)
  const [requests, setRequests] = useState<PassengerRequest[]>(() => {
    try {
      const saved = localStorage.getItem("soralink_canonical_requests")
      if (saved) {
        return JSON.parse(saved) as PassengerRequest[]
      }
    } catch (e) {
      // fallback
    }
    return INITIAL_REQUESTS
  })

  // Active PA announcement broadcast state
  const [activeBroadcast, setActiveBroadcast] = useState<PABroadcast | null>(
    () => {
      try {
        const saved = localStorage.getItem("soralink_active_broadcast")
        if (saved) {
          const parsed = JSON.parse(saved) as PABroadcast
          if (
            parsed.expires_at_ms > Date.now() &&
            parsed.active_status === "ACTIVE"
          ) {
            return parsed
          }
        }
      } catch {
        // fallback
      }
      return null
    },
  )

  const [activeCategoryModal, setActiveCategoryModal] =
    useState<RequestCategory | null>(null)
  const [isVoiceModalOpen, setIsVoiceModalOpen] = useState(false)
  const [isTypedModalOpen, setIsTypedModalOpen] = useState(false)

  // Sync state with real backend API
  const syncFromBackend = useCallback(async () => {
    if (currentScreen === "passenger-home") {
      const res = await apiFetch<{
        seat_label: string
        requests: any[]
        active_broadcasts: any[]
      }>("/api/passenger/state")
      if (res.status === 401 || res.status === 403) {
        setPassengerSeat("")
        try {
          localStorage.removeItem("soralink_passenger_seat")
        } catch {}
        setCurrentScreen("passenger-login")
        return
      }
      if (res.ok && res.data) {
        if (res.data.seat_label) {
          setPassengerSeat(res.data.seat_label)
        }
        if (Array.isArray(res.data.requests)) {
          const mapped = deduplicateRequests(
            res.data.requests.map(mapBackendRequestToFigma),
          )
          setRequests(mapped)
        }
        if (Array.isArray(res.data.active_broadcasts)) {
          const firstActive = res.data.active_broadcasts
            .map(mapBackendBroadcastToFigma)
            .find(Boolean)
          setActiveBroadcast(firstActive || null)
        }
      }
    } else if (currentScreen === "crew-dashboard") {
      const [reqRes, paRes] = await Promise.all([
        apiFetch<{ requests: any[] }>(
          "/api/crew/requests?include_completed=true",
        ),
        apiFetch<{ broadcasts: any[] }>("/api/crew/pa/broadcasts"),
      ])
      if (reqRes.status === 401 || reqRes.status === 403) {
        setIsCrewAuthenticated(false)
        try {
          sessionStorage.removeItem("soralink_crew_auth")
        } catch {}
        setCurrentScreen("crew-login")
        return
      }
      if (reqRes.ok && reqRes.data && Array.isArray(reqRes.data.requests)) {
        const mapped = deduplicateRequests(
          reqRes.data.requests.map(mapBackendRequestToFigma),
        )
        setRequests(mapped)
      }
      if (paRes.ok && paRes.data && Array.isArray(paRes.data.broadcasts)) {
        const firstActive = paRes.data.broadcasts
          .map(mapBackendBroadcastToFigma)
          .find(Boolean)
        setActiveBroadcast(firstActive || null)
      }
    }
  }, [currentScreen])

  // Check active backend session on startup
  useEffect(() => {
    apiGetMe().then((res) => {
      if (res.ok && res.data) {
        if (res.data.role === "crew" && isCrewRoute()) {
          setIsCrewAuthenticated(true)
          try {
            sessionStorage.setItem("soralink_crew_auth", "true")
          } catch {}
          setCurrentScreen("crew-dashboard")
        } else if (res.data.role === "passenger" && !isCrewRoute()) {
          if (res.data.seat_label) {
            setPassengerSeat(res.data.seat_label)
          }
          if (!isExplicitLoginRoute()) {
            setCurrentScreen("passenger-home")
          }
        }
      } else if (res.status === 401) {
        if (isCrewRoute()) {
          setIsCrewAuthenticated(false)
          try {
            sessionStorage.removeItem("soralink_crew_auth")
          } catch {}
          setCurrentScreen("crew-login")
        } else {
          setPassengerSeat("")
          try {
            localStorage.removeItem("soralink_passenger_seat")
          } catch {}
          setCurrentScreen("passenger-login")
        }
      }
    })
  }, [])

  // Trigger backend sync when entering passenger-home or crew-dashboard, plus periodic & storage sync
  useEffect(() => {
    if (
      currentScreen !== "passenger-home" &&
      currentScreen !== "crew-dashboard"
    ) {
      return
    }
    syncFromBackend()
    const interval = setInterval(syncFromBackend, 2500)
    const onStorage = () => syncFromBackend()
    window.addEventListener("storage", onStorage)
    const unsubCrossTab = onCrossTabSync(() => syncFromBackend())
    return () => {
      clearInterval(interval)
      window.removeEventListener("storage", onStorage)
      unsubCrossTab()
    }
  }, [currentScreen, syncFromBackend])

  // Connect Socket.IO for instant real-time updates
  const socketRef = useRef<any>(null)
  useEffect(() => {
    if (
      currentScreen !== "passenger-home" &&
      currentScreen !== "crew-dashboard"
    ) {
      if (socketRef.current) {
        try {
          socketRef.current.removeAllListeners?.()
        } catch {}
        socketRef.current.disconnect()
        socketRef.current = null
      }
      return
    }

    const ioGlobal = typeof window !== "undefined" ? (window as any).io : null
    if (!ioGlobal) return

    const socket = ioGlobal({
      withCredentials: true,
      transports: ["websocket", "polling"],
    })
    socketRef.current = socket

    socket.on("connect", () => {
      try {
        socket.emit("request_resync", {})
      } catch {}
      syncFromBackend()
    })
    socket.on("connection_ready", () => {
      syncFromBackend()
    })
    socket.on("state_resync_required", () => {
      syncFromBackend()
    })
    socket.on("request_created", () => {
      syncFromBackend()
    })
    socket.on("request_updated", () => {
      syncFromBackend()
    })
    socket.on("follow_up_requested", () => {
      syncFromBackend()
    })
    socket.on("crew_reply", (payload: any) => {
      applySocketCrewReply(payload)
      syncFromBackend()
    })
    socket.on("pa_broadcast_created", (payload: any) => {
      const mapped = mapBackendBroadcastToFigma(payload)
      if (mapped) setActiveBroadcast(mapped)
      syncFromBackend()
    })
    socket.on("pa_broadcast_ended", () => {
      setActiveBroadcast(null)
      syncFromBackend()
    })

    return () => {
      try {
        socket.removeAllListeners?.()
      } catch {}
      socket.disconnect()
      socketRef.current = null
    }
  }, [currentScreen, syncFromBackend])

  // Sync requests to storage
  useEffect(() => {
    try {
      localStorage.setItem(
        "soralink_canonical_requests",
        JSON.stringify(requests),
      )
    } catch (e) {
      console.warn("Storage sync failed", e)
    }
  }, [requests])

  // Sync passenger seat
  useEffect(() => {
    try {
      if (passengerSeat) {
        localStorage.setItem("soralink_passenger_seat", passengerSeat)
      } else {
        localStorage.removeItem("soralink_passenger_seat")
      }
    } catch {
      // fallback
    }
  }, [passengerSeat])

  // Sync active PA broadcast
  useEffect(() => {
    try {
      if (activeBroadcast) {
        localStorage.setItem(
          "soralink_active_broadcast",
          JSON.stringify(activeBroadcast),
        )
      } else {
        localStorage.removeItem("soralink_active_broadcast")
      }
    } catch {
      // fallback
    }
  }, [activeBroadcast])

  // Passenger Request Creation: creates on backend and updates state without duplicate IDs
  const handleCreateRequest = (data: {
    category: RequestCategory
    subDetails: string
    notes: string
    attributes?: Record<string, string>
  }) => {
    const catInfo = translations[currentLanguage].categories[data.category]
    const intentMeta = INTENT_CATALOG[data.category]

    apiCreateRequest({
      category: data.category,
      notes: data.notes || "",
      attributes: data.attributes || {},
    }).then((res) => {
      if (res.ok && res.request) {
        const serverReq = res.request
        setRequests((prev) => deduplicateRequests([serverReq, ...prev]))
        syncFromBackend()
      } else if (res.status === 0) {
        // Offline local fallback when network is unreachable
        const tempId = `req_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 6)}`
        const fallbackRequest: PassengerRequest = {
          id: tempId,
          seat_label: passengerSeat || "18A",
          intent_id: data.category,
          category: data.category,
          priority:
            intentMeta?.priority ||
            (data.category === "accessibility_assist" ? "URGENT" : "ROUTINE"),
          title: `${catInfo.label} (${catInfo.subLabel})`,
          attributes: data.attributes || {},
          created_at_ms: Date.now(),
          updated_at_ms: Date.now(),
          status: "PENDING",
          notes: data.notes || "",
        }
        setRequests((prev) => deduplicateRequests([fallbackRequest, ...prev]))
      } else if (res.status === 401 || res.status === 403) {
        syncFromBackend()
      }
    })
  }

  // Section 7.5: Passenger can cancel only when PENDING
  const handleCancelRequest = (id: string) => {
    saveRequestMeta(id, { cancelled: true })
    setRequests((prev) =>
      prev.map((r) =>
        r.id === id && r.status === "PENDING"
          ? { ...r, status: "CANCELLED" as const, updated_at_ms: Date.now() }
          : r,
      ),
    )
  }

  // Section 7.5 & 9.9: Crew Acknowledge (PENDING -> ACKNOWLEDGED)
  const handleAcknowledgeRequest = (id: string) => {
    setRequests((prev) =>
      prev.map((r) =>
        r.id === id && r.status === "PENDING"
          ? { ...r, status: "ACKNOWLEDGED" as const, updated_at_ms: Date.now() }
          : r,
      ),
    )
    apiAcknowledgeRequest(id).then(() => {
      syncFromBackend()
    })
  }

  // Section 7.5 & 9.9: Crew Complete (ACKNOWLEDGED -> COMPLETED)
  const handleCompleteRequest = (id: string) => {
    setRequests((prev) =>
      prev.map((r) =>
        r.id === id && r.status === "ACKNOWLEDGED"
          ? { ...r, status: "COMPLETED" as const, updated_at_ms: Date.now() }
          : r,
      ),
    )
    apiCompleteRequest(id).then(() => {
      syncFromBackend()
    })
  }

  // Section 9.10: Crew Reply
  const handleSendReplyToRequest = (id: string, reply: CrewResponse) => {
    setRequests((prev) =>
      prev.map((r) =>
        r.id === id
          ? {
              ...r,
              crew_reply_id: reply.reply_id,
              crew_reply_text_en: reply.text_en,
              crew_reply_text_ja: reply.text_ja,
              updated_at_ms: Date.now(),
            }
          : r,
      ),
    )
    apiSendCrewReply(id, reply).then(() => {
      syncFromBackend()
    })
  }

  // Section 14.2: Crew PA Announcement Activation
  const handleStartBroadcast = (cardId: string, durationSeconds: number) => {
    const card = APPROVED_PA_CARDS.find((c) => c.pa_card_id === cardId)
    if (!card) return

    const now = Date.now()
    const broadcast: PABroadcast = {
      broadcast_id: `pa_${now.toString(36)}`,
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
      created_at_ms: now,
      expires_at_ms: now + durationSeconds * 1000,
      active_status: "ACTIVE",
    }
    setActiveBroadcast(broadcast)

    apiStartBroadcast(cardId, durationSeconds).then((res) => {
      if (res.ok && res.data) {
        const mapped = mapBackendBroadcastToFigma(
          res.data.broadcast || res.data,
        )
        if (mapped) setActiveBroadcast(mapped)
      }
    })
  }

  // Section 14.3: Crew PA Announcement Ending
  const handleEndBroadcast = useCallback(() => {
    setActiveBroadcast((prev) => {
      if (prev && prev.broadcast_id) {
        apiEndBroadcast(prev.broadcast_id).catch(() => {})
      }
      return null
    })
  }, [])

  // Active counts for the 4 canonical visual cards
  const activeCountByCategory = requests
    .filter((r) => r.status === "PENDING" || r.status === "ACKNOWLEDGED")
    .reduce(
      (acc, curr) => {
        if (curr.category) {
          acc[curr.category] = (acc[curr.category] || 0) + 1
        }
        return acc
      },
      {} as Record<RequestCategory, number>,
    )

  const t = translations[currentLanguage]

  const voiceBadgeLabel =
    currentLanguage === "ja"
      ? "Voice / 音声"
      : currentLanguage === "zh"
        ? "Voice / 語音"
        : currentLanguage === "hi"
          ? "Voice / आवाज़"
          : currentLanguage === "ta"
            ? "Voice / குரல்"
            : currentLanguage === "mr"
              ? "Voice / आवाज"
              : "Voice"

  return (
    <div className="min-h-dvh w-full overflow-x-clip bg-[#FAF8F3] flex flex-col relative text-[#202124]">
      {/* 
        Header with SoraLink branding, 6-language switcher, and sound toggle.
        The passenger and crew experiences are completely separated per Section 5.
      */}
      <Header
        currentLanguage={currentLanguage}
        onLanguageChange={setCurrentLanguage}
        seatLabel={passengerSeat}
        currentScreen={currentScreen}
        onLogoutCrew={() => {
          apiLogout().catch(() => {})
          setIsCrewAuthenticated(false)
          try {
            sessionStorage.removeItem("soralink_crew_auth")
          } catch {}
          setCurrentScreen("crew-login")
          if (
            !window.location.hash.includes("crew") &&
            !window.location.pathname.includes("/crew")
          ) {
            window.location.hash = "crew"
          }
        }}
      />

      {/* Truthful Offline Banner (Displayed only when device is actually offline) */}
      {!isOnline && (
        <div
          role="status"
          className="w-full bg-[#202124] text-white px-4 py-2 text-xs flex items-center justify-center gap-2 border-b border-[#C8102E]"
        >
          <WifiOff className="w-3.5 h-3.5 text-[#C8102E] shrink-0" />
          <span className="font-medium">{t.offlineNotice}</span>
        </div>
      )}

      {/* Screen Routing */}
      {currentScreen === "passenger-login" ? (
        <PassengerLogin
          currentLanguage={currentLanguage}
          onLoginSuccess={(seat) => {
            setPassengerSeat(seat)
            if (isExplicitLoginRoute()) {
              try {
                window.history.pushState({}, "", "/passenger")
              } catch {}
            }
            setCurrentScreen("passenger-home")
          }}
        />
      ) : currentScreen === "crew-login" ? (
        <CrewLogin
          currentLanguage={currentLanguage}
          onLoginSuccess={() => {
            setIsCrewAuthenticated(true)
            try {
              sessionStorage.setItem("soralink_crew_auth", "true")
            } catch {}
            setCurrentScreen("crew-dashboard")
          }}
        />
      ) : currentScreen === "crew-dashboard" ? (
        <CrewDashboard
          currentLanguage={currentLanguage}
          requests={requests}
          activeBroadcast={activeBroadcast}
          onAcknowledgeRequest={handleAcknowledgeRequest}
          onCompleteRequest={handleCompleteRequest}
          onSendReplyToRequest={handleSendReplyToRequest}
          onStartBroadcast={handleStartBroadcast}
          onEndBroadcast={handleEndBroadcast}
          onLogout={() => {
            apiLogout().catch(() => {})
            setIsCrewAuthenticated(false)
            try {
              sessionStorage.removeItem("soralink_crew_auth")
            } catch {}
            setCurrentScreen("crew-login")
          }}
        />
      ) : (
        /* Passenger Homepage (Screen B) */
        <main className="flex-1 w-full max-w-6xl mx-auto px-3 py-4 sm:px-6 sm:py-6 lg:px-8 pb-[max(1.5rem,env(safe-area-inset-bottom))] space-y-6">
          {/* Active Public Announcement Banner (Section 13.1 Screen B & Section 14) */}
          <ActivePABanner
            broadcast={activeBroadcast}
            currentLanguage={currentLanguage}
          />

          <div className="grid grid-cols-1 gap-6 lg:grid-cols-[minmax(0,7fr)_minmax(0,5fr)] lg:gap-8 lg:items-start">
            {/* Left Column: Visual Request Cards & Speak/Type Flows */}
            <div className="min-w-0 space-y-6">
              {/* Heading & Hospitality Subtitle */}
              <section className="text-left space-y-1 pt-1">
                <h1 className="font-['Noto_Serif_JP',serif] text-2xl sm:text-3xl font-bold tracking-tight text-[#202124] leading-tight">
                  {t.heading}
                </h1>

                <p className="text-xs sm:text-sm text-[#5F6368] leading-relaxed max-w-xl font-normal">
                  {t.supportingText}
                </p>
              </section>

              {/* The 4 Canonical Visual Service Cards */}
              <section aria-label="Passenger Request Categories">
                <RequestGrid
                  currentLanguage={currentLanguage}
                  onSelectCategory={(cat) => setActiveCategoryModal(cat)}
                  activeCountByCategory={activeCountByCategory}
                />
              </section>

              {/* Speak / Request Flow Action */}
              <section className="space-y-2.5 pt-1">
                <button
                  type="button"
                  onClick={() => {
                    playCabinChime()
                    setIsVoiceModalOpen(true)
                  }}
                  className="w-full relative group overflow-hidden min-h-16 py-3.5 px-4 sm:px-5 rounded-2xl bg-[#C8102E] hover:bg-[#B00E28] active:bg-[#8F0A20] text-white shadow-md hover:shadow-lg transition-all duration-200 flex items-center justify-between active:scale-[0.99] focus:outline-hidden focus:ring-2 focus:ring-[#C8102E] focus:ring-offset-2 cursor-pointer"
                  aria-label={t.speakButton}
                >
                  <div className="absolute right-0 top-0 bottom-0 w-28 pointer-events-none opacity-10 flex items-center justify-end pr-3">
                    <Mic className="w-20 h-20" />
                  </div>

                  <div className="flex items-center gap-3.5 min-w-0 z-10">
                    <div className="w-11 h-11 rounded-full bg-white/15 flex items-center justify-center shrink-0 group-hover:scale-105 transition-transform">
                      <Mic className="w-5 h-5 text-white" />
                    </div>
                    <div className="text-left min-w-0">
                      <span className="font-bold text-sm sm:text-base leading-tight block truncate">
                        {t.speakButton}
                      </span>
                      <span className="text-[11px] sm:text-xs text-white/80 font-normal leading-tight block truncate mt-0.5">
                        {t.speakSubtext}
                      </span>
                    </div>
                  </div>

                  <div className="flex items-center gap-2 z-10 shrink-0">
                    <span className="hidden min-[380px]:inline-flex px-2.5 py-1 rounded-full bg-white/20 text-[11px] font-semibold tracking-wide">
                      {voiceBadgeLabel}
                    </span>
                  </div>
                </button>

                {/* Typed Request Alternative */}
                <button
                  type="button"
                  onClick={() => {
                    playSoftTap()
                    setIsTypedModalOpen(true)
                  }}
                  className="w-full min-h-12 py-2.5 px-4 rounded-xl bg-white hover:bg-[#FAF8F3] border border-[#202124]/[0.08] text-[#202124] text-xs font-semibold shadow-2xs hover:shadow-xs transition-all flex items-center justify-center gap-2 active:scale-[0.99] cursor-pointer"
                >
                  <Edit3 className="w-4 h-4 text-[#5F6368]" />
                  <span>{t.typedButton}</span>
                </button>
              </section>
            </div>

            {/* Right Column: Active Requests Section (Screen D) */}
            <div className="min-w-0">
              <ActiveRequests
                requests={requests}
                currentLanguage={currentLanguage}
                onCancelRequest={handleCancelRequest}
              />
            </div>
          </div>

          {/* Visual Category Modal */}
          <RequestModal
            isOpen={Boolean(activeCategoryModal)}
            onClose={() => setActiveCategoryModal(null)}
            category={activeCategoryModal}
            currentLanguage={currentLanguage}
            onSubmit={(data) => {
              handleCreateRequest(data)
            }}
          />

          {/* Voice Review & Confirmation Modal (Screen C) */}
          <VoiceModal
            isOpen={isVoiceModalOpen}
            onClose={() => setIsVoiceModalOpen(false)}
            currentLanguage={currentLanguage}
            onSwitchToTyped={() => setIsTypedModalOpen(true)}
            onSubmit={(data) => {
              handleCreateRequest(data)
            }}
          />

          {/* Typed Request Alternative Modal */}
          <TypedRequestModal
            isOpen={isTypedModalOpen}
            onClose={() => setIsTypedModalOpen(false)}
            currentLanguage={currentLanguage}
            onSubmit={(data) => {
              handleCreateRequest(data)
            }}
          />
        </main>
      )}
    </div>
  )
}
