import React, { useState, useEffect, useRef } from "react"
import { RequestCategory, Language, VoicePreviewOutcome } from "../types"
import { translations } from "../utils/translations"
import {
  CANONICAL_VISUAL_CATEGORIES,
  INTENT_CATALOG,
} from "../data/canonicalData"
import {
  Mic,
  X,
  Check,
  Sparkles,
  RefreshCw,
  AlertCircle,
  Edit3,
} from "lucide-react"
import { CategoryIcon } from "./RequestIcons"
import { playSoftTap, playCabinChime } from "../utils/audio"
import { apiFetch, saveRequestMeta } from "../utils/api"

interface VoiceModalProps {
  isOpen: boolean
  onClose: () => void
  currentLanguage: Language
  onSwitchToTyped?: () => void
  onSubmit: (data: {
    category: RequestCategory
    subDetails: string
    notes: string
    attributes: Record<string, string>
  }) => void
}

const KEYWORD_MAP: Record<RequestCategory, string[]> = {
  water_request: [
    "water",
    "drink",
    "お水",
    "水",
    "白湯",
    "冷水",
    "飲用水",
    "喝水",
    "水ください",
    "पानी",
    "जल",
    "वाटर",
    "पीने का पानी",
    "ठंडा पानी",
    "गुनगुना पानी",
    "தண்ணீர்",
    "நீர்",
    "குடிநீர்",
    "வெந்நீர்",
    "पाणी",
    "जल",
    "पिण्याचे पाणी",
    "कोमट पाणी",
  ],
  blanket_request: [
    "blanket",
    "毛布",
    "ブランケット",
    "寒い",
    "冷気",
    "毛毯",
    "冷",
    "毯子",
    "कंबल",
    "ब्लैंकेट",
    "ठंड",
    "कंबल चाहिए",
    "போர்வை",
    "பிளாங்கெட்",
    "குளிர்",
    "போர்வை வேண்டும்",
    "ब्लँकेट",
    "घोंगडी",
    "थंडी",
    "ब्लँकेट हवे",
  ],
  pillow_request: [
    "pillow",
    "枕",
    "まくら",
    "眠い",
    "横になりたい",
    "枕頭",
    "靠枕",
    "तकिया",
    "पिलो",
    "सिरहाने",
    "तकिया चाहिए",
    "தலையணை",
    "பில்லோ",
    "தலையணை வேண்டும்",
    "उशी",
    "पिलो",
    "उशी हवी",
  ],
  accessibility_assist: [
    "assist",
    "help",
    "wheelchair",
    "お手伝い",
    "サポート",
    "車いす",
    "移動",
    "立ち上がれない",
    "協助",
    "幫忙",
    "輪椅",
    "行動不便",
    "मदद",
    "सहायता",
    "सुलभता",
    "व्हीलचेयर",
    "चलने में परेशानी",
    "உதவி",
    "சக்கர நாற்காலி",
    "மாற்றுத்திறனாளி",
    "நகர உதவி",
    "मदत",
    "साहाय्य",
    "सुलभता",
    "व्हीलचेअर",
    "चालण्यास मदत",
  ],
}

