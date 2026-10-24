import React, { useState } from "react"
import { RequestCategory, Language } from "../types"
import { translations } from "../utils/translations"
import { INTENT_CATALOG } from "../data/canonicalData"
import { CategoryIcon } from "./RequestIcons"
import { X, Send, AlertTriangle } from "lucide-react"
import { playSoftTap, playCabinChime } from "../utils/audio"

interface RequestModalProps {
  isOpen: boolean
  onClose: () => void
  category: RequestCategory | null
  currentLanguage: Language
  onSubmit: (data: {
    category: RequestCategory
    subDetails: string
    notes: string
    attributes: Record<string, string>
  }) => void
}

export const RequestModal: React.FC<RequestModalProps> = ({
  isOpen,
  onClose,
  category,
  currentLanguage,
  onSubmit,
}) => {
  const [selectedOptionIndex, setSelectedOptionIndex] = useState(0)
  const [notes, setNotes] = useState("")

  if (!isOpen || !category) return null

  const t = translations[currentLanguage]
  const categoryInfo = t.categories[category]
  const intentMeta = INTENT_CATALOG[category]
  const isUrgent = intentMeta?.priority === "URGENT"

  const getTemperatureOptions = () => {
    switch (currentLanguage) {
      case "ja":
        return ["冷水 (Cold)", "常温 (Room temperature)", "白湯 (Warm)"]
      case "zh":
        return ["冰涼 (Cold)", "常溫 (Room temperature)", "溫熱 (Warm)"]
      case "hi":
        return [
          "ठंडा पानी (Cold)",
          "सामान्य तापमान (Room temperature)",
          "गुनगुना पानी (Warm)",
        ]
      case "ta":
        return [
          "குளிர்ந்த நீர் (Cold)",
          "சாதாரண வெப்பநிலை (Room temperature)",
          "வெதுவெதுப்பான நீர் (Warm)",
        ]
      case "mr":
        return [
          "थंड पाणी (Cold)",
          "सामान्य तापमान (Room temperature)",
          "कोमट पाणी (Warm)",
        ]
      default:
        return ["Cold", "Room temperature", "Warm"]
    }
  }

  const options =
    category === "water_request"
      ? getTemperatureOptions().map((label) => ({ label }))
      : []

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    playCabinChime()

    const details = options[selectedOptionIndex]?.label ?? ""
    const attributes: Record<string, string> = {}
    if (category === "water_request") {
      attributes["temperature"] =
        selectedOptionIndex === 0
          ? "COLD"
          : selectedOptionIndex === 1
            ? "ROOM_TEMP"
            : "WARM"
    }

    onSubmit({
      category,
      subDetails: details,
      notes: notes.trim(),
      attributes,
    })
    setNotes("")
    onClose()
  }

  const selectTempHeading =
    currentLanguage === "ja"
      ? "温度をお選びください"
      : currentLanguage === "zh"
        ? "請選擇水溫"
        : currentLanguage === "hi"
          ? "पानी का तापमान चुनें"
          : currentLanguage === "ta"
            ? "நீரின் வெப்பநிலையைத் தேர்ந்தெடுக்கவும்"
            : currentLanguage === "mr"
              ? "पाण्याचे तापमान निवडा"
              : "Select Temperature"

  const urgentNoticeText =
    currentLanguage === "ja"
      ? "お手伝いのご要望は緊急・優先キューへ登録され、担当乗務員が迅速に対応いたします。"
      : currentLanguage === "zh"
        ? "無障礙與行動協助將優先排入緊急佇列，空服員將迅速前來協助。"
        : currentLanguage === "hi"
          ? "सुलभता सहायता अनुरोध शीर्ष प्राथमिकता सूची में दर्ज किए जाते हैं और क्रू सदस्य तुरंत सहायता करेंगे।"
          : currentLanguage === "ta"
            ? "இயக்க உதவி கோரிக்கைகள் முன்னுரிமைப் பட்டியலில் பதிவு செய்யப்பட்டு, பணிப்பாளர் விரைந்து உதவுவார்."
            : currentLanguage === "mr"
              ? "सुलभता साहाय्य विनंत्या सर्वोच्च प्राधान्य रांगेत नोंदवल्या जातात आणि कर्मचारी त्वरित मदत करतील."
              : "Urgent assistance requests receive top priority in the cabin crew queue."

  const notesLabel =
    currentLanguage === "ja"
      ? "特記事項（任意）"
      : currentLanguage === "zh"
        ? "備註（選填）"
        : currentLanguage === "hi"
          ? "क्रू के लिए विशेष निर्देश (वैकल्पिक)"
          : currentLanguage === "ta"
            ? "குழுவினருக்கான குறிப்பு (விருப்பமானது)"
            : currentLanguage === "mr"
              ? "कर्मचाऱ्यांसाठी विशेष सूचना (पर्यायी)"
              : "Note for Crew (Optional)"

  const notesPlaceholder =
    currentLanguage === "ja"
      ? "例: 2杯、または追加のご要望など"
      : currentLanguage === "zh"
        ? "例如: 需要兩杯，或其他特殊需求"
        : currentLanguage === "hi"
          ? "उदा. 2 कप, या कोई अतिरिक्त प्राथमिकता"
          : currentLanguage === "ta"
            ? "எ.கா. 2 டம்ளர்கள், அல்லது கூடுதல் விருப்பங்கள்"
            : currentLanguage === "mr"
              ? "उदा. 2 कप, किंवा इतर काही आवश्यकता"
              : "e.g. 2 cups, or additional preferences"

  return (
    <div className="fixed inset-0 z-50 flex items-end sm:items-center justify-center p-0 sm:p-4 bg-[#202124]/60 backdrop-blur-xs transition-opacity animate-in fade-in duration-200">
      <div className="absolute inset-0" onClick={onClose} />

      <div className="relative w-full sm:max-w-md bg-white rounded-t-3xl sm:rounded-2xl shadow-2xl border border-[#202124]/10 overflow-hidden z-10 animate-in slide-in-from-bottom-6 sm:zoom-in-95 duration-200 max-h-[90dvh] flex flex-col">
        {/* Modal Header */}
        <div className="px-5 py-4 border-b border-[#202124]/[0.08] flex items-center justify-between bg-[#FAF8F3]">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-white border border-[#202124]/10 flex items-center justify-center text-[#C8102E] shadow-2xs shrink-0">
              <CategoryIcon category={category} size={22} />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h3 className="font-bold text-[#202124] text-base sm:text-lg leading-tight">
                  {categoryInfo.label}
                </h3>
                {isUrgent && (
                  <span className="px-2 py-0.5 rounded-full bg-red-100 text-red-900 border border-red-300 text-[10px] font-bold">
                    {t.priorities.URGENT}
                  </span>
                )}
              </div>
              {categoryInfo.subLabel && currentLanguage !== "ja" && (
                <span className="text-xs font-['Noto_Serif_JP',serif] text-[#5F6368]">
                  {categoryInfo.subLabel}
                </span>
              )}
            </div>
          </div>

          <button
            onClick={() => {
              playSoftTap()
              onClose()
            }}
            className="w-11 h-11 -mr-2 inline-flex items-center justify-center rounded-full text-[#5F6368] hover:text-[#202124] hover:bg-[#EDE8DE]/60 transition-colors cursor-pointer"
            aria-label="Close"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        <form onSubmit={handleSubmit} className="p-5 overflow-y-auto space-y-4">
          {/* Options for water */}
          {options.length > 0 && (
            <div>
              <label className="block text-xs font-semibold text-[#5F6368] uppercase tracking-wider mb-2">
                {selectTempHeading}
              </label>
              <div className="space-y-2">
                {options.map((opt, idx) => (
                  <div
                    key={idx}
                    onClick={() => {
                      playSoftTap()
                      setSelectedOptionIndex(idx)
                    }}
                    className={`flex items-center justify-between p-3.5 rounded-xl border text-left cursor-pointer transition-all ${
                      selectedOptionIndex === idx
                        ? "border-[#C8102E] bg-[#FBECEE]/40 shadow-xs"
                        : "border-[#202124]/10 hover:border-[#202124]/20 hover:bg-[#FAF8F3]/60"
                    }`}
                  >
                    <p
                      className={`text-sm font-semibold ${
                        selectedOptionIndex === idx
                          ? "text-[#C8102E]"
                          : "text-[#202124]"
                      }`}
                    >
                      {opt.label}
                    </p>
                    <div
                      className={`w-4 h-4 rounded-full border flex items-center justify-center transition-colors ${
                        selectedOptionIndex === idx
                          ? "border-[#C8102E] bg-[#C8102E]"
                          : "border-[#80868B]"
                      }`}
                    >
                      {selectedOptionIndex === idx && (
                        <div className="w-1.5 h-1.5 rounded-full bg-white" />
                      )}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Urgent accessibility notice if applicable */}
          {isUrgent && (
            <div className="p-3 rounded-xl bg-red-50 border border-red-200 text-red-900 text-xs flex items-start gap-2.5">
              <AlertTriangle className="w-4 h-4 text-[#C8102E] shrink-0 mt-0.5" />
              <p className="leading-relaxed">{urgentNoticeText}</p>
            </div>
          )}

          {/* Optional notes */}
          <div>
            <label className="block text-xs font-semibold text-[#5F6368] uppercase tracking-wider mb-1.5">
              {notesLabel}
            </label>
            <input
              type="text"
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              placeholder={notesPlaceholder}
              maxLength={80}
              className="w-full px-3.5 min-h-11 rounded-xl border border-[#202124]/15 bg-white text-xs text-[#202124] focus:outline-hidden focus:ring-2 focus:ring-[#C8102E]/40"
            />
          </div>

          {/* Action buttons */}
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
              className="w-2/3 min-h-12 px-4 rounded-xl bg-[#C8102E] hover:bg-[#B00E28] active:bg-[#8F0A20] text-white font-semibold text-xs tracking-wide shadow-md transition-all active:scale-[0.98] flex items-center justify-center gap-2 cursor-pointer"
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
