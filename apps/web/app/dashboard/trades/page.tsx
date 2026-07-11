'use client'

import { useEffect, useState } from 'react'
import { CandlestickChart, CheckCircle2 } from 'lucide-react'

import { apiRequest, errorMessage, formatDate, formatNumber } from '../../components/api'
import { EmptyState } from '../../components/empty-state'
import { PageHeader } from '../../components/page-header'
import { StatusBadge } from '../../components/status-badge'

type Trade = {
  id: number
  symbol: string
  trade_type: string
  entry_price: number
  entry_time: string
  exit_price?: number | null
  exit_time?: string | null
  stop_loss: number
  take_profit?: number | null
  volume: number
  profit_loss?: number | null
  status: string
  mode: string
  broker?: string | null
  broker_order_id?: string | null
  execution_status?: string | null
}

export default function TradesPage() {
  const [trades, setTrades] = useState<Trade[]>([])
  const [loading, setLoading] = useState(true)
  const [closingId, setClosingId] = useState<number | null>(null)
  const [exitPrice, setExitPrice] = useState('')
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')

  const loadTrades = async () => {
    setLoading(true)
    try { setTrades(await apiRequest<Trade[]>('/trades')) } catch (requestError) { setError(errorMessage(requestError)) } finally { setLoading(false) }
  }

  useEffect(() => { void loadTrades() }, [])

  const closeTrade = async (tradeId: number) => {
    setError('')
    setMessage('')
    try {
      const trade = await apiRequest<Trade>(`/trades/${tradeId}/close?exit_price=${encodeURIComponent(exitPrice)}`, { method: 'POST' })
      setTrades((current) => current.map((item) => item.id === tradeId ? trade : item))
      setClosingId(null)
      setExitPrice('')
      setMessage('Paper trade closed and P/L recorded.')
    } catch (requestError) { setError(errorMessage(requestError)) }
  }

  const openTrades = trades.filter((trade) => trade.status === 'open')
  const closedTrades = trades.filter((trade) => trade.status === 'closed')
  const totalPnl = closedTrades.reduce((total, trade) => total + (trade.profit_loss || 0), 0)

  return (
    <>
      <PageHeader eyebrow="Execution ledger" title="Paper trades" description="Review simulated fills and close open paper positions with the observed exit price." />
      {(error || message) && <div className={`mb-5 rounded-md border px-4 py-3 text-sm ${error ? 'border-red-200 bg-red-50 text-red-700' : 'border-emerald-200 bg-emerald-50 text-emerald-700'}`}>{error || message}</div>}
      <section className="grid gap-4 sm:grid-cols-3"><div className="card"><p className="text-xs font-semibold uppercase tracking-[0.06em] text-slate-500">Open positions</p><p className="mt-2 text-3xl font-bold text-slate-950">{loading ? '—' : openTrades.length}</p></div><div className="card"><p className="text-xs font-semibold uppercase tracking-[0.06em] text-slate-500">Closed positions</p><p className="mt-2 text-3xl font-bold text-slate-950">{loading ? '—' : closedTrades.length}</p></div><div className="card"><p className="text-xs font-semibold uppercase tracking-[0.06em] text-slate-500">Recorded P/L</p><p className={`mt-2 text-3xl font-bold ${totalPnl < 0 ? 'text-red-700' : 'text-slate-950'}`}>{loading ? '—' : formatNumber(totalPnl)}</p></div></section>
      <section className="card mt-6 overflow-hidden p-0"><div className="flex flex-col justify-between gap-2 border-b border-slate-200 px-5 py-4 sm:flex-row sm:items-center"><div><h2 className="text-sm font-semibold text-slate-900">Trade ledger</h2><p className="mt-1 text-xs text-slate-500">Only paper-engine fills appear here.</p></div><span className="rounded-md border border-blue-200 bg-blue-50 px-2.5 py-1 text-xs font-semibold text-[#1d4ed8]">Demo mode</span></div>{loading ? <div className="p-8 text-sm text-slate-500">Loading paper trades…</div> : trades.length ? <div className="overflow-x-auto"><table className="w-full min-w-[980px] text-left text-sm"><thead className="bg-slate-50 text-xs font-semibold uppercase tracking-[0.05em] text-slate-500"><tr><th className="px-5 py-3">Trade</th><th className="px-5 py-3">Entry / target</th><th className="px-5 py-3">Volume</th><th className="px-5 py-3">Status</th><th className="px-5 py-3">P/L</th><th className="px-5 py-3">Action</th></tr></thead><tbody className="divide-y divide-slate-100">{trades.map((trade) => <tr key={trade.id}><td className="px-5 py-4"><p className="font-semibold text-slate-900">{trade.symbol} <span className={`text-xs uppercase ${trade.trade_type === 'buy' ? 'text-emerald-700' : 'text-red-700'}`}>{trade.trade_type}</span></p><p className="mt-1 text-xs text-slate-500">{formatDate(trade.entry_time)} · {trade.broker || 'paper'}</p></td><td className="px-5 py-4"><p className="font-semibold text-slate-900">{formatNumber(trade.entry_price)}</p><p className="mt-1 text-xs text-slate-500">SL {formatNumber(trade.stop_loss)} · TP {trade.take_profit ? formatNumber(trade.take_profit) : '—'}</p></td><td className="px-5 py-4 text-slate-700">{formatNumber(trade.volume)}</td><td className="px-5 py-4"><StatusBadge value={trade.status} /></td><td className={`px-5 py-4 font-semibold ${trade.profit_loss && trade.profit_loss < 0 ? 'text-red-700' : 'text-emerald-700'}`}>{trade.profit_loss === null || trade.profit_loss === undefined ? '—' : formatNumber(trade.profit_loss)}</td><td className="px-5 py-4">{trade.status === 'open' ? closingId === trade.id ? <div className="flex items-center gap-2"><input aria-label={`Exit price for ${trade.symbol}`} type="number" step="any" className="input-base h-9 w-28" value={exitPrice} onChange={(event) => setExitPrice(event.target.value)} /><button type="button" className="btn-primary min-h-9 px-3" disabled={!exitPrice} onClick={() => void closeTrade(trade.id)}><CheckCircle2 size={15} aria-hidden="true" />Close</button></div> : <button type="button" className="btn-secondary min-h-9 px-3" onClick={() => { setClosingId(trade.id); setExitPrice('') }}>Close trade</button> : <span className="text-xs text-slate-400">{trade.exit_price ? `Exit ${formatNumber(trade.exit_price)}` : 'Closed'}</span>}</td></tr>)}</tbody></table></div> : <EmptyState icon={CandlestickChart} title="No paper trades" description="Approve and evaluate a signal before creating its simulated trade record." />}</section>
    </>
  )
}
