'use client'

import Link from 'next/link'
import { useEffect, useState } from 'react'
import {
  ArrowRight,
  BrainCircuit,
  CandlestickChart,
  FlaskConical,
  Radio,
  ShieldCheck,
  Blocks,
  Lock,
  CheckCircle2,
} from 'lucide-react'

const features = [
  {
    icon: BrainCircuit,
    title: 'AI market analysis',
    description: 'Gemini-powered analysis reads market structure, momentum and sentiment, then explains its reasoning in plain language.',
  },
  {
    icon: Radio,
    title: 'Trading signals',
    description: 'Actionable long and short setups with entry, stop-loss and take-profit levels — every signal includes its confidence score.',
  },
  {
    icon: Blocks,
    title: 'Strategy builder',
    description: 'Compose rule-based strategies from indicators and conditions without writing code, then validate them before they trade.',
  },
  {
    icon: FlaskConical,
    title: 'Backtesting',
    description: 'Replay strategies against historical data with profit factor, drawdown and win-rate metrics before risking a cent.',
  },
  {
    icon: CandlestickChart,
    title: 'Paper trading',
    description: 'A realistic demo account with live pricing lets you practice execution and test the AI with zero financial risk.',
  },
  {
    icon: ShieldCheck,
    title: 'Risk controls',
    description: 'Per-trade risk caps, daily and weekly loss limits, and maximum drawdown guards are enforced on every order.',
  },
]

const steps = [
  {
    title: 'Create your account',
    description: 'Sign up in under a minute. Every new account starts with a funded paper-trading balance.',
  },
  {
    title: 'Get AI-backed setups',
    description: 'Run AI analysis on your markets, receive signals, or build and backtest your own strategy.',
  },
  {
    title: 'Trade, review, improve',
    description: 'Execute in the demo workspace, journal the outcome, and let the metrics show what works.',
  },
]

const safeguards = [
  'Live trading is disabled by default — paper first, always',
  'Hard limits on risk per trade, daily loss and drawdown',
  'Broker credentials encrypted with AES-256 at rest',
]

