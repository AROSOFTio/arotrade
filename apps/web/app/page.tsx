'use client'

import Link from 'next/link'
import { useEffect, useState } from 'react'
import { ArrowRight, Bot, BrainCircuit, Cable, CandlestickChart, CheckCircle2, LineChart, ShieldCheck } from 'lucide-react'

import { InstallPrompt } from './components/install-prompt'
import { ThemeToggle } from './components/theme-toggle'

const features = [
  ['Direct MT5 bridge', 'Stream live candles, quotes, account telemetry, positions, orders, and history from the AroPilot Expert Advisor.', Cable],
  ['Deterministic analysis', 'Generate objective structure, trend, momentum, volatility, support, resistance, and risk context before AI explains it.', LineChart],
  ['Multi-AI consensus', 'Compare enabled providers on the same MT5 snapshot and see agreement, confidence, and conflicting opinions.', BrainCircuit],
  ['MT5 annotations', 'Send entries, stops, targets, zones, and signal arrows back to the MetaTrader chart.', CandlestickChart],
  ['Risk controls', 'Guard every setup with max risk, daily loss, open-trade limits, and explicit auto-trading confirmation.', ShieldCheck],
  ['Trading mentor chat', 'Ask follow-up questions about live market analysis, signals, strategy results, journal entries, and risk.', Bot],
] as const

const steps = [
  'Create a direct MT5 bridge in AroPilot.',
  'Install and attach the AroPilot Expert Advisor in MetaTrader 5.',
  'Analyze live MT5 data with deterministic TA, AI comparison, and consensus.',
]

