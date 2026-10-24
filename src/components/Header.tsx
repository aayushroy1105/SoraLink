import React, { useState, useRef, useEffect } from "react"
import { CraneLogo } from "./CraneLogo"
import { Language, AppScreen } from "../types"
import { translations } from "../utils/translations"
import {
  Volume2,
  VolumeX,
  Globe,
  ChevronDown,
  Check,
  ShieldCheck,
  LogOut,
} from "lucide-react"
import { isSoundEnabled, toggleSound, playSoftTap } from "../utils/audio"

interface HeaderProps {
  currentLanguage: Language
  onLanguageChange: (lang: Language) => void
  seatLabel: string
  currentScreen: AppScreen
  onLogoutCrew?: () => void
}

const LANGUAGES: { code: Language; label: string; sub: string }[] = [
  { code: "en", label: "English", sub: "EN" },
  { code: "ja", label: "日本語", sub: "JA" },
  { code: "zh", label: "繁體中文", sub: "ZH" },
  { code: "hi", label: "हिन्दी", sub: "HI" },
  { code: "ta", label: "தமிழ்", sub: "TA" },
  { code: "mr", label: "मराठी", sub: "MR" },
]

export const Header: React.FC<HeaderProps> = ({
  currentLanguage,
  onLanguageChange,
  seatLabel,
  currentScreen,
  onLogoutCrew,
}) => {
  const t = translations[currentLanguage]
  const [langDropdownOpen, setLangDropdownOpen] = useState(false)
  const [soundOn, setSoundOn] = useState(true)
  const dropdownRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    setSoundOn(isSoundEnabled())
  }, [])

  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (
        dropdownRef.current &&
        !dropdownRef.current.contains(event.target as Node)
      ) {
        setLangDropdownOpen(false)
      }
    }
    document.addEventListener("mousedown", handleClickOutside)
    return () => document.removeEventListener("mousedown", handleClickOutside)
  }, [])

  const handleSoundToggle = () => {
    const next = toggleSound()
    setSoundOn(next)
    if (next) playSoftTap()
  }

  const isCrewScreen =
    currentScreen === "crew-dashboard" || currentScreen === "crew-login"

  return (
    <header className="sticky top-0 z-30 w-full bg-[#FAF8F3]/95 backdrop-blur-md border-b border-[#202124]/[0.08] transition-colors">
      <div className="max-w-6xl mx-auto px-2.5 sm:px-6 lg:px-8 py-2 pt-[max(0.5rem,env(safe-area-inset-top))] flex items-center justify-between gap-1.5 sm:gap-3 min-w-0">
        {/* Brand Logo & Wordmark (responsive scaling to prevent 320px overlap) */}
        <div className="flex items-center gap-2 min-w-0 shrink">
          <div className="flex items-center text-left">
            <CraneLogo
              size="sm"
              showWordmark={true}
              showHanko={true}
              className="scale-95 min-[360px]:scale-100 origin-left"
            />
          </div>

          {/* Seat indicator on passenger screens (hidden below 380px to preserve spacing) */}
          {!isCrewScreen && seatLabel && (
            <div className="hidden min-[380px]:inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full bg-white border border-[#202124]/10 text-xs font-semibold text-[#202124] shadow-2xs">
              <span className="text-[10px] text-[#80868B] uppercase">Seat</span>
              <span>{seatLabel}</span>
            </div>
          )}

          {/* Crew badge indicator on crew screens */}
          {isCrewScreen && (
            <span className="hidden min-[380px]:inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-[#202124] text-white text-[10px] font-bold tracking-wider">
              <ShieldCheck className="w-3 h-3 text-[#C8102E]" />
              <span>CREW</span>
            </span>
          )}
        </div>

        {/* Right Action Controls: Sound, Language, Crew Logout */}
        <div className="flex items-center gap-1 sm:gap-2 shrink-0">
          {/* Sound Cabin Chime Mute/Unmute */}
          <button
            type="button"
            onClick={handleSoundToggle}
            className="w-11 h-11 inline-flex items-center justify-center rounded-full text-[#5F6368] hover:text-[#202124] hover:bg-[#EDE8DE]/60 transition-colors cursor-pointer"
            title={soundOn ? "Mute cabin chimes" : "Enable cabin chimes"}
            aria-label={soundOn ? "Mute cabin sound" : "Enable cabin sound"}
          >
            {soundOn ? (
              <Volume2 className="w-4 h-4 sm:w-5 sm:h-5 text-[#202124]" />
            ) : (
              <VolumeX className="w-4 h-4 sm:w-5 sm:h-5 text-[#80868B]" />
            )}
          </button>

          {/* Language Selector Dropdown (EN / JA / ZH / HI / TA / MR) */}
          <div className="relative" ref={dropdownRef}>
            <button
              type="button"
              onClick={() => setLangDropdownOpen(!langDropdownOpen)}
              className="flex items-center gap-1 px-2.5 min-h-11 rounded-full bg-white border border-[#202124]/10 text-xs font-semibold text-[#202124] hover:border-[#C8102E]/40 transition-all shadow-2xs focus:outline-hidden focus:ring-1 focus:ring-[#C8102E]/40 active:scale-95 cursor-pointer"
              aria-haspopup="true"
              aria-expanded={langDropdownOpen}
              aria-label="Select Language"
            >
              <Globe className="w-3.5 h-3.5 text-[#C8102E]" />
              <span className="uppercase text-[11px] tracking-wide font-bold">
                {currentLanguage.toUpperCase()}
              </span>
              <ChevronDown className="w-3 h-3 text-[#5F6368]" />
            </button>

            {langDropdownOpen && (
              <div className="absolute right-0 mt-1.5 w-44 bg-white rounded-2xl shadow-xl border border-[#202124]/10 py-1.5 z-50 text-xs animate-in fade-in zoom-in-95 duration-150 max-h-[80vh] overflow-y-auto">
                <div className="px-3 py-1.5 text-[10px] font-semibold tracking-wider text-[#5F6368] uppercase border-b border-[#202124]/5 mb-1">
                  Language / 言語 / भाषा / மொழி
                </div>
                {LANGUAGES.map((item) => (
                  <button
                    key={item.code}
                    type="button"
                    onClick={() => {
                      onLanguageChange(item.code)
                      setLangDropdownOpen(false)
                      playSoftTap()
                    }}
                    className={`w-full flex items-center justify-between px-3 min-h-11 text-left transition-colors cursor-pointer ${
                      currentLanguage === item.code
                        ? "bg-[#FBECEE] text-[#C8102E] font-semibold"
                        : "text-[#202124] hover:bg-[#FAF8F3]"
                    }`}
                  >
                    <span className="text-xs font-medium">{item.label}</span>
                    <div className="flex items-center gap-1.5">
                      {currentLanguage === item.code ? (
                        <Check className="w-3.5 h-3.5 text-[#C8102E]" />
                      ) : (
                        <span className="text-[10px] text-[#80868B] font-mono">
                          {item.sub}
                        </span>
                      )}
                    </div>
                  </button>
                ))}
              </div>
            )}
          </div>

          {/* Crew Logout action when on crew screens */}
          {isCrewScreen &&
            currentScreen === "crew-dashboard" &&
            onLogoutCrew && (
              <button
                type="button"
                onClick={() => {
                  playSoftTap()
                  onLogoutCrew()
                }}
                className="flex items-center gap-1.5 px-3 min-h-11 rounded-full bg-[#202124] text-white hover:bg-black text-xs font-semibold transition-colors cursor-pointer shadow-xs"
                title={t.actions.logout}
                aria-label={t.actions.logout}
              >
                <LogOut className="w-3.5 h-3.5 shrink-0" />
                <span className="text-xs font-semibold">
                  {t.actions.logout}
                </span>
              </button>
            )}
        </div>
      </div>
    </header>
  )
}