export default function HomePage() {
  const [hasSession, setHasSession] = useState(false)

  useEffect(() => {
    setHasSession(Boolean(window.localStorage.getItem('access_token')))
  }, [])

  const primaryHref = hasSession ? '/dashboard' : '/register'
  const primaryLabel = hasSession ? 'Open dashboard' : 'Start paper trading'

  return (
    <main className="min-h-screen bg-[#f6f7f9]">
      {/* Navigation */}
      <header className="sticky top-0 z-40 border-b border-slate-200 bg-white/90 backdrop-blur">
        <nav className="mx-auto flex h-16 w-full max-w-6xl items-center justify-between px-4 sm:px-6" aria-label="Main">
          <Link href="/" className="flex items-center gap-3">
            <img src="/logo.png" alt="AroTrader logo" className="h-9 w-9" />
            <span>
              <span className="block text-sm font-bold leading-tight text-slate-950">AroTrader</span>
              <span className="block text-[11px] font-medium leading-tight text-slate-500">by AROFi</span>
            </span>
          </Link>
          <div className="hidden items-center gap-8 md:flex">
            <a href="#features" className="text-sm font-medium text-slate-600 transition-colors hover:text-slate-950">Features</a>
            <a href="#how-it-works" className="text-sm font-medium text-slate-600 transition-colors hover:text-slate-950">How it works</a>
            <a href="#security" className="text-sm font-medium text-slate-600 transition-colors hover:text-slate-950">Security</a>
          </div>
          <div className="flex items-center gap-3">
            {!hasSession && (
              <Link href="/login" className="text-sm font-semibold text-slate-700 transition-colors hover:text-slate-950">Sign in</Link>
            )}
            <Link href={primaryHref} className="btn-primary">
              {primaryLabel} <ArrowRight size={16} aria-hidden="true" />
            </Link>
          </div>
        </nav>
      </header>

      {/* Hero */}
      <section className="mx-auto w-full max-w-6xl px-4 pb-20 pt-16 sm:px-6 sm:pt-24">
        <div className="grid items-center gap-12 lg:grid-cols-2">
          <div>
            <p className="inline-flex items-center gap-2 rounded-full border border-blue-200 bg-blue-50 px-3 py-1 text-xs font-semibold text-[#1d4ed8]">
              <BrainCircuit size={14} aria-hidden="true" /> AI-powered trading intelligence
            </p>
            <h1 className="mt-5 text-4xl font-bold leading-tight tracking-tight text-slate-950 sm:text-5xl">
              Trade smarter with AI — without risking real money
            </h1>
            <p className="mt-5 max-w-xl text-lg leading-8 text-slate-600">
              AroTrader analyzes markets with AI, generates signals with clear entries and exits, and lets you prove every
              strategy in a realistic paper-trading workspace before a single real dollar moves.
            </p>
            <div className="mt-8 flex flex-wrap items-center gap-4">
              <Link href={primaryHref} className="btn-primary px-6 py-3 text-base">
                {primaryLabel} <ArrowRight size={18} aria-hidden="true" />
              </Link>
              <a href="#features" className="btn-secondary px-6 py-3 text-base">Explore features</a>
            </div>
            <ul className="mt-8 space-y-2">
              {safeguards.map((item) => (
                <li key={item} className="flex items-start gap-2 text-sm text-slate-600">
                  <CheckCircle2 size={16} className="mt-0.5 shrink-0 text-[#15803d]" aria-hidden="true" />
                  {item}
                </li>
              ))}
            </ul>
          </div>

          {/* Illustrative signal card */}
          <div className="relative mx-auto w-full max-w-md" aria-hidden="true">
            <div className="absolute -inset-6 rounded-3xl bg-gradient-to-tr from-blue-100 via-transparent to-blue-50" />
            <div className="card relative space-y-4 p-6">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <span className="flex h-8 w-8 items-center justify-center rounded-md bg-blue-50 text-[#2563eb]"><Radio size={16} /></span>
                  <span className="text-sm font-bold text-slate-950">EUR/USD · Long</span>
                </div>
                <span className="rounded-full bg-[#f0fdf4] px-2.5 py-1 text-xs font-semibold text-[#15803d]">Confidence 82%</span>
              </div>
              <div className="grid grid-cols-3 gap-3 text-center">
                <div className="rounded-md bg-slate-50 px-2 py-3">
                  <p className="text-[11px] font-semibold uppercase tracking-wide text-slate-500">Entry</p>
                  <p className="mt-1 text-sm font-bold tabular-nums text-slate-950">1.0842</p>
                </div>
                <div className="rounded-md bg-slate-50 px-2 py-3">
                  <p className="text-[11px] font-semibold uppercase tracking-wide text-slate-500">Stop</p>
                  <p className="mt-1 text-sm font-bold tabular-nums text-[#b91c1c]">1.0810</p>
                </div>
                <div className="rounded-md bg-slate-50 px-2 py-3">
                  <p className="text-[11px] font-semibold uppercase tracking-wide text-slate-500">Target</p>
                  <p className="mt-1 text-sm font-bold tabular-nums text-[#15803d]">1.0906</p>
                </div>
              </div>
              <div className="rounded-md border border-slate-200 bg-white p-3">
                <p className="text-xs font-semibold text-slate-700">AI rationale</p>
                <p className="mt-1 text-xs leading-5 text-slate-500">
                  Bullish momentum confirmed above the 50-EMA with higher lows on H4. Risk/reward 2.0 within daily loss limits.
                </p>
              </div>
              <div className="flex items-center justify-between border-t border-slate-100 pt-3 text-xs text-slate-500">
                <span className="inline-flex items-center gap-1.5"><ShieldCheck size={14} className="text-[#2563eb]" /> Risk checked</span>
                <span>Paper account · $10,000</span>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* Features */}
      <section id="features" className="border-t border-slate-200 bg-white py-20">
        <div className="mx-auto w-full max-w-6xl px-4 sm:px-6">
          <div className="max-w-2xl">
            <h2 className="text-3xl font-bold tracking-tight text-slate-950">Everything you need to trade with discipline</h2>
            <p className="mt-3 text-base leading-7 text-slate-600">
              From first analysis to journaled review — one workspace covers the full loop.
            </p>
          </div>
          <div className="mt-12 grid gap-5 sm:grid-cols-2 lg:grid-cols-3">
            {features.map(({ icon: Icon, title, description }) => (
              <div key={title} className="card p-6">
                <span className="flex h-11 w-11 items-center justify-center rounded-lg bg-blue-50 text-[#2563eb]">
                  <Icon size={22} aria-hidden="true" />
                </span>
                <h3 className="mt-4 text-base font-bold text-slate-950">{title}</h3>
                <p className="mt-2 text-sm leading-6 text-slate-600">{description}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* How it works */}
      <section id="how-it-works" className="py-20">
        <div className="mx-auto w-full max-w-6xl px-4 sm:px-6">
          <div className="max-w-2xl">
            <h2 className="text-3xl font-bold tracking-tight text-slate-950">Up and running in three steps</h2>
            <p className="mt-3 text-base leading-7 text-slate-600">No broker account or deposit required to start.</p>
          </div>
          <ol className="mt-12 grid gap-5 md:grid-cols-3">
            {steps.map((step, index) => (
              <li key={step.title} className="card p-6">
                <span className="flex h-9 w-9 items-center justify-center rounded-full bg-[#2563eb] text-sm font-bold text-white">{index + 1}</span>
                <h3 className="mt-4 text-base font-bold text-slate-950">{step.title}</h3>
                <p className="mt-2 text-sm leading-6 text-slate-600">{step.description}</p>
              </li>
            ))}
          </ol>
        </div>
      </section>

      {/* Security */}
      <section id="security" className="border-t border-slate-200 bg-white py-20">
        <div className="mx-auto w-full max-w-6xl px-4 sm:px-6">
          <div className="grid items-start gap-10 lg:grid-cols-2">
            <div>
              <span className="flex h-11 w-11 items-center justify-center rounded-lg bg-blue-50 text-[#2563eb]">
                <Lock size={22} aria-hidden="true" />
              </span>
              <h2 className="mt-4 text-3xl font-bold tracking-tight text-slate-950">Built safety-first</h2>
              <p className="mt-3 max-w-xl text-base leading-7 text-slate-600">
                Trading tools should protect you from your worst day, not amplify it. AroTrader enforces guardrails at the
                platform level — they are not optional settings you can forget to turn on.
              </p>
            </div>
            <ul className="space-y-4">
              {[
                ['Paper trading by default', 'Live execution stays off until you explicitly enable it — and it is off platform-wide today.'],
                ['Enforced risk limits', 'Max risk per trade, daily and weekly loss caps, and account drawdown guards block over-sized orders.'],
                ['Encrypted credentials', 'API keys and broker tokens are encrypted with AES-256; passwords are stored as bcrypt hashes.'],
                ['Full audit trail', 'Every signal, order and settings change is logged so you can always reconstruct what happened.'],
              ].map(([title, description]) => (
                <li key={title} className="flex gap-3">
                  <CheckCircle2 size={20} className="mt-0.5 shrink-0 text-[#15803d]" aria-hidden="true" />
                  <div>
                    <p className="text-sm font-bold text-slate-950">{title}</p>
                    <p className="mt-1 text-sm leading-6 text-slate-600">{description}</p>
                  </div>
                </li>
              ))}
            </ul>
          </div>
        </div>
      </section>

      {/* CTA */}
      <section className="py-20">
        <div className="mx-auto w-full max-w-6xl px-4 sm:px-6">
          <div className="rounded-2xl bg-[#2563eb] px-6 py-14 text-center sm:px-12">
            <h2 className="text-3xl font-bold tracking-tight text-white">Prove your edge before you pay for it</h2>
            <p className="mx-auto mt-3 max-w-xl text-base leading-7 text-blue-100">
              Open a free paper-trading account with a $10,000 demo balance and let the AI go to work.
            </p>
            <div className="mt-8 flex flex-wrap items-center justify-center gap-4">
              <Link
                href={primaryHref}
                className="inline-flex min-h-10 items-center justify-center gap-2 rounded-md bg-white px-6 py-3 text-base font-semibold text-[#1d4ed8] transition-colors hover:bg-blue-50"
              >
                {primaryLabel} <ArrowRight size={18} aria-hidden="true" />
              </Link>
              {!hasSession && (
                <Link href="/login" className="text-sm font-semibold text-blue-100 transition-colors hover:text-white">
                  Already have an account? Sign in
                </Link>
              )}
            </div>
          </div>
        </div>
      </section>

      {/* Footer */}
      <footer className="border-t border-slate-200 bg-white">
        <div className="mx-auto w-full max-w-6xl px-4 py-10 sm:px-6">
          <div className="flex flex-col items-start justify-between gap-6 sm:flex-row sm:items-center">
            <div className="flex items-center gap-3">
              <img src="/logo.png" alt="AroTrader logo" className="h-9 w-9" />
              <span>
                <span className="block text-sm font-bold leading-tight text-slate-950">AroTrader</span>
                <span className="block text-[11px] font-medium leading-tight text-slate-500">by AROFi</span>
              </span>
            </div>
            <div className="flex items-center gap-6 text-sm font-medium text-slate-600">
              <Link href="/login" className="transition-colors hover:text-slate-950">Sign in</Link>
              <Link href="/register" className="transition-colors hover:text-slate-950">Create account</Link>
            </div>
          </div>
          <p className="mt-8 max-w-3xl text-xs leading-5 text-slate-500">
            Trading involves substantial risk of loss and is not suitable for every investor. AroTrader provides analysis and
            simulated trading tools for educational purposes; nothing on this platform constitutes financial advice.
          </p>
          <p className="mt-3 text-xs text-slate-400">© {new Date().getFullYear()} AROFi. All rights reserved.</p>
        </div>
      </footer>
    </main>
  )
}
