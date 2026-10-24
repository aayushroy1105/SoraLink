import React, { useState, useEffect } from "react"
import {
  PassengerRequest,
  Language,
  RequestStatus,
  PABroadcast,
  CrewResponse,
} from "../types"
import { translations } from "../utils/translations"
import { APPROVED_PA_CARDS } from "../data/canonicalData"
import { CrewReplyModal } from "./CrewReplyModal"
import { CategoryIcon } from "./RequestIcons"
import {
  Megaphone,
  Clock,
  CheckCircle2,
  AlertTriangle,
  Radio,
  Send,
  XCircle,
  Timer,
  Filter,
} from "lucide-react"
import { playSoftTap, playCabinChime } from "../utils/audio"

interface CrewDashboardProps {
  currentLanguage: Language
  requests: PassengerRequest[]
  activeBroadcast: PABroadcast | null
  onAcknowledgeRequest: (id: string) => void
  onCompleteRequest: (id: string) => void
  onSendReplyToRequest: (id: string, reply: CrewResponse) => void
  onStartBroadcast: (cardId: string, durationSeconds: number) => void
  onEndBroadcast: () => void
  onLogout?: () => void
}

export const CrewDashboard: React.FC<CrewDashboardProps> = ({
  currentLanguage,
  requests,
  activeBroadcast,
  onAcknowledgeRequest,
  onCompleteRequest,
  onSendReplyToRequest,
  onStartBroadcast,
  onEndBroadcast,
}) => {
  const t = translations[currentLanguage]

  // Filter state
  const [statusFilter, setStatusFilter] = useState<"ALL" | RequestStatus>("ALL")

  // PA Form state
  const [selectedPaCardId, setSelectedPaCardId] = useState<string>(
    APPROVED_PA_CARDS[0].pa_card_id,
  )
  const [selectedDuration, setSelectedDuration] = useState<number>(180)

  // Reply Modal state
  const [replyTargetRequest, setReplyTargetRequest] =
    useState<PassengerRequest | null>(null)

  // Countdown timer for active announcement
  const [timeRemainingSeconds, setTimeRemainingSeconds] = useState<number>(0)

  useEffect(() => {
    if (!activeBroadcast || activeBroadcast.active_status !== "ACTIVE") {
      setTimeRemainingSeconds(0)
      return
    }

    const updateTimer = () => {
      const now = Date.now()
      const remaining = Math.max(
        0,
        Math.floor((activeBroadcast.expires_at_ms - now) / 1000),
      )
      setTimeRemainingSeconds(remaining)
      if (remaining === 0) {
        onEndBroadcast()
      }
    }

    updateTimer()
    const interval = setInterval(updateTimer, 1000)
    return () => clearInterval(interval)
  }, [activeBroadcast, onEndBroadcast])

  // Sorting strictly per Section 9.8:
  // 1. URGENT before ROUTINE
  // 2. Older requests first within each priority (FIFO)
  const sortedRequests = [...requests].sort((a, b) => {
    if (a.priority === "URGENT" && b.priority !== "URGENT") return -1
    if (a.priority !== "URGENT" && b.priority === "URGENT") return 1
    return a.created_at_ms - b.created_at_ms
  })

  const filteredRequests = sortedRequests.filter((r) => {
    if (statusFilter === "ALL") return true
    return r.status === statusFilter
  })

  const urgentCount = requests.filter(
    (r) =>
      r.priority === "URGENT" &&
      r.status !== "COMPLETED" &&
      r.status !== "CANCELLED",
  ).length

  const pendingCount = requests.filter((r) => r.status === "PENDING").length
  const acknowledgedCount = requests.filter(
    (r) => r.status === "ACKNOWLEDGED",
  ).length
  const completedCount = requests.filter((r) => r.status === "COMPLETED").length

  const formatTime = (ts: number) => {
    return new Date(ts).toLocaleTimeString([], {
      hour: "2-digit",
      minute: "2-digit",
    })
  }

  const formatCountdown = (totalSeconds: number) => {
    const mins = Math.floor(totalSeconds / 60)
    const secs = totalSeconds % 60
    return `${mins}m ${secs.toString().padStart(2, "0")}s`
  }

  const handleBroadcastSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    playCabinChime()
    onStartBroadcast(selectedPaCardId, selectedDuration)
  }

  return (
    <div className="w-full max-w-6xl mx-auto px-4 py-4 sm:px-6 sm:py-6 lg:px-8 space-y-6">
      {/* Public Announcement (PA) Control Box positioned directly below main header */}
      <section className="bg-white rounded-2xl border border-[#202124]/[0.08] p-4 sm:p-5 shadow-xs space-y-4">
        <div className="flex items-center justify-between gap-2 border-b border-[#202124]/[0.06] pb-3">
          <div className="flex items-center gap-2">
            <div className="w-8 h-8 rounded-lg bg-[#FAF8F3] border border-[#202124]/10 flex items-center justify-center text-[#C8102E]">
              <Megaphone className="w-4 h-4" />
            </div>
            <div>
              <h2 className="font-['Noto_Serif_JP',serif] text-sm sm:text-base font-bold text-[#202124]">
                {t.crew.paTitle}
              </h2>
            </div>
          </div>

          {activeBroadcast && (
            <span className="flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-red-50 text-red-700 text-xs font-bold border border-red-200 animate-pulse">
              <Radio className="w-3.5 h-3.5" />
              <span>BROADCASTING</span>
            </span>
          )}
        </div>

        {activeBroadcast ? (
          <div className="p-4 rounded-xl bg-[#FAF8F3] border border-[#C8102E]/30 space-y-3">
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
              <div className="flex items-center gap-2">
                <span className="px-2 py-0.5 rounded-md bg-[#C8102E] text-white text-[10px] font-bold uppercase tracking-wider">
                  {activeBroadcast.category}
                </span>
                <span className="font-bold text-sm text-[#202124]">
                  {currentLanguage === "ja"
                    ? activeBroadcast.title_ja
                    : currentLanguage === "zh"
                      ? activeBroadcast.title_zh
                      : activeBroadcast.title_en}
                </span>
              </div>

              <div className="flex items-center gap-2 text-xs font-semibold text-[#5F6368]">
                <Timer className="w-4 h-4 text-[#C8102E]" />
                <span>{formatCountdown(timeRemainingSeconds)}</span>
              </div>
            </div>

            <p className="text-xs text-[#202124] italic bg-white p-3 rounded-lg border border-[#202124]/[0.06]">
              “
              {currentLanguage === "ja"
                ? activeBroadcast.text_ja
                : currentLanguage === "zh"
                  ? activeBroadcast.text_zh
                  : activeBroadcast.text_en}
              ”
            </p>

            <div className="flex justify-end pt-1">
              <button
                type="button"
                onClick={() => {
                  playSoftTap()
                  onEndBroadcast()
                }}
                className="px-4 min-h-11 rounded-xl bg-[#202124] hover:bg-black text-white text-xs font-semibold transition-colors flex items-center gap-1.5 cursor-pointer"
              >
                <XCircle className="w-3.5 h-3.5" />
                <span>{t.crew.paEndAction}</span>
              </button>
            </div>
          </div>
        ) : (
          <form
            onSubmit={handleBroadcastSubmit}
            className="grid grid-cols-1 md:grid-cols-[1fr_auto_auto] gap-3 items-end"
          >
            <div>
              <label className="block text-xs font-semibold text-[#5F6368] mb-1">
                {t.crew.paSelectCard}
              </label>
              <select
                value={selectedPaCardId}
                onChange={(e) => {
                  const cardId = e.target.value
                  setSelectedPaCardId(cardId)
                  const card = APPROVED_PA_CARDS.find(
                    (c) => c.pa_card_id === cardId,
                  )
                  if (card) setSelectedDuration(card.default_duration_seconds)
                }}
                className="w-full min-h-11 px-3 rounded-xl border border-[#202124]/15 bg-white text-xs text-[#202124] focus:outline-hidden focus:ring-2 focus:ring-[#C8102E]/40"
              >
                {APPROVED_PA_CARDS.map((card) => (
                  <option key={card.pa_card_id} value={card.pa_card_id}>
                    [{card.category}] {card.title_en} — {card.title_ja}
                  </option>
                ))}
              </select>
            </div>

            <div>
              <label className="block text-xs font-semibold text-[#5F6368] mb-1">
                {t.crew.paDuration}
              </label>
              <select
                value={selectedDuration}
                onChange={(e) => setSelectedDuration(Number(e.target.value))}
                className="w-full min-h-11 px-3 rounded-xl border border-[#202124]/15 bg-white text-xs text-[#202124] focus:outline-hidden focus:ring-2 focus:ring-[#C8102E]/40"
              >
                <option value={60}>1 min</option>
                <option value={180}>3 mins (Standard)</option>
                <option value={300}>5 mins</option>
                <option value={600}>10 mins</option>
              </select>
            </div>

            <button
              type="submit"
              className="min-h-11 px-4 rounded-xl bg-[#C8102E] hover:bg-[#B00E28] text-white text-xs font-bold transition-all shadow-xs flex items-center justify-center gap-1.5 active:scale-[0.98] cursor-pointer"
            >
              <Radio className="w-3.5 h-3.5" />
              <span>{t.crew.paBroadcastAction}</span>
            </button>
          </form>
        )}
      </section>

      {/* Main Request Queue Management */}
      <section className="space-y-4">
        {/* Filters and Counters Bar */}
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 bg-white p-3.5 rounded-2xl border border-[#202124]/[0.08] shadow-xs">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="text-xs font-bold text-[#202124] flex items-center gap-1.5 mr-2">
              <Filter className="w-3.5 h-3.5 text-[#5F6368]" />
              <span>{t.crew.queueSummary}</span>
            </span>

            {[
              { id: "ALL", label: t.crew.filterAll, count: requests.length },
              {
                id: "PENDING",
                label: t.crew.filterPending,
                count: pendingCount,
              },
              {
                id: "ACKNOWLEDGED",
                label: t.crew.filterAcknowledged,
                count: acknowledgedCount,
              },
              {
                id: "COMPLETED",
                label: t.crew.filterCompleted,
                count: completedCount,
              },
            ].map((f) => (
              <button
                key={f.id}
                type="button"
                onClick={() => {
                  playSoftTap()
                  setStatusFilter(f.id as any)
                }}
                className={`px-3 min-h-9 rounded-lg text-xs font-semibold transition-colors flex items-center gap-1.5 cursor-pointer ${
                  statusFilter === f.id
                    ? "bg-[#202124] text-white"
                    : "bg-[#FAF8F3] text-[#5F6368] hover:text-[#202124] hover:bg-stone-200/60"
                }`}
              >
                <span>{f.label}</span>
                <span
                  className={`px-1.5 py-0.2 rounded-full text-[10px] ${
                    statusFilter === f.id
                      ? "bg-white/20 text-white"
                      : "bg-[#202124]/10 text-[#202124]"
                  }`}
                >
                  {f.count}
                </span>
              </button>
            ))}
          </div>

          {urgentCount > 0 && (
            <div className="flex items-center gap-1.5 px-3 py-1 rounded-full bg-red-50 border border-red-200 text-red-800 text-xs font-bold shrink-0">
              <AlertTriangle className="w-3.5 h-3.5 text-[#C8102E]" />
              <span>
                {urgentCount} {t.crew.urgentBadge}
              </span>
            </div>
          )}
        </div>

        {/* Request Cards List */}
        {filteredRequests.length === 0 ? (
          <div className="p-12 rounded-3xl bg-white border border-[#202124]/[0.08] text-center shadow-xs">
            <div className="w-12 h-12 rounded-full bg-[#FAF8F3] border border-[#202124]/10 flex items-center justify-center mx-auto mb-3 text-emerald-700">
              <CheckCircle2 className="w-6 h-6" />
            </div>
            <h3 className="text-base font-bold text-[#202124]">
              {t.crew.emptyQueue}
            </h3>
            <p className="text-xs text-[#5F6368] mt-1 max-w-sm mx-auto">
              {t.crew.emptyQueueSub}
            </p>
          </div>
        ) : (
          <div className="space-y-3">
            {filteredRequests.map((req) => {
              const isUrgent = req.priority === "URGENT"
              const isPending = req.status === "PENDING"
              const isAcknowledged = req.status === "ACKNOWLEDGED"
              const isCompleted = req.status === "COMPLETED"
              const isCancelled = req.status === "CANCELLED"

              return (
                <div
                  key={req.id}
                  className={`rounded-2xl bg-white border shadow-xs overflow-hidden transition-all duration-200 ${
                    isUrgent && !isCompleted && !isCancelled
                      ? "border-[#C8102E]/40 ring-1 ring-[#C8102E]/20"
                      : "border-[#202124]/[0.08]"
                  }`}
                >
                  <div className="p-4 flex flex-col md:flex-row md:items-center justify-between gap-4">
                    {/* Left: Seat, Intent, Attributes, Time */}
                    <div className="flex items-start gap-3.5 min-w-0">
                      {/* Seat Badge */}
                      <div className="flex flex-col items-center justify-center min-w-14 px-2.5 py-1.5 rounded-xl bg-[#FAF8F3] border border-[#202124]/10 text-center shrink-0">
                        <span className="text-[9px] uppercase font-bold text-[#80868B] tracking-wider leading-none">
                          SEAT
                        </span>
                        <span className="text-base font-black text-[#202124] tracking-tight leading-tight">
                          {req.seat_label}
                        </span>
                      </div>

                      {/* Icon */}
                      <div className="w-10 h-10 rounded-xl bg-[#FAF8F3] border border-[#202124]/[0.06] flex items-center justify-center text-[#202124] shrink-0 mt-0.5">
                        <CategoryIcon
                          category={
                            req.category ||
                            req.intent_id as any ||
                            "water_request"
                          }
                          size={20}
                        />
                      </div>

                      {/* Details */}
                      <div className="min-w-0">
                        <div className="flex items-center gap-2 flex-wrap">
                          <span className="font-bold text-sm text-[#202124] break-words">
                            {req.title}
                          </span>

                          {/* Priority Badge */}
                          {isUrgent ? (
                            <span className="px-2 py-0.5 rounded-full bg-red-100 text-red-900 border border-red-300 text-[10px] font-bold tracking-wide">
                              {t.priorities.URGENT}
                            </span>
                          ) : (
                            <span className="px-2 py-0.5 rounded-full bg-stone-100 text-[#5F6368] border border-stone-200 text-[10px] font-semibold">
                              {t.priorities.ROUTINE}
                            </span>
                          )}

                          {/* Status Badge */}
                          <span
                            className={`px-2 py-0.5 rounded-full text-[10px] font-bold border ${
                              isPending
                                ? "bg-amber-50 text-amber-800 border-amber-200"
                                : isAcknowledged
                                  ? "bg-blue-50 text-blue-800 border-blue-200"
                                  : isCompleted
                                    ? "bg-emerald-50 text-emerald-800 border-emerald-200"
                                    : "bg-stone-100 text-[#80868B] border-stone-200"
                            }`}
                          >
                            {req.status}
                          </span>
                        </div>

                        {/* Attributes / Details */}
                        {Object.keys(req.attributes).length > 0 && (
                          <div className="flex items-center gap-2 mt-1 text-xs text-[#5F6368] flex-wrap">
                            {Object.entries(req.attributes).map(([k, v]) => (
                              <span
                                key={k}
                                className="px-1.5 py-0.5 rounded-md bg-[#FAF8F3] border border-[#202124]/10 text-[11px]"
                              >
                                {k}:{" "}
                                <strong className="text-[#202124]">{v}</strong>
                              </span>
                            ))}
                          </div>
                        )}

                        {req.notes && (
                          <p className="text-xs text-[#5F6368] mt-1 italic">
                            “{req.notes}”
                          </p>
                        )}

                        {/* ID and Created Time */}
                        <div className="flex items-center gap-3 mt-1.5 text-[10px] text-[#80868B]">
                          <span className="font-mono">{req.id}</span>
                          <span>•</span>
                          <span className="flex items-center gap-1">
                            <Clock className="w-3 h-3" />
                            <span>{formatTime(req.created_at_ms)}</span>
                          </span>
                        </div>
                      </div>
                    </div>

                    {/* Right: Crew Action Controls (Section 9.9, 9.10) */}
                    <div className="flex items-center gap-2 shrink-0 flex-wrap pt-2 md:pt-0 border-t md:border-t-0 border-[#202124]/[0.06]">
                      {/* Fixed Reply Button */}
                      {!isCompleted && !isCancelled && (
                        <button
                          type="button"
                          onClick={() => {
                            playSoftTap()
                            setReplyTargetRequest(req)
                          }}
                          className="px-3 min-h-11 rounded-xl border border-[#202124]/15 bg-white hover:bg-stone-50 text-xs font-semibold text-[#202124] transition-colors flex items-center gap-1.5 cursor-pointer"
                        >
                          <Send className="w-3.5 h-3.5 text-[#5F6368]" />
                          <span>{t.crew.actionSendReply}</span>
                        </button>
                      )}

                      {/* Acknowledge Button */}
                      {isPending && (
                        <button
                          type="button"
                          onClick={() => {
                            playSoftTap()
                            onAcknowledgeRequest(req.id)
                          }}
                          className="px-4 min-h-11 rounded-xl bg-[#202124] hover:bg-black text-white text-xs font-semibold transition-colors flex items-center gap-1.5 active:scale-95 cursor-pointer"
                        >
                          <CheckCircle2 className="w-3.5 h-3.5" />
                          <span>{t.crew.actionAcknowledge}</span>
                        </button>
                      )}

                      {/* Complete Button (Only valid once ACKNOWLEDGED per Section 7.5) */}
                      {isAcknowledged && (
                        <button
                          type="button"
                          onClick={() => {
                            playCabinChime()
                            onCompleteRequest(req.id)
                          }}
                          className="px-4 min-h-11 rounded-xl bg-emerald-700 hover:bg-emerald-800 text-white text-xs font-semibold transition-colors flex items-center gap-1.5 active:scale-95 cursor-pointer"
                        >
                          <CheckCircle2 className="w-3.5 h-3.5" />
                          <span>{t.crew.actionComplete}</span>
                        </button>
                      )}

                      {isCompleted && (
                        <span className="inline-flex items-center gap-1 px-3 py-1.5 rounded-lg bg-emerald-50 text-emerald-800 text-xs font-semibold">
                          <CheckCircle2 className="w-3.5 h-3.5" />
                          <span>{t.crew.actionCompleted}</span>
                        </span>
                      )}

                      {isCancelled && (
                        <span className="inline-flex items-center gap-1 px-3 py-1.5 rounded-lg bg-stone-100 text-[#80868B] text-xs font-medium">
                          <XCircle className="w-3.5 h-3.5" />
                          <span>Cancelled</span>
                        </span>
                      )}
                    </div>
                  </div>

                  {/* Reply Display Row if Reply Exists */}
                  {req.crew_reply_text_en && (
                    <div className="px-4 py-2.5 bg-[#FAF8F3] border-t border-[#202124]/[0.06] text-xs flex items-center gap-2">
                      <span className="font-semibold text-[#80868B] uppercase tracking-wider text-[10px]">
                        Latest Reply:
                      </span>
                      <span className="text-[#202124] italic">
                        “
                        {currentLanguage === "ja"
                          ? req.crew_reply_text_ja || req.crew_reply_text_en
                          : req.crew_reply_text_en}
                        ”
                      </span>
                    </div>
                  )}
                </div>
              )
            })}
          </div>
        )}
      </section>

      {/* Crew Reply Modal */}
      {replyTargetRequest && (
        <CrewReplyModal
          isOpen={Boolean(replyTargetRequest)}
          onClose={() => setReplyTargetRequest(null)}
          requestId={replyTargetRequest.id}
          seatLabel={replyTargetRequest.seat_label}
          currentLanguage={currentLanguage}
          onSendReply={(reply) => {
            onSendReplyToRequest(replyTargetRequest.id, reply)
          }}
        />
      )}
    </div>
  )
}
