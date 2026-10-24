import React, { useState } from "react"
import { Language } from "../types"
import { translations } from "../utils/translations"
import { CraneLogo } from "./CraneLogo"
import { ArrowRight, AlertCircle, Loader2 } from "lucide-react"
import { playSoftTap, playCabinChime } from "../utils/audio"
import { apiLoginPassenger } from "../utils/api"

interface PassengerLoginProps {
  currentLanguage: Language
  onLoginSuccess: (seatLabel: string) => void
}

export const PassengerLogin: React.FC<PassengerLoginProps> = ({
  currentLanguage,
  onLoginSuccess,
}) => {
  const t = translations[currentLanguage]
  const [seatInput, setSeatInput] = useState("")
  const [inviteInput, setInviteInput] = useState("")
  const [seatError, setSeatError] = useState("")
  const [inviteError, setInviteError] = useState("")
  const [isLoading, setIsLoading] = useState(false)

  const handleLogin = (e: React.FormEvent) => {
    e.preventDefault()
    playSoftTap()

    let valid = true
    const seatTrimmed = seatInput.trim().toUpperCase()
    const inviteTrimmed = inviteInput.trim().toUpperCase()

    if (!seatTrimmed || !/^[0-9]{1,2}[A-K]$/i.test(seatTrimmed)) {
      setSeatError(t.passengerLogin.seatError)
      valid = false
    } else {
      setSeatError("")
    }

    if (!inviteTrimmed) {
      setInviteError(t.passengerLogin.codeError)
      valid = false
    } else {
      setInviteError("")
    }

    if (!valid) return

    setIsLoading(true)

    // Authenticate seat against real backend
    apiLoginPassenger(seatTrimmed, inviteTrimmed).then((res) => {
      setIsLoading(false)
      if (res.ok && res.data) {
        playCabinChime()
        onLoginSuccess(res.data.seat_label || seatTrimmed)
      } else if (res.status === 0) {
        // Offline local fallback
        playCabinChime()
        onLoginSuccess(seatTrimmed)
      } else {
        setInviteError(res.error?.message || t.passengerLogin.codeError)
      }
    })
  }

  return (
    <div className="w-full max-w-md mx-auto px-4 py-8 sm:py-12 flex flex-col justify-center min-h-[calc(100dvh-5rem)]">
      <div className="bg-white rounded-3xl border border-[#202124]/[0.08] shadow-lg p-6 sm:p-8 space-y-6">
        <div className="text-center space-y-2">
          <div className="flex justify-center mb-1">
            <CraneLogo size="md" showWordmark={true} showHanko={true} />
          </div>
          <h1 className="font-['Noto_Serif_JP',serif] text-xl sm:text-2xl font-bold text-[#202124] tracking-tight">
            {t.passengerLogin.title}
          </h1>
          <p className="text-xs sm:text-sm text-[#5F6368] font-normal leading-relaxed">
            {t.passengerLogin.subtitle}
          </p>
        </div>

        <form onSubmit={handleLogin} className="space-y-4">
          <div>
            <label className="block text-xs font-semibold uppercase tracking-wider text-[#5F6368] mb-1.5">
              {t.passengerLogin.seatLabel}
            </label>
            <div className="relative">
              <input
                type="text"
                value={seatInput}
                onChange={(e) => {
                  setSeatInput(e.target.value.toUpperCase())
                  if (seatError) setSeatError("")
                }}
                placeholder={t.passengerLogin.seatPlaceholder}
                disabled={isLoading}
                maxLength={4}
                className="w-full px-4 min-h-12 rounded-xl border border-[#202124]/15 bg-[#FAF8F3]/50 text-base font-bold text-[#202124] placeholder:font-normal placeholder:text-[#80868B] focus:bg-white focus:outline-hidden focus:ring-2 focus:ring-[#C8102E]/40 tracking-wider"
              />
              <span className="absolute right-3.5 top-3.5 text-xs text-[#80868B] font-medium pointer-events-none">
                SEAT
              </span>
            </div>
            {seatError && (
              <p className="mt-1 text-xs text-[#C8102E] flex items-center gap-1 font-medium">
                <AlertCircle className="w-3.5 h-3.5 shrink-0" />
                <span>{seatError}</span>
              </p>
            )}
          </div>

          <div>
            <label className="block text-xs font-semibold uppercase tracking-wider text-[#5F6368] mb-1.5">
              {t.passengerLogin.inviteCode}
            </label>
            <div className="relative">
              <input
                type="text"
                value={inviteInput}
                onChange={(e) => {
                  setInviteInput(e.target.value.toUpperCase())
                  if (inviteError) setInviteError("")
                }}
                placeholder={t.passengerLogin.invitePlaceholder}
                disabled={isLoading}
                maxLength={12}
                className="w-full px-4 min-h-12 rounded-xl border border-[#202124]/15 bg-[#FAF8F3]/50 text-base font-bold text-[#202124] placeholder:font-normal placeholder:text-[#80868B] focus:bg-white focus:outline-hidden focus:ring-2 focus:ring-[#C8102E]/40 tracking-wider"
              />
              <span className="absolute right-3.5 top-3.5 text-xs text-[#80868B] font-medium pointer-events-none">
                CODE
              </span>
            </div>
            {inviteError && (
              <p className="mt-1 text-xs text-[#C8102E] flex items-center gap-1 font-medium">
                <AlertCircle className="w-3.5 h-3.5 shrink-0" />
                <span>{inviteError}</span>
              </p>
            )}
          </div>

          <button
            type="submit"
            disabled={isLoading}
            className="w-full min-h-12 rounded-xl bg-[#C8102E] hover:bg-[#B00E28] active:bg-[#8F0A20] text-white font-semibold text-sm shadow-md transition-all flex items-center justify-center gap-2 active:scale-[0.99] disabled:opacity-50"
          >
            {isLoading ? (
              <>
                <Loader2 className="w-4 h-4 animate-spin" />
                <span>{t.passengerLogin.loggingIn}</span>
              </>
            ) : (
              <>
                <span>{t.passengerLogin.enterButton}</span>
                <ArrowRight className="w-4 h-4" />
              </>
            )}
          </button>
        </form>
      </div>
    </div>
  )
}
