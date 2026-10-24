import React from "react"
import { RequestCategory, Language } from "../types"
import { translations } from "../utils/translations"
import { CategoryIcon } from "./RequestIcons"
import { playSoftTap } from "../utils/audio"

interface RequestGridProps {
  currentLanguage: Language
  onSelectCategory: (category: RequestCategory) => void
  activeCountByCategory: Record<RequestCategory, number>
}

export const RequestGrid: React.FC<RequestGridProps> = ({
  currentLanguage,
  onSelectCategory,
  activeCountByCategory,
}) => {
  const t = translations[currentLanguage]

  const categories: {
    key: RequestCategory
    kanjiBadge: string
    bgHover: string
  }[] = [
    {
      key: "water_request",
      kanjiBadge: "水",
      bgHover: "hover:border-[#0284C7]/40 hover:shadow-md",
    },
    {
      key: "blanket_request",
      kanjiBadge: "毛",
      bgHover: "hover:border-[#C8102E]/40 hover:shadow-md",
    },
    {
      key: "pillow_request",
      kanjiBadge: "枕",
      bgHover: "hover:border-[#B8860B]/40 hover:shadow-md",
    },
    {
      key: "accessibility_assist",
      kanjiBadge: "介",
      bgHover: "hover:border-[#C8102E]/60 hover:shadow-md",
    },
  ]

  const getActiveBadgeText = (count: number) => {
    switch (currentLanguage) {
      case "ja":
        return `${count}件進行中`
      case "zh":
        return `${count}項進行中`
      case "hi":
        return `${count} सक्रिय`
      case "ta":
        return `${count} செயலில்`
      case "mr":
        return `${count} सक्रिय`
      default:
        return `${count} active`
    }
  }

  return (
    <div className="w-full">
      {/* 
        Responsive layout with items-stretch and h-full cards so all cards in the row
        match height and allow vertical expansion without text overflow or clipped borders.
      */}
      <div className="grid grid-cols-1 min-[360px]:grid-cols-2 sm:grid-cols-4 lg:grid-cols-2 xl:grid-cols-4 gap-3 sm:gap-4 items-stretch">
        {categories.map((item) => {
          const categoryInfo = t.categories[item.key]
          const activeCount = activeCountByCategory[item.key] || 0
          const isUrgent = item.key === "accessibility_assist"

          return (
            <div
              key={item.key}
              role="button"
              tabIndex={0}
              onClick={() => {
                playSoftTap()
                onSelectCategory(item.key)
              }}
              onKeyDown={(e) => {
                if (e.key === "Enter" || e.key === " ") {
                  e.preventDefault()
                  playSoftTap()
                  onSelectCategory(item.key)
                }
              }}
              className={`group relative flex flex-col justify-between h-full p-3.5 sm:p-4 rounded-2xl min-w-0 bg-white border border-[#202124]/[0.08] text-left transition-all duration-200 cursor-pointer shadow-xs active:scale-[0.98] select-none min-h-[160px] sm:min-h-[175px] focus:outline-hidden focus:ring-2 focus:ring-[#C8102E]/30 ${item.bgHover}`}
            >
              {/* Active count badge if present */}
              {activeCount > 0 && (
                <div className="absolute top-2.5 right-2.5 flex items-center gap-1 px-2 py-0.5 rounded-full bg-[#FBECEE] text-[#C8102E] text-[10px] font-bold border border-[#C8102E]/20">
                  <span className="w-1.5 h-1.5 rounded-full bg-[#C8102E] animate-pulse" />
                  <span>{getActiveBadgeText(activeCount)}</span>
                </div>
              )}

              {/* Icon and Kanji mark */}
              <div className="flex items-start justify-between w-full">
                <div
                  className={`w-11 h-11 rounded-xl flex items-center justify-center transition-colors shrink-0 ${
                    isUrgent
                      ? "bg-[#FBECEE] text-[#C8102E] group-hover:bg-[#C8102E] group-hover:text-white"
                      : "bg-[#FAF8F3] border border-[#202124]/[0.06] text-[#202124] group-hover:text-[#C8102E] group-hover:bg-[#FBECEE]/50"
                  }`}
                >
                  <CategoryIcon category={item.key} size={24} />
                </div>

                <span className="font-['Noto_Serif_JP',serif] text-xl font-light text-[#202124]/10 select-none group-hover:text-[#C8102E]/20 transition-colors">
                  {item.kanjiBadge}
                </span>
              </div>

              {/* Text content with flexible expansion and overflow-wrap: anywhere */}
              <div className="mt-3 min-w-0 flex-1 flex flex-col justify-end">
                <div className="flex items-baseline gap-1.5 flex-wrap min-w-0">
                  <h3 className="font-bold text-[#202124] text-sm sm:text-base leading-snug break-words [overflow-wrap:anywhere] group-hover:text-[#C8102E] transition-colors min-w-0">
                    {categoryInfo.label}
                  </h3>
                  {categoryInfo.subLabel && currentLanguage !== "ja" && (
                    <span className="font-['Noto_Serif_JP',serif] text-xs text-[#5F6368] font-normal shrink-0">
                      {categoryInfo.subLabel}
                    </span>
                  )}
                </div>

                <p className="text-xs text-[#5F6368] line-clamp-3 mt-1 leading-relaxed font-normal break-words [overflow-wrap:anywhere]">
                  {categoryInfo.description}
                </p>
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}
