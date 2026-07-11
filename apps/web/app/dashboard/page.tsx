'use client'

import Link from 'next/link'
import { useEffect, useState } from 'react'
import { ArrowRight, CircleDollarSign, Radio, ShieldCheck, Sparkles } from 'lucide-react'

import { apiRequest, errorMessage, formatDate, formatNumber } from '../components/api'
import { EmptyState } from '../components/empty-state'
import { PageHeader } from '../components/page-header'
import { StatusBadge } from '../components/status-badge'

type User = {
  default_risk_percent: number
  max_daily_loss_percent: number
  max_open_trades: number
}

type Signal = {
  id: number
  symbol: string
  signal_type: string
  confidence: number
  status: string
  created_at: string
}

type Trade = {
  id: number
  symbol: string
  trade_type: string
  entry_price: number
  volume: number
  status: string
  broker?: string | null
  created_at: string
}

type BrokerAccount = {
  id: number
  balance: number
  is_active: boolean
}

export default function DashboardPage() {
  const [user, setUser] = useState<User | null>(null)
  const [signals, setSignals] = useState<Signal[]>([])
  const [trades, setTrades] = useState<Trade[]>([])
  const [accounts, setAccounts] = useState<BrokerAccount[]>([])
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    Promise.all([
      apiRequest<User>('/auth/me'),
      apiRequest<Signal[]>('/signals'),
      apiRequest<Trade[]>('/trades'),
      apiRequest<BrokerAccount[]>('/broker-accounts'),
    ])
      .then(([currentUser, currentSignals, currentTrades, currentAccounts]) => {
        setUser(currentUser)
        setSignals(currentSignals)
        setTrades(currentTrades)
        setAccounts(currentAccounts)
      })
      .catch((requestError) => setError(errorMessage(requestError)))
      .finally(() => setLoading(false))
  }, [])

  const activeSignals = signals.filter((signal) => ['pending', 'approved'].includes(signal.status)).length
  const openTrades = trades.filter((trade) => trade.status === 'open').length
  const demoBalance = accounts.filter((account) => account.is_active).reduce((total, account) => total + account.balance, 0)

  return (
    <>
      <PageHeader
        eyebrow="Trading operations"
        title="Workspace overview"
        description="Review paper-trading readiness, current signals, and your risk limits in one place."
        actions={<Link href="/dashboard/signals" className="btn-primary">Review signals <ArrowRight size={16} aria-hidden="true" /></Link>}
      />

      {error && <div className="mb-5 rounded-md border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">{error}</div>}

      <section className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4" aria-label="Workspace summary">
        <div className="card">
          <p className="text-xs font-semibold uppercase tracking-[0.06em] text-slate-500">Open paper trades</p>
          <p className="mt-2 text-3xl font-bold text-slate-950">{loading ? '—' : openTrades}</p>
          <p className="mt-2 text-xs text-slate-500">Limit: {user?.max_open_trades ?? '—'} concurrent trades</p>
        </div>
        <div className="card">
          <p className="text-xs font-semibold uppercase tracking-[0.06em] text-slate-500">Signals in review</p>
          <p className="mt-2 text-3xl font-bold text-slate-950">{loading ? '—' : activeSignals}</p>
          <p className="mt-2 text-xs text-slate-500">Approved signals can be checked for paper execution</p>
        </div>
        <div className="card">
          <p className="text-xs font-semibold uppercase tracking-[0.06em] text-slate-500">Demo balance</p>
          <p className="mt-2 text-3xl font-bold text-slate-950">{loading ? '—' : demoBalance ? `$${formatNumber(demoBalance)}` : 'Not set'}</p>
          <p className="mt-2 text-xs text-slate-500">From active demo account records</p>
        </div>
        <div className="card">
          <p className="text-xs font-semibold uppercase tracking-[0.06em] text-slate-500">Risk per trade</p>
          <p className="mt-2 text-3xl font-bold text-slate-950">{loading ? '—' : `${user?.default_risk_percent ?? 0}%`}</p>
          <p className="mt-2 text-xs text-slate-500">Daily loss limit: {user?.max_daily_loss_percent ?? 0}%</p>
        </div>
      </section>

      <section className="mt-6 grid gap-6 xl:grid-cols-[minmax(0,1.5fr)_minmax(280px,0.8fr)]">
        <div className="card overflow-hidden p-0">
          <div className="flex items-center justify-between border-b border-slate-200 px-5 py-4">
            <div>
              <h2 className="text-sm font-semibold text-slate-900">Recent signals</h2>
              <p className="mt-1 text-xs text-slate-500">Only approved signals may move to paper execution.</p>
            </div>
            <Link href="/dashboard/signals" className="text-sm font-semibold text-[#2563eb] hover:text-[#1d4ed8]">Open signals</Link>
          </div>
          {signals.length ? (
            <div className="overflow-x-auto">
              <table className="w-full min-w-[560px] text-left text-sm">
                <thead className="bg-slate-50 text-xs font-semibold uppercase tracking-[0.05em] text-slate-500">
                  <tr><th className="px-5 py-3">Symbol</th><th className="px-5 py-3">Direction</th><th className="px-5 py-3">Confidence</th><th className="px-5 py-3">Status</th><th className="px-5 py-3">Created</th></tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {signals.slice(0, 6).map((signal) => (
                    <tr key={signal.id} className="text-slate-700">
                      <td className="px-5 py-3.5 font-semibold text-slate-900">{signal.symbol}</td>
                      <td className="px-5 py-3.5 capitalize">{signal.signal_type}</td>
                      <td className="px-5 py-3.5">{signal.confidence}%</td>
                      <td className="px-5 py-3.5"><StatusBadge value={signal.status} /></td>
                      <td className="px-5 py-3.5 text-slate-500">{formatDate(signal.created_at)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <EmptyState icon={Sparkles} title="No signals yet" description="Create a signal with a defined entry, stop, target, and confidence score to begin paper validation." action={<Link href="/dashboard/signals" className="btn-secondary">Create signal</Link>} />
          )}
        </div>

        <aside className="card">
          <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-blue-50 text-[#2563eb]"><ShieldCheck size={20} aria-hidden="true" /></div>
          <h2 className="mt-4 text-base font-semibold text-slate-900">Execution protection</h2>
          <dl className="mt-4 space-y-3 text-sm">
            <div className="flex justify-between gap-4 border-b border-slate-100 pb-3"><dt className="text-slate-500">Mode</dt><dd className="font-semibold text-[#1d4ed8]">Paper only</dd></div>
            <div className="flex justify-between gap-4 border-b border-slate-100 pb-3"><dt className="text-slate-500">Minimum confidence</dt><dd className="font-semibold text-slate-900">70%</dd></div>
            <div className="flex justify-between gap-4 border-b border-slate-100 pb-3"><dt className="text-slate-500">Minimum reward:risk</dt><dd className="font-semibold text-slate-900">1.5:1</dd></div>
            <div className="flex justify-between gap-4"><dt className="text-slate-500">Broker connection</dt><dd className="font-semibold text-slate-900">Locked</dd></div>
          </dl>
          <Link href="/dashboard/risk" className="btn-secondary mt-5 w-full">Review risk controls</Link>
        </aside>
      </section>

      <section className="mt-6 grid gap-4 md:grid-cols-3">
        <Link href="/dashboard/signals" className="card group transition-colors hover:border-blue-300">
          <Radio size={20} className="text-[#2563eb]" aria-hidden="true" /><h2 className="mt-3 text-sm font-semibold text-slate-900">Manage signals</h2><p className="mt-1 text-sm leading-6 text-slate-500">Review entry conditions before simulated execution.</p>
        </Link>
        <Link href="/dashboard/trades" className="card group transition-colors hover:border-blue-300">
          <CircleDollarSign size={20} className="text-[#2563eb]" aria-hidden="true" /><h2 className="mt-3 text-sm font-semibold text-slate-900">Paper-trade ledger</h2><p className="mt-1 text-sm leading-6 text-slate-500">Track fills, open positions, and closed results.</p>
        </Link>
        <Link href="/dashboard/broker-accounts" className="card group transition-colors hover:border-blue-300">
          <ShieldCheck size={20} className="text-[#2563eb]" aria-hidden="true" /><h2 className="mt-3 text-sm font-semibold text-slate-900">Demo accounts</h2><p className="mt-1 text-sm leading-6 text-slate-500">Keep demo-account context separate from execution credentials.</p>
        </Link>
      </section>
    </>
  )
}
