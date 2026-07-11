'use client'

import { useEffect, useState } from 'react'
import { Download, X } from 'lucide-react'

type BeforeInstallPromptEvent = Event & {
  prompt: () => Promise<void>
  userChoice: Promise<{ outcome: 'accepted' | 'dismissed' }>
}

const SNOOZE_KEY = 'install-prompt-snoozed-until'

export function InstallPrompt() {
  const [installEvent, setInstallEvent] = useState<BeforeInstallPromptEvent | null>(null)
  const [visible, setVisible] = useState(false)

  useEffect(() => {
    if ('serviceWorker' in navigator) {
      navigator.serviceWorker.register('/sw.js').catch(() => undefined)
    }

    const snoozedUntil = Number(window.localStorage.getItem(SNOOZE_KEY) || 0)
    if (snoozedUntil > Date.now()) return
    if (window.matchMedia('(display-mode: standalone)').matches) return

    const onPrompt = (event: Event) => {
      event.preventDefault()
      setInstallEvent(event as BeforeInstallPromptEvent)
      window.setTimeout(() => setVisible(true), 2500)
    }
    window.addEventListener('beforeinstallprompt', onPrompt)
    return () => window.removeEventListener('beforeinstallprompt', onPrompt)
  }, [])

  const install = async () => {
    if (!installEvent) return
    setVisible(false)
    await installEvent.prompt()
    const choice = await installEvent.userChoice
    if (choice.outcome === 'dismissed') snooze()
  }

  const snooze = () => {
    setVisible(false)
    window.localStorage.setItem(SNOOZE_KEY, String(Date.now() + 7 * 24 * 3600 * 1000))
  }

  if (!visible || !installEvent) return null

  return (
    <div className="fixed inset-x-4 bottom-4 z-50 sm:inset-x-auto sm:right-6 sm:w-96" role="dialog" aria-label="Install AroTrader">
      <div className="card flex items-start gap-3 p-4 shadow-xl">
        <img src="/logo.png" alt="" aria-hidden="true" className="h-11 w-11 shrink-0 rounded-lg" />
        <div className="min-w-0 flex-1">
          <p className="text-sm font-bold text-slate-950">Install AroTrader</p>
          <p className="mt-0.5 text-xs leading-5 text-slate-500">Get the app on your home screen — faster access, full screen, no browser bars.</p>
          <div className="mt-3 flex items-center gap-2">
            <button type="button" onClick={() => void install()} className="btn-primary min-h-8 px-3 py-1 text-xs">
              <Download size={14} aria-hidden="true" /> Install app
            </button>
            <button type="button" onClick={snooze} className="btn-secondary min-h-8 px-3 py-1 text-xs">Not now</button>
          </div>
        </div>
        <button type="button" onClick={snooze} className="icon-button h-8 w-8 shrink-0" title="Dismiss" aria-label="Dismiss install prompt">
          <X size={14} aria-hidden="true" />
        </button>
      </div>
    </div>
  )
}
