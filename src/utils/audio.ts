let audioCtx: AudioContext | null = null
let soundEnabled = true

function getAudioContext(): AudioContext | null {
  if (typeof window === "undefined") return null
  if (!audioCtx) {
    const AudioContextClass =
      window.AudioContext ||
      (window as unknown as { webkitAudioContext: typeof AudioContext })
        .webkitAudioContext
    if (AudioContextClass) {
      audioCtx = new AudioContextClass()
    }
  }
  if (audioCtx && audioCtx.state === "suspended") {
    audioCtx.resume()
  }
  return audioCtx
}

export function toggleSound(enabled?: boolean): boolean {
  if (typeof enabled === "boolean") {
    soundEnabled = enabled
  } else {
    soundEnabled = !soundEnabled
  }
  return soundEnabled
}

export function isSoundEnabled(): boolean {
  return soundEnabled
}

export function playCabinChime() {
  if (!soundEnabled) return
  const ctx = getAudioContext()
  if (!ctx) return

  const now = ctx.currentTime
  const osc1 = ctx.createOscillator()
  const gain1 = ctx.createGain()
  osc1.type = "sine"
  osc1.frequency.setValueAtTime(659.25, now)
  gain1.gain.setValueAtTime(0.08, now)
  gain1.gain.exponentialRampToValueAtTime(0.001, now + 0.8)
  osc1.connect(gain1)
  gain1.connect(ctx.destination)
  osc1.start(now)
  osc1.stop(now + 0.85)

  const osc2 = ctx.createOscillator()
  const gain2 = ctx.createGain()
  osc2.type = "sine"
  osc2.frequency.setValueAtTime(830.61, now + 0.22)
  gain2.gain.setValueAtTime(0.09, now + 0.22)
  gain2.gain.exponentialRampToValueAtTime(0.001, now + 1.2)
  osc2.connect(gain2)
  gain2.connect(ctx.destination)
  osc2.start(now + 0.22)
  osc2.stop(now + 1.25)
}

export function playServerAckChime() {
  if (!soundEnabled) return
  const ctx = getAudioContext()
  if (!ctx) return

  const now = ctx.currentTime
  const notes = [554.37, 659.25, 830.61]

  notes.forEach((freq, index) => {
    const osc = ctx.createOscillator()
    const gain = ctx.createGain()
    const startTime = now + index * 0.12
    osc.type = "sine"
    osc.frequency.setValueAtTime(freq, startTime)
    gain.gain.setValueAtTime(0.06, startTime)
    gain.gain.exponentialRampToValueAtTime(0.0001, startTime + 0.7)
    osc.connect(gain)
    gain.connect(ctx.destination)
    osc.start(startTime)
    osc.stop(startTime + 0.75)
  })
}

export function playSoftTap() {
  if (!soundEnabled) return
  const ctx = getAudioContext()
  if (!ctx) return

  const now = ctx.currentTime
  const osc = ctx.createOscillator()
  const gain = ctx.createGain()
  osc.type = "triangle"
  osc.frequency.setValueAtTime(440, now)
  gain.gain.setValueAtTime(0.03, now)
  gain.gain.exponentialRampToValueAtTime(0.001, now + 0.1)
  osc.connect(gain)
  gain.connect(ctx.destination)
  osc.start(now)
  osc.stop(now + 0.1)
}
