import React, { useState } from "react"
import { PassengerRequest, Language, RequestStatus } from "../types"
import { translations } from "../utils/translations"
import { CategoryIcon } from "./RequestIcons"
import {
  Clock,
  ChevronDown,
  ChevronUp,
  XCircle,
  Volume2,
  UserCheck,
  Check,
} from "lucide-react"
import { playSoftTap } from "../utils/audio"

interface ActiveRequestsProps {
  requests: PassengerRequest[]
  currentLanguage: Language
  onCancelRequest: (id: string) => void
}

export const ActiveRequests: React.FC<ActiveRequestsProps> = ({
  requests,
  currentLanguage,
  onCancelRequest,
}) => {
  const t = translations[currentLanguage]
  const [expandedId, setExpandedId] = useState<string | null>(null)
  const [isSpeakingId, setIsSpeakingId] = useState<string | null>(null)

  const displayRequests = requests

  const formatTime = (ts: number) => {
    const date = new Date(ts)
    return date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })
  }

  // Canonical status config strictly conforming to Section 7.4
  const getStatusBadge = (status: RequestStatus) => {
    switch (status) {
      case "PENDING":
        return {
          label: t.statuses.PENDING.title,
          badgeClass: "bg-amber-50 text-amber-900 border-amber-200",
          dotClass: "bg-amber-500 animate-pulse",
          icon: <Clock className="w-3.5 h-3.5 text-amber-700" />,
        }
      case "ACKNOWLEDGED":
        return {
          label: t.statuses.ACKNOWLEDGED.title,
          badgeClass: "bg-blue-50 text-blue-900 border-blue-200",
          dotClass: "bg-blue-600",
          icon: <UserCheck className="w-3.5 h-3.5 text-blue-700" />,
        }
      case "COMPLETED":
        return {
          label: t.statuses.COMPLETED.title,
          badgeClass: "bg-emerald-50 text-emerald-900 border-emerald-200",
          dotClass: "bg-emerald-600",
          icon: <Check className="w-3.5 h-3.5 text-emerald-700" />,
        }
      case "CANCELLED":
        return {
          label: t.statuses.CANCELLED.title,
          badgeClass: "bg-stone-100 text-[#80868B] border-stone-200",
          dotClass: "bg-stone-400",
          icon: <XCircle className="w-3.5 h-3.5 text-[#80868B]" />,
        }
    }
  }

  // Read-aloud feature (Section 13.4): direct tap handler invokes speechSynthesis
  const handleSpeakReply = (req: PassengerRequest) => {
    if (typeof window === "undefined" || !("speechSynthesis" in window)) return

    const replyText =
      currentLanguage === "ja"
        ? req.crew_reply_text_ja || req.crew_reply_text_en
        : req.crew_reply_text_en

    if (!replyText) return

    window.speechSynthesis.cancel()
    const utterance = new SpeechSynthesisUtterance(replyText)
    utterance.lang =
      currentLanguage === "ja"
        ? "ja-JP"
        : currentLanguage === "zh"
          ? "zh-TW"
          : currentLanguage === "hi"
            ? "hi-IN"
            : currentLanguage === "ta"
              ? "ta-IN"
              : currentLanguage === "mr"
                ? "mr-IN"
                : "en-US"
    utterance.rate = 0.95

    utterance.onstart = () => setIsSpeakingId(req.id)
    utterance.onend = () => setIsSpeakingId(null)
    utterance.onerror = () => setIsSpeakingId(null)

    window.speechSynthesis.speak(utterance)
  }

  const crewReplyHeading =
    currentLanguage === "ja"
      ? "客室乗務員からの応答"
      : currentLanguage === "zh"
        ? "空服員回覆"
        : currentLanguage === "hi"
          ? "केबिन क्रू उत्तर"
          : currentLanguage === "ta"
            ? "பணிப்பாளர் பதில்"
            : currentLanguage === "mr"
              ? "केबिन क्रू उत्तर"
              : "Cabin Attendant Reply"

  const noteHeading =
    currentLanguage === "ja"
      ? "メモ / 認識内容"
      : currentLanguage === "zh"
        ? "備註 / 內容"
        : currentLanguage === "hi"
          ? "टिप्पणी / विवरण"
          : currentLanguage === "ta"
            ? "குறிப்பு / விவரம்"
            : currentLanguage === "mr"
              ? "नोंद / तपशील"
              : "Note / Details"

  const noCancellationNotice =
    currentLanguage === "ja"
      ? "担当乗務員が対応中のため、取り消しはできません。"
      : currentLanguage === "zh"
        ? "空服員已受理，無法取消。"
        : currentLanguage === "hi"
          ? "क्रू सदस्य द्वारा स्वीकृत — अब रद्द नहीं किया जा सकता।"
          : currentLanguage === "ta"
            ? "பணிப்பாளர் ஏற்றுக்கொண்டார் — இனி ரத்து செய்ய முடியாது."
            : currentLanguage === "mr"
              ? "कर्मचाऱ्यांनी स्वीकारले — आता रद्द करता येणार नाही."
              : "Assigned to cabin attendant — cancellation no longer eligible."

  return (
    <div className="w-full">
      <div className="flex items-center justify-between mb-3 px-1">
        <div className="flex items-center gap-2">
          <h2 className="font-['Noto_Serif_JP',serif] font-bold text-base sm:text-lg text-[#202124]">
            {t.activeRequestsHeading}
          </h2>
          {displayRequests.length > 0 && (
            <span className="inline-flex items-center justify-center px-2 py-0.5 rounded-full bg-white border border-[#202124]/10 text-xs font-semibold text-[#202124] shadow-2xs">
              {displayRequests.length}
            </span>
          )}
        </div>
      </div>

      {displayRequests.length === 0 ? (
        <div className="p-8 rounded-3xl bg-white border border-[#202124]/[0.06] text-center shadow-xs">
          <div className="w-12 h-12 rounded-full bg-[#FAF8F3] border border-[#202124]/[0.08] flex items-center justify-center mx-auto mb-2 text-[#5F6368]">
            <Clock className="w-6 h-6 text-[#5F6368]" />
          </div>
          <p className="text-sm font-bold text-[#202124]">
            {t.noActiveRequests}
          </p>
          <p className="text-xs text-[#5F6368] mt-1 max-w-sm mx-auto leading-relaxed">
            {t.noActiveRequestsSub}
          </p>
        </div>
      ) : (
        <div className="space-y-3">
          {displayRequests.map((req) => {
            const isExpanded = expandedId === req.id
            const statusConfig = getStatusBadge(req.status)
            const statusText = t.statuses[req.status]
            const isUrgent = req.priority === "URGENT"
            const canCancel = req.status === "PENDING"

            // Dynamic localized category title
            const localizedTitle =
              req.category && t.categories[req.category]
                ? `${t.categories[req.category].label} (${t.categories[req.category].subLabel})`
                : req.title

            return (
              <div
                key={req.id}
                className="rounded-2xl bg-white border border-[#202124]/[0.08] shadow-xs overflow-hidden transition-all duration-200 hover:border-[#202124]/20"
              >
                {/* Header tap target */}
                <div
                  role="button"
                  tabIndex={0}
                  onClick={() => {
                    playSoftTap()
                    setExpandedId(isExpanded ? null : req.id)
                  }}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" || e.key === " ") {
                      e.preventDefault()
                      playSoftTap()
                      setExpandedId(isExpanded ? null : req.id)
                    }
                  }}
                  className="p-3.5 sm:p-4 flex flex-col min-[480px]:flex-row min-[480px]:items-center justify-between gap-3 cursor-pointer select-none"
                >
                  <div className="flex items-start gap-3 min-w-0">
                    <div className="w-10 h-10 rounded-xl bg-[#FAF8F3] border border-[#202124]/[0.06] flex items-center justify-center text-[#202124] shrink-0 mt-0.5 sm:mt-0">
                      <CategoryIcon
                        category={
                          req.category ||
                          req.intent_id as any ||
                          "water_request"
                        }
                        size={20}
                      />
                    </div>

                    <div className="min-w-0">
                      <div className="flex items-center gap-1.5 flex-wrap">
                        <span className="font-bold text-sm text-[#202124] break-words">
                          {localizedTitle}
                        </span>

                        {isUrgent && (
                          <span className="px-1.5 py-0.2 rounded-full bg-red-100 text-red-900 border border-red-200 text-[9px] font-bold">
                            {t.priorities.URGENT}
                          </span>
                        )}
                      </div>

                      {/* Attributes */}
                      {Object.keys(req.attributes).length > 0 && (
                        <p className="text-xs text-[#5F6368] mt-0.5 break-words">
                          {Object.entries(req.attributes)
                            .map(([k, v]) => `${k}: ${v}`)
                            .join(", ")}
                        </p>
                      )}

                      <div className="flex items-center gap-2 mt-1 text-[10px] text-[#80868B]">
                        <span className="font-mono">{req.id}</span>
                        <span>•</span>
                        <span className="flex items-center gap-1">
                          <Clock className="w-3 h-3" />
                          <span>{formatTime(req.created_at_ms)}</span>
                        </span>
                      </div>
                    </div>
                  </div>

                  <div className="flex items-center justify-between min-[480px]:justify-end gap-2 shrink-0">
                    <span
                      className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full border text-[11px] font-bold ${statusConfig.badgeClass}`}
                    >
                      <span
                        className={`w-1.5 h-1.5 rounded-full ${statusConfig.dotClass}`}
                      />
                      <span>{statusConfig.label}</span>
                    </span>

                    <button
                      type="button"
                      className="w-11 h-11 inline-flex items-center justify-center rounded-lg text-[#5F6368] hover:text-[#202124] hover:bg-[#FAF8F3] cursor-pointer"
                      aria-label={isExpanded ? "Collapse" : "Expand"}
                    >
                      {isExpanded ? (
                        <ChevronUp className="w-4 h-4" />
                      ) : (
                        <ChevronDown className="w-4 h-4" />
                      )}
                    </button>
                  </div>
                </div>

                {/* Expanded Details (Screen D Details) */}
                {isExpanded && (
                  <div className="px-4 pb-4 pt-1 border-t border-[#202124]/[0.06] bg-[#FAF8F3]/60 text-xs animate-in slide-in-from-top-2 duration-150 space-y-3">
                    {/* Status Explanation Card */}
                    <div className="p-3 rounded-xl bg-white border border-[#202124]/[0.06] shadow-2xs">
                      <div className="flex items-center gap-1.5 font-bold text-[#202124] text-xs">
                        {statusConfig.icon}
                        <span>{statusText.title}</span>
                      </div>
                      <p className="text-[11px] text-[#5F6368] mt-1 leading-relaxed">
                        {statusText.desc}
                      </p>
                    </div>

                    {/* Passenger Note if present */}
                    {req.notes && (
                      <div className="p-3 rounded-xl bg-white border border-[#202124]/[0.06]">
                        <span className="text-[10px] font-semibold text-[#80868B] uppercase tracking-wider block mb-0.5">
                          {noteHeading}
                        </span>
                        <p className="text-xs text-[#202124] italic">
                          “{req.notes}”
                        </p>
                      </div>
                    )}

                    {/* Crew Reply Section (Master Implementation Plan Section 13.4) */}
                    {req.crew_reply_text_en && (
                      <div className="p-3.5 rounded-xl bg-white border border-[#202124]/10 shadow-2xs space-y-2">
                        <div className="flex items-center justify-between">
                          <span className="text-[10px] font-bold uppercase tracking-wider text-[#C8102E] flex items-center gap-1">
                            <UserCheck className="w-3.5 h-3.5" />
                            <span>{crewReplyHeading}</span>
                          </span>

                          {/* Read-Aloud Button */}
                          <button
                            type="button"
                            onClick={() => handleSpeakReply(req)}
                            className={`inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-[11px] font-semibold transition-colors cursor-pointer ${
                              isSpeakingId === req.id
                                ? "bg-[#C8102E] text-white animate-pulse"
                                : "bg-[#FAF8F3] hover:bg-stone-200 text-[#202124] border border-[#202124]/10"
                            }`}
                            aria-label={t.actions.hearReply}
                          >
                            <Volume2 className="w-3.5 h-3.5" />
                            <span>{t.actions.hearReply}</span>
                          </button>
                        </div>

                        <p className="text-xs text-[#202124] font-medium italic leading-relaxed">
                          “
                          {currentLanguage === "ja"
                            ? req.crew_reply_text_ja || req.crew_reply_text_en
                            : req.crew_reply_text_en}
                          ”
                        </p>
                      </div>
                    )}

                    {/* Cancellation Controls per Section 7.5 */}
                    <div className="flex items-center justify-between pt-1 gap-2 flex-wrap">
                      {canCancel ? (
                        <button
                          type="button"
                          onClick={() => {
                            playSoftTap()
                            onCancelRequest(req.id)
                          }}
                          className="px-3 min-h-11 rounded-lg border border-[#202124]/15 hover:border-red-300 hover:bg-red-50 text-red-700 font-semibold text-xs transition-colors flex items-center gap-1.5 active:scale-95 cursor-pointer"
                        >
                          <XCircle className="w-3.5 h-3.5" />
                          <span>{t.actions.cancel}</span>
                        </button>
                      ) : req.status === "ACKNOWLEDGED" ? (
                        <span className="text-[11px] text-[#80868B] italic">
                          {noCancellationNotice}
                        </span>
                      ) : null}
                    </div>
                  </div>
                )}
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}