export const VoiceModal: React.FC<VoiceModalProps> = ({
  isOpen,
  onClose,
  currentLanguage,
  onSwitchToTyped,
  onSubmit,
}) => {
  const [isListening, setIsListening] = useState(false)
  const [transcript, setTranscript] = useState("")
  const [suggestedCategory, setSuggestedCategory] =
    useState<RequestCategory | null>(null)
  const [confidenceScore, setConfidenceScore] = useState<number>(0)
  const [outcome, setOutcome] = useState<VoicePreviewOutcome>("SUGGESTED")
  const [alternativeIntents, setAlternativeIntents] =
    useState<RequestCategory[]>([])
  const [temperature, setTemperature] = useState<"COLD" | "ROOM_TEMP" | "WARM">(
    "COLD",
  )
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [errorText, setErrorText] = useState("")
  const [previewId, setPreviewId] = useState<string | null>(null)
  const recognitionRef = useRef<any>(null)
  const mediaRecorderRef = useRef<MediaRecorder | null>(null)
  const chunksRef = useRef<Blob[]>([])

  const SpeechRecognitionCtor =
    typeof window !== "undefined"
      ? (window as any).SpeechRecognition ||
        (window as any).webkitSpeechRecognition
      : undefined

  // Reset state when modal opens
  useEffect(() => {
    if (!isOpen) {
      setTranscript("")
      setSuggestedCategory(null)
      setConfidenceScore(0)
      setAlternativeIntents([])
      setIsListening(false)
      setIsSubmitting(false)
      setErrorText("")
      setPreviewId(null)
      return
    }

    setTranscript("")
    setSuggestedCategory(null)
    setConfidenceScore(0)
    setAlternativeIntents([])
    setErrorText("")
    setPreviewId(null)
  }, [isOpen])

  // Setup Web Speech recognition if supported
  useEffect(() => {
    if (!isOpen || !SpeechRecognitionCtor) return
    const recognition = new SpeechRecognitionCtor()
    recognition.continuous = false
    recognition.interimResults = true

    const langMap: Record<Language, string> = {
      ja: "ja-JP",
      zh: "zh-TW",
      hi: "hi-IN",
      ta: "ta-IN",
      mr: "mr-IN",
      en: "en-US",
    }
    recognition.lang = langMap[currentLanguage] || "en-US"

    recognition.onresult = (event: any) => {
      const text = event.results[event.resultIndex][0].transcript
      setTranscript(text)
      classifySpokenText(text)
    }
    recognition.onend = () => setIsListening(false)
    recognition.onerror = () => {
      setIsListening(false)
      setErrorText(translations[currentLanguage].voice.errorCapture)
    }
    recognitionRef.current = recognition

    return () => {
      recognition.abort()
      recognitionRef.current = null
    }
  }, [isOpen, currentLanguage, SpeechRecognitionCtor])

  useEffect(() => {
    if (typeof window !== "undefined") {
      if (isOpen) {
        ;(window as any).__soralinkUploadVoiceBlob = uploadAudioForPreview
      } else {
        delete (window as any).__soralinkUploadVoiceBlob
      }
    }
    return () => {
      if (typeof window !== "undefined") {
        delete (window as any).__soralinkUploadVoiceBlob
      }
    }
  })

  if (!isOpen) return null

  const t = translations[currentLanguage]

  const classifySpokenText = (text: string) => {
    const trimmed = text.trim()
    if (!trimmed) {
      setSuggestedCategory(null)
      setConfidenceScore(0)
      setAlternativeIntents([])
      return
    }

    const lower = trimmed.toLowerCase()
    let matched: RequestCategory = "water_request"
    let maxMatches = 0

    for (const cat of CANONICAL_VISUAL_CATEGORIES) {
      const count = KEYWORD_MAP[cat].filter((k) =>
        lower.includes(k.toLowerCase()),
      ).length
      if (count > maxMatches) {
        maxMatches = count
        matched = cat
      }
    }

    setSuggestedCategory(matched)

    if (
      lower.includes("warm") ||
      lower.includes("白湯") ||
      lower.includes("温") ||
      lower.includes("溫") ||
      lower.includes("गुनगुना") ||
      lower.includes("வெதுவெதுப்பான") ||
      lower.includes("कोमट")
    ) {
      setTemperature("WARM")
    } else if (
      lower.includes("room") ||
      lower.includes("常温") ||
      lower.includes("常溫") ||
      lower.includes("सामान्य") ||
      lower.includes("சாதாரண")
    ) {
      setTemperature("ROOM_TEMP")
    } else {
      setTemperature("COLD")
    }

    if (maxMatches > 1) {
      setConfidenceScore(0.94)
      setOutcome("SUGGESTED")
    } else if (maxMatches === 1) {
      setConfidenceScore(0.78)
      setOutcome("REQUIRES_CHOICE")
    } else {
      setConfidenceScore(0.55)
      setOutcome("UNRELIABLE")
    }

    // Up to two candidate alternative intents (Section 13.1 Screen C)
    const alts = CANONICAL_VISUAL_CATEGORIES.filter((c) => c !== matched).slice(
      0,
      2,
    )
    setAlternativeIntents(alts)
  }

  const uploadAudioForPreview = async (blob: Blob, filename = "voice.webm") => {
    const fd = new FormData()
    fd.append("audio", blob, filename)
    const res = await apiFetch("/api/voice_request", {
      method: "POST",
      body: fd,
    })
    if (!res.ok) {
      setErrorText(
        res.error?.message || translations[currentLanguage].voice.errorCapture,
      )
      setPreviewId(null)
      setSuggestedCategory(null)
      setAlternativeIntents([])
      return res
    }
    if (res.ok && res.data) {
      setErrorText("")
      setPreviewId(res.data.preview_id || null)
      if (typeof res.data.transcript === "string") {
        setTranscript(res.data.transcript)
      }
      if (typeof res.data.confidence === "number") {
        setConfidenceScore(res.data.confidence)
      }
      const backendOutcome = (res.data.outcome ||
        "SUGGESTED") as VoicePreviewOutcome
      setOutcome(backendOutcome)

      const tempAttr = res.data.attributes?.temperature
      if (tempAttr === "WARM") {
        setTemperature("WARM")
      } else if (tempAttr === "ROOM" || tempAttr === "ROOM_TEMP") {
        setTemperature("ROOM_TEMP")
      } else if (tempAttr === "COLD") {
        setTemperature("COLD")
      }

      const rawList =
        res.data.alternatives ||
        res.data.candidates ||
        res.data.candidate_intents ||
        []
      const rawCandidates: RequestCategory[] = Array.isArray(rawList)
        ? rawList
            .map((c: any) => (typeof c === "string" ? c : c?.intent_id))
            .filter((c: any) => CANONICAL_VISUAL_CATEGORIES.includes(c))
        : []

      if (
        backendOutcome === "SUGGESTED" &&
        res.data.intent_id &&
        CANONICAL_VISUAL_CATEGORIES.includes(res.data.intent_id)
      ) {
        const matched = res.data.intent_id as RequestCategory
        setSuggestedCategory(matched)
        const alts =
          rawCandidates.filter((c) => c !== matched).length > 0
            ? rawCandidates.filter((c) => c !== matched).slice(0, 2)
            : CANONICAL_VISUAL_CATEGORIES.filter((c) => c !== matched).slice(
                0,
                2,
              )
        setAlternativeIntents(alts)
      } else {
        // REQUIRES_CHOICE or UNRELIABLE: require explicit passenger selection
        setSuggestedCategory(null)
        const alts =
          rawCandidates.length > 0
            ? rawCandidates.slice(0, 2)
            : CANONICAL_VISUAL_CATEGORIES.slice(0, 2)
        setAlternativeIntents(alts)
      }
    }
    return res
  }

  const rejectActivePreview = () => {
    if (previewId) {
      const pid = previewId
      setPreviewId(null)
      apiFetch("/api/voice_request/none_of_these", {
        method: "POST",
        body: JSON.stringify({ preview_id: pid }),
      }).catch(() => {})
    }
  }

  const toggleListening = () => {
    playSoftTap()
    if (!recognitionRef.current && !navigator.mediaDevices?.getUserMedia) return
    if (isListening) {
      try {
        recognitionRef.current?.stop()
      } catch {}
      try {
        if (
          mediaRecorderRef.current &&
          mediaRecorderRef.current.state !== "inactive"
        ) {
          mediaRecorderRef.current.stop()
        }
      } catch {}
      setIsListening(false)
      return
    }
    setTranscript("")
    setErrorText("")
    setPreviewId(null)
    try {
      recognitionRef.current?.start()
      setIsListening(true)
    } catch {
      setIsListening(false)
    }
    if (navigator.mediaDevices?.getUserMedia) {
      navigator.mediaDevices
        .getUserMedia({ audio: true })
        .then((stream) => {
          chunksRef.current = []
          const recorder = new MediaRecorder(stream)
          mediaRecorderRef.current = recorder
          recorder.ondataavailable = (ev) => {
            if (ev.data.size > 0) chunksRef.current.push(ev.data)
          }
          recorder.onstop = () => {
            stream.getTracks().forEach((tr) => tr.stop())
            if (chunksRef.current.length > 0) {
              const blob = new Blob(chunksRef.current, { type: "audio/webm" })
              uploadAudioForPreview(blob).catch(() => {})
            }
          }
          recorder.start()
          setIsListening(true)
        })
        .catch(() => {})
    }
  }

  const handleSelectAlternative = (alt: RequestCategory) => {
    playSoftTap()
    setSuggestedCategory(alt)
    setConfidenceScore(0.85)
    setOutcome("SUGGESTED")
    const newAlts = CANONICAL_VISUAL_CATEGORIES.filter((c) => c !== alt).slice(
      0,
      2,
    )
    setAlternativeIntents(newAlts)
  }

  const handleConfirmSend = () => {
    if (isSubmitting || !suggestedCategory || !transcript.trim()) return
    setIsSubmitting(true)
    playCabinChime()

    const catInfo = t.categories[suggestedCategory]
    const attributes: Record<string, string> = {}
    if (suggestedCategory === "water_request") {
      attributes["temperature"] = temperature
    }

    // Explicit confirmation submission
    if (previewId) {
      apiFetch("/api/voice_request/confirm", {
        method: "POST",
        body: JSON.stringify({
          preview_id: previewId,
          intent_id: suggestedCategory,
        }),
      }).then((res) => {
        if (res.ok && res.data) {
          const reqId = res.data.id || res.data.request_id
          if (reqId) {
            saveRequestMeta(reqId, {
              attributes,
              notes: transcript.trim(),
              cancelled: false,
            })
          }
          try {
            window.dispatchEvent(new Event("storage"))
          } catch {}
        } else {
          onSubmit({
            category: suggestedCategory,
            subDetails: `${catInfo.label}${
              suggestedCategory === "water_request" ? ` (${temperature})` : ""
            }`,
            notes: transcript.trim(),
            attributes,
          })
        }
        setIsSubmitting(false)
        onClose()
      })
      return
    }

    setTimeout(() => {
      onSubmit({
        category: suggestedCategory,
        subDetails: `${catInfo.label}${
          suggestedCategory === "water_request" ? ` (${temperature})` : ""
        }`,
        notes: transcript.trim(),
        attributes,
      })
      setIsSubmitting(false)
      onClose()
    }, 350)
  }

  const suggestedMetadata = suggestedCategory
    ? INTENT_CATALOG[suggestedCategory]
    : null
  const isUrgent = suggestedMetadata?.priority === "URGENT"

  const headerSubtext =
    currentLanguage === "ja"
      ? "送信前に内容を確認してください"
      : currentLanguage === "zh"
        ? "發送前確認內容"
        : currentLanguage === "hi"
          ? "भेजने से पहले समीक्षा और पुष्टि करें"
          : currentLanguage === "ta"
            ? "அனுப்புவதற்கு முன் சரிபார்த்து உறுதிப்படுத்தவும்"
            : currentLanguage === "mr"
              ? "पाठवण्यापूर्वी तपासा आणि खात्री करा"
              : "Review & Confirm before submission"

  const switchIntentNotice =
    currentLanguage === "ja"
      ? "このリクエストに変更"
      : currentLanguage === "zh"
        ? "切換至此項目"
        : currentLanguage === "hi"
          ? "इस अनुरोध पर बदलें"
          : currentLanguage === "ta"
            ? "இந்த விருப்பத்திற்கு மாற்றவும்"
            : currentLanguage === "mr"
              ? "या विनंतीवर बदला"
              : "Switch to this intent"

  const getTemperatureLabels = () => {
    switch (currentLanguage) {
      case "ja":
        return { cold: "冷水", room: "常温", warm: "白湯" }
      case "zh":
        return { cold: "冰水", room: "常溫", warm: "溫熱" }
      case "hi":
        return { cold: "ठंडा", room: "सामान्य", warm: "गुनगुना" }
      case "ta":
        return { cold: "குளிர்ந்த", room: "சாதாரண", warm: "வெதுவெதுப்பான" }
      case "mr":
        return { cold: "थंड", room: "सामान्य", warm: "कोमट" }
      default:
        return { cold: "Cold", room: "Room Temp", warm: "Warm" }
    }
  }

  const tempLabels = getTemperatureLabels()

  return (
    <div className="fixed inset-0 z-50 flex items-end sm:items-center justify-center p-0 sm:p-4 bg-[#202124]/65 backdrop-blur-xs animate-in fade-in duration-200">
      <div
        className="absolute inset-0"
        onClick={() => {
          rejectActivePreview()
          onClose()
        }}
      />

      <div className="relative w-full sm:max-w-lg bg-white rounded-t-3xl sm:rounded-2xl shadow-2xl border border-[#202124]/10 overflow-hidden z-10 animate-in slide-in-from-bottom-6 sm:zoom-in-95 duration-200 max-h-[92dvh] flex flex-col">
        {/* Header */}
        <div className="px-5 py-3.5 border-b border-[#202124]/[0.08] flex items-center justify-between gap-2 bg-[#FAF8F3]">
          <div className="flex items-center gap-2.5 min-w-0">
            <div className="w-8 h-8 rounded-full bg-[#C8102E] text-white flex items-center justify-center shrink-0">
              <Sparkles className="w-4 h-4" />
            </div>
            <div>
              <h3 className="font-bold text-[#202124] text-base leading-tight">
                {t.voice.title}
              </h3>
              <p className="text-[11px] text-[#5F6368]">{headerSubtext}</p>
            </div>
          </div>
          <button
            onClick={() => {
              playSoftTap()
              rejectActivePreview()
              onClose()
            }}
            aria-label={t.actions.close}
            className="w-11 h-11 -mr-2 inline-flex items-center justify-center rounded-full text-[#5F6368] hover:text-[#202124] hover:bg-[#EDE8DE]/60 transition-colors cursor-pointer"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        <div className="p-5 overflow-y-auto space-y-4">
          {/* Microphone tap bar */}
          <div className="flex items-center justify-between p-3 rounded-2xl bg-[#FAF8F3] border border-[#202124]/[0.06]">
            <div className="flex items-center gap-3">
              <button
                type="button"
                onClick={toggleListening}
                disabled={!SpeechRecognitionCtor}
                className={`w-12 h-12 rounded-full flex items-center justify-center text-white shadow-sm transition-all active:scale-95 disabled:opacity-40 cursor-pointer ${
                  isListening
                    ? "bg-[#C8102E] animate-pulse"
                    : "bg-[#202124] hover:bg-black"
                }`}
                aria-label={isListening ? "Stop listening" : "Tap to speak"}
              >
                <Mic className="w-5 h-5" />
              </button>
              <div className="text-xs">
                <span className="font-bold text-[#202124] block">
                  {!SpeechRecognitionCtor
                    ? "Microphone unavailable"
                    : isListening
                      ? t.voice.listening
                      : t.voice.tapToSpeak}
                </span>
                <span className="text-[#5F6368] text-[11px]">
                  Web Speech Recognition
                </span>
              </div>
            </div>

            {/* Outcome Badge if transcript exists */}
            {suggestedCategory && (
              <span
                className={`px-2.5 py-1 rounded-full text-[10px] font-bold border ${
                  outcome === "SUGGESTED"
                    ? "bg-emerald-50 text-emerald-800 border-emerald-200"
                    : outcome === "REQUIRES_CHOICE"
                      ? "bg-amber-50 text-amber-800 border-amber-200"
                      : "bg-red-50 text-red-800 border-red-200"
                }`}
              >
                {outcome === "SUGGESTED"
                  ? t.voice.outcomeSuggested.split(" ")[0] || "SUGGESTED"
                  : outcome}
              </span>
            )}
          </div>

          {!SpeechRecognitionCtor && (
            <div className="p-3 rounded-xl bg-amber-50 border border-amber-200 text-amber-900 text-xs">
              {t.voice.unsupported}
            </div>
          )}

          {errorText && (
            <div className="p-2.5 rounded-xl bg-red-50 border border-red-200 text-red-800 text-xs flex items-center gap-2">
              <AlertCircle className="w-4 h-4 shrink-0" />
              <span>{errorText}</span>
            </div>
          )}

          {/* Transcript Field (Editable per Section 13.1 Screen C) */}
          <div className="space-y-1.5">
            <div className="flex items-center justify-between">
              <label className="text-xs font-semibold uppercase tracking-wider text-[#5F6368]">
                {t.voice.transcriptLabel}
              </label>
              <span className="text-[10px] text-[#80868B]">Editable</span>
            </div>
            <textarea
              value={transcript}
              onChange={(e) => {
                setTranscript(e.target.value)
                classifySpokenText(e.target.value)
              }}
              placeholder={t.voice.transcriptPlaceholder}
              rows={2}
              className="w-full p-3 rounded-xl border border-[#202124]/15 bg-white text-sm text-[#202124] focus:outline-hidden focus:ring-2 focus:ring-[#C8102E]/40 leading-relaxed resize-none placeholder:text-[#80868B]"
            />
          </div>

          {/* Empty Prompt when no transcript yet */}
          {!transcript.trim() && (
            <div className="p-6 text-center rounded-2xl bg-[#FAF8F3] border border-dashed border-[#202124]/10 text-xs text-[#5F6368] space-y-2">
              <p>{t.voice.emptyPrompt}</p>
              {onSwitchToTyped && (
                <button
                  type="button"
                  onClick={() => {
                    playSoftTap()
                    rejectActivePreview()
                    onClose()
                    onSwitchToTyped()
                  }}
                  className="inline-flex items-center gap-1.5 text-xs font-semibold text-[#C8102E] hover:underline cursor-pointer"
                >
                  <Edit3 className="w-3.5 h-3.5" />
                  <span>{t.typedButton}</span>
                </button>
              )}
            </div>
          )}

          {/* Suggested Intent Card (Only shown when an intent was detected) */}
          {suggestedCategory && (
            <div className="space-y-2">
              <span className="text-xs font-semibold uppercase tracking-wider text-[#5F6368] block">
                {t.voice.suggestedIntent}
              </span>

              <div className="p-4 rounded-2xl bg-[#FAF8F3] border border-[#202124]/10 shadow-2xs space-y-3">
                <div className="flex items-start justify-between gap-3">
                  <div className="flex items-center gap-3">
                    <div className="w-11 h-11 rounded-xl bg-white border border-[#202124]/10 flex items-center justify-center text-[#C8102E] shrink-0">
                      <CategoryIcon category={suggestedCategory} size={22} />
                    </div>
                    <div>
                      <div className="flex items-center gap-2">
                        <h4 className="font-bold text-sm sm:text-base text-[#202124]">
                          {t.categories[suggestedCategory].label}
                        </h4>
                        {isUrgent ? (
                          <span className="px-2 py-0.5 rounded-full bg-red-100 text-red-900 border border-red-300 text-[10px] font-bold">
                            {t.priorities.URGENT}
                          </span>
                        ) : (
                          <span className="px-2 py-0.5 rounded-full bg-stone-100 text-[#5F6368] border border-stone-200 text-[10px] font-semibold">
                            {t.priorities.ROUTINE}
                          </span>
                        )}
                      </div>
                      <p className="text-xs text-[#5F6368] mt-0.5">
                        {t.categories[suggestedCategory].description}
                      </p>
                    </div>
                  </div>

                  <div className="text-right shrink-0">
                    <span className="text-[10px] text-[#80868B] block uppercase tracking-wider">
                      {t.voice.confidence}
                    </span>
                    <span className="font-mono text-xs font-bold text-emerald-700">
                      {Math.round(confidenceScore * 100)}%
                    </span>
                  </div>
                </div>

                {/* Attributes (e.g. Temperature for water) */}
                {suggestedCategory === "water_request" && (
                  <div className="pt-2 border-t border-[#202124]/[0.06] flex items-center justify-between gap-2 flex-wrap">
                    <span className="text-xs font-semibold text-[#5F6368]">
                      {t.voice.attributes}:
                    </span>
                    <div className="flex items-center gap-1.5">
                      {[
                        { id: "COLD", label: tempLabels.cold },
                        { id: "ROOM_TEMP", label: tempLabels.room },
                        { id: "WARM", label: tempLabels.warm },
                      ].map((opt) => (
                        <button
                          key={opt.id}
                          type="button"
                          onClick={() => {
                            playSoftTap()
                            setTemperature(opt.id as any)
                          }}
                          className={`px-2.5 py-1 rounded-lg text-xs font-semibold transition-colors cursor-pointer ${
                            temperature === opt.id
                              ? "bg-[#C8102E] text-white"
                              : "bg-white border border-[#202124]/10 text-[#5F6368] hover:bg-stone-100"
                          }`}
                        >
                          {opt.label}
                        </button>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            </div>
          )}

          {/* Up to Two Candidate Alternative Intents (Section 13.1 Screen C) */}
          {alternativeIntents.length > 0 && (
            <div className="space-y-1.5">
              <span className="text-xs font-semibold uppercase tracking-wider text-[#5F6368] block">
                {t.voice.alternatives}
              </span>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                {alternativeIntents.map((alt) => (
                  <button
                    key={alt}
                    type="button"
                    onClick={() => handleSelectAlternative(alt)}
                    className="p-2.5 rounded-xl border border-[#202124]/10 hover:border-[#202124]/20 hover:bg-[#FAF8F3] text-left transition-all flex items-center gap-2.5 cursor-pointer"
                  >
                    <div className="w-7 h-7 rounded-lg bg-stone-100 flex items-center justify-center text-[#202124] shrink-0">
                      <CategoryIcon category={alt} size={15} />
                    </div>
                    <div className="min-w-0">
                      <span className="text-xs font-bold text-[#202124] block truncate">
                        {t.categories[alt].label}
                      </span>
                      <span className="text-[10px] text-[#80868B] block truncate">
                        {switchIntentNotice}
                      </span>
                    </div>
                  </button>
                ))}
              </div>
            </div>
          )}

          {/* Primary Action Buttons */}
          <div className="pt-2 flex items-center gap-3">
            <button
              type="button"
              onClick={() => {
                playSoftTap()
                rejectActivePreview()
                onClose()
              }}
              disabled={isSubmitting}
              className="w-1/3 min-h-12 px-4 rounded-xl border border-[#202124]/15 font-semibold text-xs text-[#202124] hover:bg-stone-50 transition-colors cursor-pointer"
            >
              {t.actions.cancel}
            </button>

            <button
              type="button"
              disabled={
                isSubmitting || !suggestedCategory || !transcript.trim()
              }
              onClick={handleConfirmSend}
              className="w-2/3 min-h-12 px-4 rounded-xl bg-[#C8102E] hover:bg-[#B00E28] active:bg-[#8F0A20] disabled:opacity-40 text-white font-semibold text-xs tracking-wide shadow-md transition-all active:scale-[0.98] flex items-center justify-center gap-2 cursor-pointer"
            >
              {isSubmitting ? (
                <>
                  <RefreshCw className="w-4 h-4 animate-spin" />
                  <span>{t.voice.submitting}</span>
                </>
              ) : (
                <>
                  <Check className="w-4 h-4" />
                  <span>{t.voice.confirmSend}</span>
                </>
              )}
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}
