import React, { useState, useEffect } from "react"
import { PABroadcast, Language } from "../types"
import { Megaphone, Radio, Clock } from "lucide-react"

interface ActivePABannerProps {
  broadcast: PABroadcast | null
  currentLanguage: Language
}

export const ActivePABanner: React.FC<ActivePABannerProps> = ({
  broadcast,
  currentLanguage,
}) => {
  const [secondsLeft, setSecondsLeft] = useState<number>(0)

  useEffect(() => {
    if (!broadcast || broadcast.active_status !== "ACTIVE") {
      setSecondsLeft(0)
      return
    }

    const calc = () => {
      const remaining = Math.max(
        0,
        Math.floor((broadcast.expires_at_ms - Date.now()) / 1000),
      )
      setSecondsLeft(remaining)
    }

    calc()
    const timer = setInterval(calc, 1000)
    return () => clearInterval(timer)
  }, [broadcast])

  if (!broadcast || broadcast.active_status !== "ACTIVE" || secondsLeft <= 0) {
    return null
  }

  const formatCountdown = (totalSeconds: number) => {
    const mins = Math.floor(totalSeconds / 60)
    const secs = totalSeconds % 60
    return `${mins}:${secs.toString().padStart(2, "0")}`
  }

  const getTitle = () => {
    switch (currentLanguage) {
      case "ja":
        return broadcast.title_ja || broadcast.title_en
      case "zh":
        return broadcast.title_zh || broadcast.title_en
      case "hi":
        return broadcast.title_hi || broadcast.title_en
      case "ta":
        return broadcast.title_ta || broadcast.title_en
      case "mr":
        return broadcast.title_mr || broadcast.title_en
      default:
        return broadcast.title_en
    }
  }

  const getMessage = () => {
    switch (currentLanguage) {
      case "ja":
        return broadcast.text_ja || broadcast.text_en
      case "zh":
        return broadcast.text_zh || broadcast.text_en
      case "hi":
        return broadcast.text_hi || broadcast.text_en
      case "ta":
        return broadcast.text_ta || broadcast.text_en
      case "mr":
        return broadcast.text_mr || broadcast.text_en
      default:
        return broadcast.text_en
    }
  }

  const title = getTitle()
  const message = getMessage()

  const bannerBadgeLabel =
    currentLanguage === "ja"
      ? "機内アナウンス"
      : currentLanguage === "zh"
        ? "客艙廣播"
        : currentLanguage === "hi"
          ? "केबिन घोषणा"
          : currentLanguage === "ta"
            ? "கேபின் பொது அறிவிப்பு"
            : currentLanguage === "mr"
              ? "केबिन घोषणा"
              : "CABIN ANNOUNCEMENT"

  return (
    <div
      role="region"
      aria-label="Active Cabin Announcement"
      className="w-full rounded-2xl bg-[#C8102E] text-white p-4 shadow-md border border-[#8F0A20] animate-in fade-in slide-in-from-top-3 duration-300 relative overflow-hidden"
    >
      {/* Decorative background watermark */}
      <div className="absolute right-0 top-0 bottom-0 w-32 pointer-events-none opacity-10 flex items-center justify-end pr-4 text-white">
        <Megaphone className="w-24 h-24" />
      </div>

      <div className="relative z-10 space-y-2">
        <div className="flex items-center justify-between gap-2 flex-wrap">
          <div className="flex items-center gap-2">
            <span className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full bg-white/20 text-[10px] font-bold tracking-wider uppercase backdrop-blur-xs">
              <Radio className="w-3 h-3 text-white animate-pulse" />
              <span>{bannerBadgeLabel}</span>
            </span>

            <span className="px-2 py-0.5 rounded-full bg-black/20 text-[10px] font-semibold text-white/90">
              {broadcast.category}
            </span>
          </div>

          <div className="flex items-center gap-1.5 text-xs font-semibold bg-black/20 px-2.5 py-0.5 rounded-full text-white/95">
            <Clock className="w-3.5 h-3.5" />
            <span>{formatCountdown(secondsLeft)}</span>
          </div>
        </div>

        <div>
          <h3 className="font-['Noto_Serif_JP',serif] text-sm sm:text-base font-bold tracking-tight">
            {title}
          </h3>
          <p className="text-xs sm:text-sm text-white/95 mt-1 leading-relaxed font-normal">
            {message}
          </p>
          {currentLanguage !== "en" && broadcast.text_en && (
            <p className="text-[11px] text-white/80 mt-0.5 italic">
              {broadcast.text_en}
            </p>
          )}
        </div>
      </div>
    </div>
  )
}
