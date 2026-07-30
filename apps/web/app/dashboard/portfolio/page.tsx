'use client'

import { useEffect, useState } from 'react'
import { Activity, BarChart3, Landmark, PieChart, RefreshCw, TrendingUp } from 'lucide-react'

import { apiRequest, errorMessage } from '../../components/api'
import { PageHeader } from '../../components/page-header'

type AccountRow = {
  id: number
  name: string
  broker: string
  account_id: string
  account_type: string
  balance: number
  currency: string
  connection_state?: string | null
  provider: string
  positions: number
  floating_pnl: number
  last_snapshot_at?: string | null
}

type ExposureRow = {
  symbol: string
  volume: number
  floating_pnl: number
  positions: number
}

type PortfolioSummary = {
  generated_at: string
  currency: string
  total_balance: number
  equity_estimate: number
  realized_pnl: number
  floating_pnl: number
  account_count: number
  open_trade_count: number
  live_position_count: number
  closed_trade_count: number
  win_rate: number
  accounts: AccountRow[]
  exposure_by_symbol: ExposureRow[]
}

function money(value: number, currency: string) {
  return `${currency} ${Number(value || 0).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
}

function signedTone(value: number) {
  if (value > 0) return 'text-emerald-700'
  if (value < 0) return 'text-red-700'
  return 'text-slate-700'
}

export default function PortfolioPage() {
  const [summary, setSummary] = useState<PortfolioSummary | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  const load = async () => {
    setError('')
    setLoading(true)
    try {
      setSummary(await apiRequest<PortfolioSummary>('/portfolio/summary'))
    } catch (requestError) {
      setError(errorMessage(requestError))
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    void load()
  }, [])

  return (
    <>
      <PageHeader
        eyebrow="Portfolio"
        title="Portfolio analytics"
        description="Track account equity, open MT5 exposure, realized P&L, and execution performance from connected accounts."
        action={
          <button type="button" onClick={() => void load()} className="btn-secondary px-3 py-2" title="Refresh portfolio" aria-label="Refresh portfolio">
            <RefreshCw size={16} />
          </button>
        }
      />

      {error && <div className="mb-5 rounded-md border border-red-200 bg-red-50 px-3 py-3 text-sm text-red-700">{error}</div>}
      {loading && <div className="flex h-56 items-center justify-center text-sm font-medium text-slate-500">Loading portfolio...</div>}

      {!loading && summary && (
        <div className="space-y-6">
          <section className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
            <div className="card"><div className="flex items-center gap-2 text-xs font-bold uppercase text-slate-500"><PieChart size={15} />Equity estimate</div><p className="mt-3 text-2xl font-bold text-slate-950">{money(summary.equity_estimate, summary.currency)}</p><p className="mt-1 text-xs text-slate-500">Balance plus live floating P&L</p></div>
            <div className="card"><div className="flex items-center gap-2 text-xs font-bold uppercase text-slate-500"><Landmark size={15} />Total balance</div><p className="mt-3 text-2xl font-bold text-slate-950">{money(summary.total_balance, summary.currency)}</p><p className="mt-1 text-xs text-slate-500">Across {summary.account_count} active account{summary.account_count === 1 ? '' : 's'}</p></div>
            <div className="card"><div className="flex items-center gap-2 text-xs font-bold uppercase text-slate-500"><Activity size={15} />Floating P&L</div><p className={`mt-3 text-2xl font-bold ${signedTone(summary.floating_pnl)}`}>{money(summary.floating_pnl, summary.currency)}</p><p className="mt-1 text-xs text-slate-500">From {summary.live_position_count} live MT5 position{summary.live_position_count === 1 ? '' : 's'}</p></div>
            <div className="card"><div className="flex items-center gap-2 text-xs font-bold uppercase text-slate-500"><TrendingUp size={15} />Closed win rate</div><p className="mt-3 text-2xl font-bold text-slate-950">{summary.win_rate.toFixed(1)}%</p><p className="mt-1 text-xs text-slate-500">{summary.closed_trade_count} closed trade{summary.closed_trade_count === 1 ? '' : 's'}</p></div>
          </section>

          <section className="grid gap-6 xl:grid-cols-[minmax(0,1.2fr)_minmax(340px,0.8fr)]">
            <div className="card overflow-hidden p-0">
              <div className="border-b border-slate-200 px-5 py-4"><h2 className="text-sm font-semibold text-slate-900">Connected accounts</h2><p className="mt-1 text-xs text-slate-500">Live bridge rows include the most recent EA snapshot when available.</p></div>
              {summary.accounts.length ? <div className="divide-y divide-slate-100">{summary.accounts.map((account) => <div key={account.id} className="grid gap-3 px-5 py-4 sm:grid-cols-[minmax(0,1fr)_auto]">
                <div><h3 className="text-sm font-semibold text-slate-950">{account.name}</h3><p className="mt-1 text-xs text-slate-500">{account.provider} - {account.account_type.toUpperCase()} - {account.account_id}</p></div>
                <div className="text-left sm:text-right"><p className="text-sm font-bold text-slate-950">{money(account.balance, account.currency)}</p><p className={`mt-1 text-xs font-semibold ${signedTone(account.floating_pnl)}`}>Floating {money(account.floating_pnl, account.currency)} - {account.positions} positions</p></div>
              </div>)}</div> : <div className="p-8 text-sm text-slate-500">No active connected accounts.</div>}
            </div>

            <div className="card overflow-hidden p-0">
              <div className="border-b border-slate-200 px-5 py-4"><h2 className="flex items-center gap-2 text-sm font-semibold text-slate-900"><BarChart3 size={16} />Symbol exposure</h2><p className="mt-1 text-xs text-slate-500">Aggregated from live MT5 positions.</p></div>
              {summary.exposure_by_symbol.length ? <div className="divide-y divide-slate-100">{summary.exposure_by_symbol.map((row) => <div key={row.symbol} className="flex items-center justify-between gap-3 px-5 py-4"><div><p className="text-sm font-bold text-slate-950">{row.symbol}</p><p className="text-xs text-slate-500">{row.positions} positions - {row.volume} lots</p></div><p className={`text-sm font-bold ${signedTone(row.floating_pnl)}`}>{money(row.floating_pnl, summary.currency)}</p></div>)}</div> : <div className="p-8 text-sm text-slate-500">No live position exposure from the MT5 bridge.</div>}
            </div>
          </section>
        </div>
      )}
    </>
  )
}