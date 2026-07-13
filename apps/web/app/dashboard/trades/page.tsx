'use client'

import { useEffect, useState } from 'react'
import { CandlestickChart, CheckCircle2, RefreshCw, Pencil, Scissors, ShieldCheck, X } from 'lucide-react'

import { apiRequest, errorMessage, formatDate, formatNumber } from '../../components/api'
import { EmptyState } from '../../components/empty-state'
import { PageHeader } from '../../components/page-header'
import { StatusBadge } from '../../components/status-badge'

type Trade = {
  id: number
  symbol: string
  broker_symbol?: string | null
  trade_type: string
  entry_price: number
  entry_time: string
  exit_price?: number | null
  exit_time?: string | null
  stop_loss: number
  take_profit?: number | null
  volume: number
  actual_volume?: number | null
  profit_loss?: number | null
  status: string
  mode: string
  execution_mode?: string | null
  broker?: string | null
  broker_order_id?: string | null
  broker_position_id?: string | null
  broker_deal_id?: string | null
  reconciliation_status?: string | null
  commission?: number | null
  swap?: number | null
}

export default function TradesPage() {
  const [trades, setTrades] = useState<Trade[]>([])
  const [loading, setLoading] = useState(true)
  const [closingId, setClosingId] = useState<number | null>(null)
  const [exitPrice, setExitPrice] = useState('')
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')

  // Edit SL/TP
  const [editingProtectionId, setEditingProtectionId] = useState<number | null>(null)
  const [editSl, setEditSl] = useState('')
  const [editTp, setEditTp] = useState('')
  const [protectionSaving, setProtectionSaving] = useState(false)

  // Partial Close
  const [partialCloseId, setPartialCloseId] = useState<number | null>(null)
  const [partialVolume, setPartialVolume] = useState('')
  const [partialClosing, setPartialClosing] = useState(false)

  // Reconcile
  const [reconciling, setReconciling] = useState(false)

  const loadTrades = async (showLoading = true) => {
    if (showLoading) setLoading(true)
    try {
      setTrades(await apiRequest<Trade[]>('/trades'))
    } catch (requestError) {
      setError(errorMessage(requestError))
    } finally {
      if (showLoading) setLoading(false)
    }
  }

  useEffect(() => {
    void loadTrades()
  }, [])

  const closeTrade = async (tradeId: number, isPaper: boolean) => {
    setError('')
    setMessage('')
    try {
      const url = isPaper
        ? `/trades/${tradeId}/close?exit_price=${encodeURIComponent(exitPrice)}`
        : `/trades/${tradeId}/close`
      
      const trade = await apiRequest<Trade>(url, { method: 'POST' })
      setTrades((current) => current.map((item) => item.id === tradeId ? trade : item))
      setClosingId(null)
      setExitPrice('')
      setMessage(isPaper ? 'Paper trade closed.' : 'MT5 broker position closed.')
      await loadTrades(false)
    } catch (requestError) {
      setError(errorMessage(requestError))
    }
  }

  const saveProtection = async (tradeId: number) => {
    setProtectionSaving(true)
    setError('')
    try {
      const body: any = {}
      if (editSl) body.stop_loss = parseFloat(editSl)
      if (editTp) body.take_profit = parseFloat(editTp)
      await apiRequest(`/trades/${tradeId}/protection`, {
        method: 'PATCH',
        body: JSON.stringify(body)
      })
      setMessage('Protection levels updated.')
      setEditingProtectionId(null)
      await loadTrades(false)
    } catch (e) {
      setError(errorMessage(e))
    } finally {
      setProtectionSaving(false)
    }
  }

  const doPartialClose = async (tradeId: number) => {
    if (!partialVolume) return
    setPartialClosing(true)
    setError('')
    try {
      await apiRequest(`/trades/${tradeId}/partial-close`, {
        method: 'POST',
        body: JSON.stringify({ volume: parseFloat(partialVolume) })
      })
      setMessage(`Partial close of ${partialVolume} lots executed.`)
      setPartialCloseId(null)
      setPartialVolume('')
      await loadTrades(false)
    } catch (e) {
      setError(errorMessage(e))
    } finally {
      setPartialClosing(false)
    }
  }

  const forceReconcile = async () => {
    // Reconcile the first trade's broker info — in production this would reconcile per-account
    setReconciling(true)
    setError('')
    try {
      // Try reconciling via the trades endpoint which should handle it
      await apiRequest('/trades/reconcile', { method: 'POST' })
      setMessage('Reconciliation complete. Refresh to see results.')
      await loadTrades(false)
    } catch (e) {
      // Fall back: try per broker-account endpoint
      try {
        const accounts = await apiRequest<{id: number}[]>('/broker-accounts')
        for (const a of accounts) {
          await apiRequest(`/broker-accounts/${a.id}/reconcile`, { method: 'POST' })
        }
        setMessage('Reconciliation complete across all accounts.')
        await loadTrades(false)
      } catch (e2) {
        setError(errorMessage(e2))
      }
    } finally {
      setReconciling(false)
    }
  }

  const openTrades = trades.filter((trade) => trade.status === 'open')
  const closedTrades = trades.filter((trade) => trade.status === 'closed')
  const totalPnl = closedTrades.reduce((total, trade) => total + (trade.profit_loss || 0), 0)

  const modeBadge = (mode?: string | null) => {
    if (mode === 'live') {
      return (
        <span className="rounded-full bg-[#fef2f2] border border-[#fca5a5] px-2 py-0.5 text-[10px] font-bold text-[#b91c1c]">
          LIVE MT5
        </span>
      )
    }
    if (mode === 'broker_demo') {
      return (
        <span className="rounded-full bg-[#eff6ff] border border-[#bfdbfe] px-2 py-0.5 text-[10px] font-bold text-[#1e40af]">
          DEMO MT5
        </span>
      )
    }
    return (
      <span className="rounded-full bg-slate-50 border border-slate-200 px-2 py-0.5 text-[10px] font-bold text-slate-600">
        PAPER
      </span>
    )
  }

  const reconBadge = (status?: string | null) => {
    if (!status || status === 'reconciled') {
      return <span className="text-[10px] text-emerald-600 font-semibold bg-emerald-50 px-1.5 py-0.5 rounded">Synced</span>
    }
    if (status === 'modified') {
      return <span className="text-[10px] text-amber-700 font-semibold bg-amber-50 px-1.5 py-0.5 rounded">Modified</span>
    }
    return <span className="text-[10px] text-red-600 font-semibold bg-red-50 px-1.5 py-0.5 rounded">{status}</span>
  }

  return (
    <>
      <PageHeader
        eyebrow="Execution ledger"
        title="Trades"
        description="Review execution history, reconcile states, and manage open positions on the connected MT5 accounts."
      />
      {(error || message) && (
        <div className={`mb-5 rounded-md border px-4 py-3 text-sm ${
          error ? 'border-red-200 bg-red-50 text-red-700' : 'border-emerald-200 bg-emerald-50 text-emerald-700'
        }`}>
          {error || message}
        </div>
      )}

      <div className="mb-4 flex justify-end gap-2">
        <button
          type="button"
          disabled={reconciling}
          onClick={() => void forceReconcile()}
          className="btn-secondary flex items-center gap-1.5 text-xs py-1.5 border-amber-200 text-amber-700 hover:bg-amber-50"
        >
          <ShieldCheck size={13} /> {reconciling ? 'Reconciling…' : 'Force Reconcile'}
        </button>
        <button
          type="button"
          onClick={() => void loadTrades(true)}
          className="btn-secondary flex items-center gap-1.5 text-xs py-1.5"
        >
          <RefreshCw size={13} /> Refresh Ledger
        </button>
      </div>

      <section className="grid gap-4 sm:grid-cols-3">
        <div className="card">
          <p className="text-xs font-semibold uppercase tracking-[0.06em] text-slate-500">Open positions</p>
          <p className="mt-2 text-3xl font-bold text-slate-950">{loading ? '—' : openTrades.length}</p>
        </div>
        <div className="card">
          <p className="text-xs font-semibold uppercase tracking-[0.06em] text-slate-500">Closed positions</p>
          <p className="mt-2 text-3xl font-bold text-slate-950">{loading ? '—' : closedTrades.length}</p>
        </div>
        <div className="card">
          <p className="text-xs font-semibold uppercase tracking-[0.06em] text-slate-500">Recorded P/L</p>
          <p className={`mt-2 text-3xl font-bold ${totalPnl < 0 ? 'text-[#b91c1c]' : 'text-slate-950'}`}>
            {loading ? '—' : (totalPnl >= 0 ? '+' : '') + formatNumber(totalPnl, 2)}
          </p>
        </div>
      </section>

      <section className="card mt-6 overflow-hidden p-0">
        <div className="flex flex-col justify-between gap-2 border-b border-slate-200 px-5 py-4 sm:flex-row sm:items-center">
          <div>
            <h2 className="text-sm font-semibold text-slate-900">Trade ledger</h2>
            <p className="mt-1 text-xs text-slate-500">Syncs open and closed trade metrics.</p>
          </div>
        </div>

        {loading ? (
          <div className="p-8 text-sm text-slate-500">Loading trades…</div>
        ) : trades.length ? (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[980px] text-left text-sm">
              <thead className="bg-slate-50 text-xs font-semibold uppercase tracking-[0.05em] text-slate-500">
                <tr>
                  <th className="px-5 py-3">Trade</th>
                  <th className="px-5 py-3">Account & Mode</th>
                  <th className="px-5 py-3">Entry / Target</th>
                  <th className="px-5 py-3">Volume (lots)</th>
                  <th className="px-5 py-3">Status / Sync</th>
                  <th className="px-5 py-3">Broker metrics</th>
                  <th className="px-5 py-3">P/L ($)</th>
                  <th className="px-5 py-3">Action</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {trades.map((trade) => {
                  const isPaper = trade.execution_mode === 'paper' || !trade.execution_mode
                  return (
                    <tr key={trade.id}>
                      <td className="px-5 py-4">
                        <p className="font-semibold text-slate-900">
                          {trade.symbol}{' '}
                          <span className={`text-xs uppercase ${trade.trade_type === 'buy' ? 'text-emerald-700' : 'text-red-700'}`}>
                            {trade.trade_type}
                          </span>
                        </p>
                        <p className="mt-1 text-[11px] text-slate-400">
                          ID: #{trade.id} · {formatDate(trade.entry_time)}
                        </p>
                      </td>
                      <td className="px-5 py-4">
                        <div className="flex flex-col gap-1">
                          {modeBadge(trade.execution_mode)}
                          {trade.broker && (
                            <span className="text-[11px] text-slate-500">
                              {trade.broker}
                            </span>
                          )}
                        </div>
                      </td>
                      <td className="px-5 py-4">
                        <p className="font-semibold text-slate-900 tabular-nums">
                          {formatNumber(trade.entry_price, 5)}
                        </p>
                        <p className="mt-1 text-[11px] text-slate-500 tabular-nums">
                          SL: {formatNumber(trade.stop_loss, 5)} · TP:{' '}
                          {trade.take_profit ? formatNumber(trade.take_profit, 5) : '—'}
                        </p>
                      </td>
                      <td className="px-5 py-4 text-slate-700 tabular-nums font-medium">
                        {trade.actual_volume ? trade.actual_volume.toFixed(2) : trade.volume.toFixed(2)}
                      </td>
                      <td className="px-5 py-4">
                        <div className="flex flex-col gap-1 items-start">
                          <StatusBadge value={trade.status} />
                          {!isPaper && reconBadge(trade.reconciliation_status)}
                        </div>
                      </td>
                      <td className="px-5 py-4 text-xs text-slate-500 space-y-0.5">
                        {!isPaper ? (
                          <>
                            <p>Pos ID: <span className="font-mono text-slate-800">{trade.broker_position_id || '—'}</span></p>
                            <p>Com: <span className="tabular-nums text-slate-800">${(trade.commission || 0).toFixed(2)}</span></p>
                            <p>Swap: <span className="tabular-nums text-slate-800">${(trade.swap || 0).toFixed(2)}</span></p>
                          </>
                        ) : (
                          <span className="text-slate-400">—</span>
                        )}
                      </td>
                      <td className={`px-5 py-4 font-bold text-base tabular-nums ${
                        trade.profit_loss && trade.profit_loss < 0 ? 'text-[#b91c1c]' : 'text-[#166534]'
                      }`}>
                        {trade.profit_loss === null || trade.profit_loss === undefined
                          ? '—'
                          : (trade.profit_loss >= 0 ? '+' : '') + formatNumber(trade.profit_loss, 2)}
                      </td>
                      <td className="px-5 py-4">
                        {trade.status === 'open' ? (
                          <div className="flex flex-col gap-1.5">
                            {/* Edit SL/TP */}
                            {editingProtectionId === trade.id ? (
                              <div className="flex flex-col gap-1.5 rounded-md border border-blue-200 bg-blue-50/50 p-2">
                                <div className="flex items-center justify-between">
                                  <span className="text-[10px] font-bold uppercase text-blue-700">Edit Protection</span>
                                  <button type="button" onClick={() => setEditingProtectionId(null)} className="text-slate-400 hover:text-slate-600"><X size={12} /></button>
                                </div>
                                <div className="grid grid-cols-2 gap-1.5">
                                  <label className="block">
                                    <span className="text-[10px] font-semibold text-red-600">SL</span>
                                    <input type="number" step="0.00001" className="input-base mt-0.5 h-7 w-full text-xs" value={editSl} onChange={(e) => setEditSl(e.target.value)} />
                                  </label>
                                  <label className="block">
                                    <span className="text-[10px] font-semibold text-[#15803d]">TP</span>
                                    <input type="number" step="0.00001" className="input-base mt-0.5 h-7 w-full text-xs" value={editTp} onChange={(e) => setEditTp(e.target.value)} />
                                  </label>
                                </div>
                                <button type="button" disabled={protectionSaving} onClick={() => void saveProtection(trade.id)} className="btn-primary h-7 text-[11px] w-full">
                                  {protectionSaving ? 'Saving…' : 'Update Levels'}
                                </button>
                              </div>
                            ) : (
                              <button
                                type="button"
                                className="btn-secondary flex items-center gap-1 min-h-7 px-2 text-[11px]"
                                onClick={() => {
                                  setEditingProtectionId(trade.id)
                                  setEditSl(String(trade.stop_loss))
                                  setEditTp(trade.take_profit ? String(trade.take_profit) : '')
                                }}
                              >
                                <Pencil size={11} /> Edit SL/TP
                              </button>
                            )}

                            {/* Partial Close */}
                            {!isPaper && (
                              partialCloseId === trade.id ? (
                                <div className="flex items-center gap-1.5 rounded-md border border-amber-200 bg-amber-50 p-2">
                                  <label className="flex-1">
                                    <span className="text-[10px] font-semibold text-amber-700">Vol</span>
                                    <input type="number" step="0.01" min="0.01" className="input-base mt-0.5 h-7 w-full text-xs" value={partialVolume} onChange={(e) => setPartialVolume(e.target.value)} />
                                  </label>
                                  <div className="flex gap-1 self-end">
                                    <button type="button" disabled={partialClosing || !partialVolume} onClick={() => void doPartialClose(trade.id)} className="btn-primary h-7 px-2 text-[11px]">
                                      {partialClosing ? '…' : 'Go'}
                                    </button>
                                    <button type="button" onClick={() => setPartialCloseId(null)} className="text-slate-400 hover:text-slate-600"><X size={12} /></button>
                                  </div>
                                </div>
                              ) : (
                                <button
                                  type="button"
                                  className="btn-secondary flex items-center gap-1 min-h-7 px-2 text-[11px] border-amber-200 text-amber-700 hover:bg-amber-50"
                                  onClick={() => { setPartialCloseId(trade.id); setPartialVolume('') }}
                                >
                                  <Scissors size={11} /> Partial Close
                                </button>
                              )
                            )}

                            {/* Full Close */}
                            {isPaper ? (
                              closingId === trade.id ? (
                                <div className="flex items-center gap-1.5">
                                  <input
                                    aria-label={`Exit price for ${trade.symbol}`}
                                    type="number"
                                    step="any"
                                    className="input-base h-7 w-24 text-xs"
                                    value={exitPrice}
                                    onChange={(event) => setExitPrice(event.target.value)}
                                  />
                                  <button type="button" className="btn-primary h-7 px-2 text-[11px]" disabled={!exitPrice} onClick={() => void closeTrade(trade.id, true)}>
                                    <CheckCircle2 size={12} /> Close
                                  </button>
                                </div>
                              ) : (
                                <button
                                  type="button"
                                  className="btn-secondary flex items-center gap-1 min-h-7 px-2 text-[11px]"
                                  onClick={() => { setClosingId(trade.id); setExitPrice('') }}
                                >
                                  Close Paper
                                </button>
                              )
                            ) : (
                              <button
                                type="button"
                                className="btn-secondary flex items-center gap-1 min-h-7 px-2 text-[11px] border-red-200 text-red-700 hover:bg-red-50"
                                onClick={() => {
                                  if (window.confirm('Close this position on your MT5 terminal?')) {
                                    void closeTrade(trade.id, false)
                                  }
                                }}
                              >
                                Close MT5
                              </button>
                            )}
                          </div>
                        ) : (
                          <span className="text-xs text-slate-400">
                            {trade.exit_price ? `Exit ${formatNumber(trade.exit_price, 5)}` : 'Closed'}
                          </span>
                        )}
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        ) : (
          <EmptyState
            icon={CandlestickChart}
            title="No trades"
            description="Run automatic scanner or manual trades to view records."
          />
        )}
      </section>
    </>
  )
}