export default function HomePage() {
  const [hasSession, setHasSession] = useState(false)

  useEffect(() => {
    setHasSession(Boolean(window.localStorage.getItem('access_token')))
  }, [])

  const primaryHref = hasSession ? '/dashboard' : '/register'
  const primaryLabel = hasSession ? 'Open dashboard' : 'Connect MT5'

  return (
    <main className="min-h-screen bg-[#f6f7f9]">
      <InstallPrompt />
      <header className="sticky top-0 z-40 border-b border-slate-200 bg-white/90 backdrop-blur">
        <nav className="mx-auto flex h-16 w-full max-w-6xl items-center justify-between px-4 sm:px-6" aria-label="Main">
          <Link href="/" className="flex items-center gap-3">
            <img src="/logo.png" alt="AroPilot logo" className="h-9 w-9" />
            <span>
              <span className="block text-sm font-bold leading-tight text-slate-950">AroPilot</span>
              <span className="block text-[11px] font-medium leading-tight text-slate-500">by AROFi</span>
            </span>
          </Link>
          <div className="hidden items-center gap-8 md:flex">
            <a href="#features" className="text-sm font-medium text-slate-600 hover:text-slate-950">Features</a>
            <a href="#workflow" className="text-sm font-medium text-slate-600 hover:text-slate-950">Workflow</a>
            <a href="#security" className="text-sm font-medium text-slate-600 hover:text-slate-950">Security</a>
          </div>
          <div className="flex items-center gap-2 sm:gap-3">
            <ThemeToggle />
            {!hasSession && <Link href="/login" className="hidden text-sm font-semibold text-slate-700 hover:text-slate-950 sm:block">Sign in</Link>}
            <Link href={primaryHref} className="btn-primary">{primaryLabel} <ArrowRight size={16} aria-hidden="true" /></Link>
          </div>
        </nav>
      </header>

      <section className="mx-auto w-full max-w-6xl px-4 pb-16 pt-14 sm:px-6 sm:pt-20">
        <div className="grid items-center gap-10 lg:grid-cols-[1.05fr_0.95fr]">
          <div>
            <p className="inline-flex items-center gap-2 rounded-full border border-emerald-200 bg-emerald-50 px-3 py-1 text-xs font-semibold text-emerald-700">
              <Cable size={14} aria-hidden="true" /> Direct MetaTrader 5 intelligence
            </p>
            <h1 className="mt-5 text-4xl font-bold leading-tight tracking-tight text-slate-950 sm:text-5xl">
              AroPilot turns live MT5 data into multi-AI trading intelligence.
            </h1>
            <p className="mt-5 max-w-xl text-lg leading-8 text-slate-600">
              Connect the AroPilot Expert Advisor, stream real market data, run deterministic analysis, compare AI providers, and draw actionable levels back on your MT5 chart.
            </p>
            <div className="mt-8 flex flex-wrap items-center gap-4">
              <Link href={primaryHref} className="btn-primary px-6 py-3 text-base">{primaryLabel} <ArrowRight size={18} aria-hidden="true" /></Link>
              <a href="#features" className="btn-secondary px-6 py-3 text-base">Explore features</a>
            </div>
            <ul className="mt-8 space-y-2">
              {['Live MT5 candles and account telemetry', 'Provider fallback without crashes', 'Risk controls before any execution command'].map((item) => (
                <li key={item} className="flex items-start gap-2 text-sm text-slate-600"><CheckCircle2 size={16} className="mt-0.5 shrink-0 text-[#15803d]" aria-hidden="true" />{item}</li>
              ))}
            </ul>
          </div>

          <div className="card p-6" aria-label="AroPilot terminal preview">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-xs font-bold uppercase text-slate-500">MT5 bridge</p>
                <h2 className="mt-1 text-xl font-bold text-slate-950">XAUUSD H1</h2>
              </div>
              <span className="rounded-full bg-[#f0fdf4] px-3 py-1 text-xs font-semibold text-[#15803d]">Live stream</span>
            </div>
            <div className="mt-5 grid grid-cols-3 gap-3 text-center">
              <div className="rounded-md bg-slate-50 px-2 py-3"><p className="text-[11px] font-semibold uppercase text-slate-500">Consensus</p><p className="mt-1 text-sm font-bold text-slate-950">BUY 78%</p></div>
              <div className="rounded-md bg-slate-50 px-2 py-3"><p className="text-[11px] font-semibold uppercase text-slate-500">Risk</p><p className="mt-1 text-sm font-bold text-slate-950">0.5%</p></div>
              <div className="rounded-md bg-slate-50 px-2 py-3"><p className="text-[11px] font-semibold uppercase text-slate-500">RR</p><p className="mt-1 text-sm font-bold text-slate-950">2.1:1</p></div>
            </div>
            <div className="mt-4 rounded-md border border-slate-200 bg-white p-3 text-sm leading-6 text-slate-600">
              Deterministic structure is bullish above support. Providers agree on continuation while one model warns about volatility near resistance.
            </div>
          </div>
        </div>
      </section>

      <section id="features" className="border-t border-slate-200 bg-white py-16">
        <div className="mx-auto w-full max-w-6xl px-4 sm:px-6">
          <h2 className="text-3xl font-bold tracking-tight text-slate-950">Built around the MT5 terminal</h2>
          <div className="mt-10 grid gap-5 sm:grid-cols-2 lg:grid-cols-3">
            {features.map(([title, description, Icon]) => (
              <div key={title} className="card p-6">
                <span className="flex h-11 w-11 items-center justify-center rounded-lg bg-emerald-50 text-[#16a34a]"><Icon size={22} aria-hidden="true" /></span>
                <h3 className="mt-4 text-base font-bold text-slate-950">{title}</h3>
                <p className="mt-2 text-sm leading-6 text-slate-600">{description}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      <section id="workflow" className="py-16">
        <div className="mx-auto w-full max-w-6xl px-4 sm:px-6">
          <h2 className="text-3xl font-bold tracking-tight text-slate-950">Production workflow</h2>
          <ol className="mt-10 grid gap-5 md:grid-cols-3">
            {steps.map((step, index) => (
              <li key={step} className="card p-6"><span className="flex h-9 w-9 items-center justify-center rounded-full bg-[#16a34a] text-sm font-bold text-white">{index + 1}</span><p className="mt-4 text-sm leading-6 text-slate-700">{step}</p></li>
            ))}
          </ol>
        </div>
      </section>

      <section id="security" className="border-t border-slate-200 bg-white py-16">
        <div className="mx-auto w-full max-w-6xl px-4 sm:px-6">
          <h2 className="text-3xl font-bold tracking-tight text-slate-950">Risk-first by design</h2>
          <p className="mt-3 max-w-2xl text-base leading-7 text-slate-600">Auto trading requires explicit user enablement, backend permission, and local EA risk checks. Analysis and chart annotations continue even when execution is disabled.</p>
        </div>
      </section>

      <footer className="border-t border-slate-200 bg-white">
        <div className="mx-auto w-full max-w-6xl px-4 py-8 text-xs leading-5 text-slate-500 sm:px-6">
          <p>Trading involves substantial risk of loss. AroPilot provides trading intelligence and risk tooling; it does not provide financial advice or guarantee outcomes.</p>
          <p className="mt-3">(c) {new Date().getFullYear()} AROFi. All rights reserved.</p>
        </div>
      </footer>
    </main>
  )
}