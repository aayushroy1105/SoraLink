import React, { useState } from "react"
import { Language, CrewResponse } from "../types"
import { translations } from "../utils/translations"
import { APPROVED_CREW_RESPONSES } from "../data/canonicalData"
import { MessageSquare, X, Send, Check } from "lucide-react"
import { playSoftTap, playCabinChime } from "../utils/audio"

interface CrewReplyModalProps {
  isOpen: boolean
  onClose: () => void
  requestId: string
  seatLabel: string
  currentLanguage: Language
  onSendReply: (reply: CrewResponse) => void
}

export const CrewReplyModal: React.FC<CrewReplyModalProps> = ({
  isOpen,
  onClose,
  requestId,
  seatLabel,
  currentLanguage,
  onSendReply,
}) => {
  const [selectedReplyId, setSelectedReplyId] = useState<string>(
    APPROVED_CREW_RESPONSES[0].reply_id,
  )

  if (!isOpen) return null

  const t = translations[currentLanguage]
  const selectedReply = APPROVED_CREW_RESPONSES.find(
    (r) => r.reply_id === selectedReplyId,
  )

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    if (!selectedReply) return
    playCabinChime()
    onSendReply(selectedReply)
    onClose()
  }

  return (
    <div className="fixed inset-0 z-50 flex items-end sm:items-center justify-center p-0 sm:p-4 bg-[#202124]/60 backdrop-blur-xs animate-in fade-in duration-200">
      <div className="absolute inset-0" onClick={onClose} />

      <div className="relative w-full sm:max-w-lg bg-white rounded-t-3xl sm:rounded-2xl shadow-2xl border border-[#202124]/10 overflow-hidden z-10 animate-in slide-in-from-bottom-6 sm:zoom-in-95 duration-200 max-h-[92dvh] flex flex-col">
        <div className="px-5 py-4 border-b border-[#202124]/[0.08] flex items-center justify-between bg-[#FAF8F3]">
          <div className="flex items-center gap-2.5 min-w-0">
            <div className="w-8 h-8 rounded-full bg-[#202124] text-white flex items-center justify-center shrink-0">
              <MessageSquare className="w-4 h-4" />
            </div>
            <div>
              <h3 className="font-bold text-[#202124] text-base leading-tight">
                {t.replyModal.title}
              </h3>
              <p className="text-xs text-[#5F6368] font-medium">
                Seat {seatLabel} • {requestId}
              </p>
            </div>
          </div>
          <button
            onClick={() => {
              playSoftTap()
              onClose()
            }}
            className="w-11 h-11 -mr-2 inline-flex items-center justify-center rounded-full text-[#5F6368] hover:text-[#202124] hover:bg-[#EDE8DE]/60 transition-colors"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        <form onSubmit={handleSubmit} className="p-5 overflow-y-auto space-y-4">
          <div>
            <p className="text-xs text-[#5F6368] mb-3">
              {t.replyModal.selectReply}
            </p>

            <div className="space-y-2.5">
              {APPROVED_CREW_RESPONSES.map((resp) => {
                const isSelected = selectedReplyId === resp.reply_id
                const label =
                  currentLanguage === "ja"
                    ? resp.label_ja
                    : currentLanguage === "zh"
                      ? resp.label_zh
                      : resp.label_en
                const text =
                  currentLanguage === "ja"
                    ? resp.text_ja
                    : currentLanguage === "zh"
                      ? resp.text_zh
                      : resp.text_en

                return (
                  <button
                    key={resp.reply_id}
                    type="button"
                    onClick={() => {
                      playSoftTap()
                      setSelectedReplyId(resp.reply_id)
                    }}
                    className={`w-full p-3.5 rounded-xl border text-left transition-all flex items-start justify-between gap-3 ${
                      isSelected
                        ? "border-[#202124] bg-[#FAF8F3] ring-1 ring-[#202124]"
                        : "border-[#202124]/10 hover:border-[#202124]/20 bg-white"
                    }`}
                  >
                    <div className="min-w-0">
                      <div className="flex items-center gap-2">
                        <span
                          className={`text-xs font-bold ${
                            isSelected ? "text-[#202124]" : "text-[#5F6368]"
                          }`}
                        >
                          {label}
                        </span>
                      </div>
                      <p className="text-xs text-[#202124] mt-1 italic leading-relaxed">
                        “{text}”
                      </p>
                      <p className="text-[10px] text-[#80868B] mt-0.5">
                        {currentLanguage !== "en" && resp.text_en}
                      </p>
                    </div>

                    <div className="pt-0.5 shrink-0">
                      <div
                        className={`w-4 h-4 rounded-full border flex items-center justify-center transition-colors ${
                          isSelected
                            ? "border-[#202124] bg-[#202124]"
                            : "border-[#80868B]"
                        }`}
                      >
                        {isSelected && <Check className="w-3 h-3 text-white" />}
                      </div>
                    </div>
                  </button>
                )
              })}
            </div>
          </div>

          <div className="pt-2 flex items-center gap-3">
            <button
              type="button"
              onClick={() => {
                playSoftTap()
                onClose()
              }}
              className="w-1/3 min-h-11 rounded-xl border border-[#202124]/15 font-semibold text-xs text-[#202124] hover:bg-stone-50 transition-colors"
            >
              {t.replyModal.cancelButton}
            </button>
            <button
              type="submit"
              className="w-2/3 min-h-11 rounded-xl bg-[#202124] hover:bg-black text-white font-semibold text-xs tracking-wide shadow-md transition-all active:scale-[0.98] flex items-center justify-center gap-2"
            >
              <Send className="w-3.5 h-3.5" />
              <span>{t.replyModal.sendButton}</span>
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}
