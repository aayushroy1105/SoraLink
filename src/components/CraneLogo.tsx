import React from "react"

interface CraneLogoProps {
  className?: string
  size?: "sm" | "md" | "lg"
  showWordmark?: boolean
  showHanko?: boolean
}

export const CraneLogo: React.FC<CraneLogoProps> = ({
  className = "",
  size = "md",
  showWordmark = true,
  showHanko = true,
}) => {
  const emblemSizes = {
    sm: "w-8 h-8",
    md: "w-12 h-12",
    lg: "w-16 h-16",
  }

  const wordmarkSizes = {
    sm: "text-lg sm:text-xl",
    md: "text-2xl sm:text-3xl",
    lg: "text-3xl sm:text-4xl",
  }

  return (
    <div className={`inline-flex items-center gap-2.5 ${className}`}>
      {/* Finalized SoraLink Crimson Crane Emblem */}
      <div
        className={`relative ${emblemSizes[size]} aspect-square flex items-center justify-center shrink-0 drop-shadow-xs`}
      >
        <img
          src="/static/img/soralink-crane-emblem-128.png"
          srcSet="/static/img/soralink-crane-emblem-64.png 64w, /static/img/soralink-crane-emblem-128.png 128w, /static/img/soralink-crane-emblem-256.png 256w, /static/img/soralink-crane-emblem.png 1097w"
          sizes="(max-width: 640px) 32px, 48px"
          alt="SoraLink Crane Emblem"
          className="w-full h-full object-contain rounded-full select-none"
          draggable={false}
          loading="eager"
        />
      </div>

      {showWordmark && (
        <div className="flex flex-col min-w-0">
          <div className="flex items-center gap-1.5">
            <span
              className={`font-['Plus_Jakarta_Sans',sans-serif] font-bold tracking-tight text-[#202124] ${wordmarkSizes[size]} leading-none`}
            >
              Sora<span className="text-[#C8102E]">Link</span>
            </span>
            {showHanko && (
              <span className="hidden min-[360px]:inline-flex items-center justify-center px-1.5 py-0.5 rounded-xs bg-[#C8102E] text-white text-[9px] font-['Noto_Serif_JP',serif] font-bold tracking-widest leading-none border border-[#8F0A20] select-none shadow-2xs">
                空連
              </span>
            )}
          </div>
        </div>
      )}
    </div>
  )
}
