import React, { useState } from "react"
import { RequestCategory, Language } from "../types"
import { translations } from "../utils/translations"
import { CANONICAL_VISUAL_CATEGORIES } from "../data/canonicalData"
import { CategoryIcon } from "./RequestIcons"
import { X, Send, Edit3 } from "lucide-react"
import { playSoftTap, playCabinChime } from "../utils/audio"

interface TypedRequestModalProps {
  isOpen: boolean
  onClose: () => void
  currentLanguage: Language
  onSubmit: (data: {
    category: RequestCategory
    subDetails: string
    notes: string
    attributes: Record<string, string>
  }) => void
}

export const TypedRequestModal: React.FC<TypedRequestModalProps> = ({
  isOpen,
  onClose,
  currentLanguage,
  onSubmit,
}) => {
  const [selectedCategory, setSelectedCategory] =
    useState<RequestCategory>("water_request")
  const [typedNotes, setTypedNotes] = useState("")

  if (!isOpen) return null

  const t = translations[currentLanguage]

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    playCabinChime()
    const info = t.categories[selectedCategory]

    onSubmit({
      category: selectedCategory,
      subDetails: info.label,
      notes: typedNotes.trim(),
      attributes: {},
    })
    setTypedNotes("")
    onClose()
  }

  const categorySelectHeading =
    currentLanguage === "ja"
      ? "カテゴリー選択"
      : currentLanguage === "zh"
        ? "選擇服務項目"
        : currentLanguage === "hi"
          ? "सेवा श्रेणी चुनें"
          : currentLanguage === "ta"
            ? "சேவைப் பிரிவைத் தேர்ந்தெடுக்கவும்"
            : currentLanguage === "mr"
              ? "सेवा प्रकार निवडा"
              : "Select Service Category"

  const detailsLabel =
    currentLanguage === "ja"
      ? "ご要望内容を入力"
      : currentLanguage === "zh"
        ? "輸入需求細節"
        : currentLanguage === "hi"
          ? "अनुरोध विवरण / संदेश"
          : currentLanguage === "ta"
            ? "கோரிக்கை விவரங்கள் / செய்தி"
            : currentLanguage === "mr"
              ? "विनंती तपशील / संदेश"
              : "Request Details / Message"

  const detailsPlaceholder =
    currentLanguage === "ja"
      ? "乗務員への具体的なご要望をお書きください..."
      : currentLanguage === "zh"
        ? "請輸入您希望空服員協助的具體細節..."
        : currentLanguage === "hi"
          ? "कृपया क्रू के लिए अपना विशिष्ट अनुरोध लिखें..."
          : currentLanguage === "ta"
            ? "தயவுசெய்து குழுவினருக்கான விவரங்களை இங்கே எழுதவும்..."
            : currentLanguage === "mr"
              ? "कृपया कर्मचाऱ्यांसाठी आपली विशिष्ट विनंती लिहा..."
              : "Please describe your specific request for the crew..."

  return (
    <div className="fixed inset-0 z-50 flex items-end sm:items-center justify-center p-0 sm:p-4 bg-[#202124]/60 backdrop-blur-xs transition-opacity animate-in fade-in duration-200">
      <div className="absolute inset-0" onClick={onClose} />

      <div className="relative w-full sm:max-w-md bg-white rounded-t-3xl sm:rounded-2xl shadow-2xl border border-[#202124]/10 overflow-hidden z-10 animate-in slide-in-from-bottom-6 sm:zoom-in-95 duration-200 max-h-[92dvh] flex flex-col">
        <div className="px-5 py-4 border-b border-[#202124]/[0.08] flex items-center justify-between bg-[#FAF8F3]">
          <div className="flex items-center gap-2.5">
            <div className="w-8 h-8 rounded-full bg-[#202124] text-white flex items-center justify-center shadow-xs">
              <Edit3 className="w-4 h-4" />
            </div>
            <div>
              <h3 className="font-bold text-[#202124] text-base leading-tight">
                {t.typedButton}
              </h3>
              <p className="text-[11px] text-[#5F6368] font-['Noto_Serif_JP',serif]">
                {t.typedSubtext}
              </p>
            </div>
          </div>
          <button
            onClick={() => {
              playSoftTap()
              onClose()
            }}
            className="w-11 h-11 -mr-2 inline-flex items-center justify-center rounded-full text-[#5F6368] hover:text-[#202124] hover:bg-[#EDE8DE]/60 transition-colors cursor-pointer"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        <form onSubmit={handleSubmit} className="p-5 overflow-y-auto space-y-4">
          <div>
            <label className="block text-xs font-semibold text-[#5F6368] uppercase tracking-wider mb-2">
              {categorySelectHeading}
            </label>
            <div className="grid grid-cols-2 gap-2">
              {CANONICAL_VISUAL_CATEGORIES.map((cat) => {
                const isSelected = selectedCategory === cat
                const info = t.categories[cat]

                return (
                  <button
                    key={cat}
                    type="button"
                    onClick={() => {
                      playSoftTap()
                      setSelectedCategory(cat)
                    }}
                    className={`flex items-center gap-2 p-3 min-h-12 rounded-xl border text-left transition-all cursor-pointer ${
                      isSelected
                        ? "border-[#C8102E] bg-[#FBECEE]/50 shadow-xs"
                        : "border-[#202124]/10 hover:border-[#202124]/20 hover:bg-[#FAF8F3]"
                    }`}
                  >
                    <div
                      className={`w-7 h-7 rounded-lg flex items-center justify-center shrink-0 ${
                        isSelected
                          ? "text-[#C8102E] bg-white"
                          : "text-[#202124] bg-stone-100"
                      }`}
                    >
                      <CategoryIcon category={cat} size={16} />
                    </div>
                    <div className="overflow-hidden">
                      <p
                        className={`text-xs font-bold truncate ${
                          isSelected ? "text-[#C8102E]" : "text-[#202124]"
                        }`}
                      >
                        {info.label}
                      </p>
                      <span className="text-[10px] text-[#5F6368] truncate block">
                        {info.shortBadge}
                      </span>
                    </div>
                  </button>
                )
              })}
            </div>
          </div>

          <div>
            <label className="block text-xs font-semibold text-[#5F6368] uppercase tracking-wider mb-1.5">
              {detailsLabel}
            </label>
            <textarea
              value={typedNotes}
              onChange={(e) => setTypedNotes(e.target.value)}
              placeholder={detailsPlaceholder}
              rows={3}
              maxLength={120}
              className="w-full p-3 rounded-xl border border-[#202124]/15 bg-white text-xs text-[#202124] focus:outline-hidden focus:ring-2 focus:ring-[#C8102E]/40 resize-none leading-relaxed"
            />
          </div>

          <div className="pt-2 flex items-center gap-3">
            <button
              type="button"
              onClick={() => {
                playSoftTap()
                onClose()
              }}
              className="w-1/3 min-h-12 px-4 rounded-xl border border-[#202124]/15 font-semibold text-xs text-[#202124] hover:bg-stone-50 transition-colors cursor-pointer"
            >
              {t.actions.cancel}
            </button>
            <button
              type="submit"
              className="w-2/3 min-h-12 px-4 rounded-xl bg-[#202124] hover:bg-black text-white font-semibold text-xs tracking-wide shadow-md transition-all active:scale-[0.98] flex items-center justify-center gap-2 cursor-pointer"
            >
              <Send className="w-3.5 h-3.5" />
              <span>{t.actions.sendRequest}</span>
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}
