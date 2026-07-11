'use client'

import { useEffect, useState } from 'react'
import { Plus, Trash2, Workflow } from 'lucide-react'

import { apiRequest, errorMessage, formatDate } from '../../components/api'
import { EmptyState } from '../../components/empty-state'
import { PageHeader } from '../../components/page-header'

type Strategy = {
  id: number
  name: string
  description?: string | null
  risk_per_trade: number
  max_open_trades: number
  health_score: number
  is_active: boolean
  created_at: string
}

type StrategyForm = {
  name: string
  description: string
  trend: string
  momentum: string
  volume: string
  smartMoney: string
  riskPerTrade: string
  maxDailyLoss: string
  maxOpenTrades: string
}

const initialForm: StrategyForm = {
  name: '',
  description: '',
  trend: '',
  momentum: '',
  volume: '',
  smartMoney: '',
  riskPerTrade: '1',
  maxDailyLoss: '3',
  maxOpenTrades: '1',
}

const splitRules = (value: string) => value.split(',').map((item) => item.trim()).filter(Boolean)

export default function StrategyBuilderPage() {
  const [strategies, setStrategies] = useState<Strategy[]>([])
  const [form, setForm] = useState<StrategyForm>(initialForm)
  const [loading, setLoading] = useState(true)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')

  const loadStrategies = async () => {
    setLoading(true)
    try {
      setStrategies(await apiRequest<Strategy[]>('/strategies'))
    } catch (requestError) {
      setError(errorMessage(requestError))
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { void loadStrategies() }, [])

  const updateForm = (field: keyof StrategyForm, value: string) => setForm((current) => ({ ...current, [field]: value }))

  const createStrategy = async (event: React.FormEvent) => {
    event.preventDefault()
    setError('')
    setMessage('')
    setSubmitting(true)
    try {
      const created = await apiRequest<Strategy>('/strategies', {
        method: 'POST',
        body: JSON.stringify({
          name: form.name,
          description: form.description || null,
          trend_indicators: splitRules(form.trend),
          momentum_indicators: splitRules(form.momentum),
          volume_indicators: splitRules(form.volume),
          smart_money: splitRules(form.smartMoney),
          risk_per_trade: Number(form.riskPerTrade),
          max_daily_loss: form.maxDailyLoss ? Number(form.maxDailyLoss) : null,
          max_open_trades: Number(form.maxOpenTrades),
          allow_martingale: false,
        }),
      })
      setStrategies((current) => [created, ...current])
      setForm(initialForm)
      setMessage('Strategy saved.')
    } catch (requestError) {
      setError(errorMessage(requestError))
    } finally {
      setSubmitting(false)
    }
  }

  const deleteStrategy = async (id: number) => {
    setError('')
    try {
      await apiRequest(`/strategies/${id}`, { method: 'DELETE' })
      setStrategies((current) => current.filter((strategy) => strategy.id !== id))
      setMessage('Strategy removed.')
    } catch (requestError) {
      setError(errorMessage(requestError))
    }
  }

  return (
    <>
      <PageHeader eyebrow="Rules library" title="Strategy builder" description="Store named rule sets and position limits. Backtesting remains unavailable until verified market data is connected." />
      {(error || message) && <div className={`mb-5 rounded-md border px-4 py-3 text-sm ${error ? 'border-red-200 bg-red-50 text-red-700' : 'border-emerald-200 bg-emerald-50 text-emerald-700'}`}>{error || message}</div>}
      <section className="grid gap-6 xl:grid-cols-[minmax(360px,0.85fr)_minmax(0,1.15fr)]">
        <form onSubmit={createStrategy} className="card h-fit">
          <div className="flex items-center gap-2"><span className="flex h-9 w-9 items-center justify-center rounded-lg bg-blue-50 text-[#2563eb]"><Plus size={18} aria-hidden="true" /></span><div><h2 className="text-sm font-semibold text-slate-900">New strategy</h2><p className="mt-0.5 text-xs text-slate-500">Rules are stored as documented inputs, not auto-executed.</p></div></div>
          <div className="mt-5"><label htmlFor="strategy-name" className="label">Name</label><input id="strategy-name" className="input-base" value={form.name} onChange={(event) => updateForm('name', event.target.value)} required /></div>
          <div className="mt-4"><label htmlFor="strategy-description" className="label">Description</label><textarea id="strategy-description" className="input-base min-h-20 resize-y" value={form.description} onChange={(event) => updateForm('description', event.target.value)} /></div>
          <div className="mt-4 grid gap-4 sm:grid-cols-2 xl:grid-cols-1"><div><label htmlFor="trend-rules" className="label">Trend rules</label><input id="trend-rules" className="input-base" value={form.trend} onChange={(event) => updateForm('trend', event.target.value)} placeholder="EMA 20, EMA 50" /></div><div><label htmlFor="momentum-rules" className="label">Momentum rules</label><input id="momentum-rules" className="input-base" value={form.momentum} onChange={(event) => updateForm('momentum', event.target.value)} placeholder="RSI above 55" /></div><div><label htmlFor="volume-rules" className="label">Volume rules</label><input id="volume-rules" className="input-base" value={form.volume} onChange={(event) => updateForm('volume', event.target.value)} placeholder="Volume above average" /></div><div><label htmlFor="market-rules" className="label">Market structure rules</label><input id="market-rules" className="input-base" value={form.smartMoney} onChange={(event) => updateForm('smartMoney', event.target.value)} placeholder="Break of structure" /></div></div>
          <div className="mt-4 grid grid-cols-3 gap-3"><div><label htmlFor="risk-per-trade" className="label">Risk %</label><input id="risk-per-trade" type="number" min="0.1" max="5" step="0.1" className="input-base" value={form.riskPerTrade} onChange={(event) => updateForm('riskPerTrade', event.target.value)} /></div><div><label htmlFor="daily-loss" className="label">Daily loss %</label><input id="daily-loss" type="number" min="0.1" max="25" step="0.1" className="input-base" value={form.maxDailyLoss} onChange={(event) => updateForm('maxDailyLoss', event.target.value)} /></div><div><label htmlFor="strategy-max-open" className="label">Max open</label><input id="strategy-max-open" type="number" min="1" max="20" className="input-base" value={form.maxOpenTrades} onChange={(event) => updateForm('maxOpenTrades', event.target.value)} /></div></div>
          <button type="submit" disabled={submitting} className="btn-primary mt-5 w-full">{submitting ? 'Saving…' : 'Save strategy'}</button>
        </form>
        <div className="card overflow-hidden p-0"><div className="flex items-center justify-between border-b border-slate-200 px-5 py-4"><div><h2 className="text-sm font-semibold text-slate-900">Saved strategies</h2><p className="mt-1 text-xs text-slate-500">The strategy score stays unverified until market-data backtesting is available.</p></div><span className="text-xs font-semibold text-slate-500">{strategies.length} saved</span></div>{loading ? <div className="p-8 text-sm text-slate-500">Loading strategies…</div> : strategies.length ? <div className="divide-y divide-slate-100">{strategies.map((strategy) => <div key={strategy.id} className="flex flex-col gap-4 px-5 py-4 sm:flex-row sm:items-start sm:justify-between"><div><h3 className="text-sm font-semibold text-slate-900">{strategy.name}</h3><p className="mt-1 max-w-2xl text-sm leading-6 text-slate-500">{strategy.description || 'No description added.'}</p><div className="mt-3 flex flex-wrap gap-x-4 gap-y-1 text-xs text-slate-500"><span>{strategy.risk_per_trade}% risk</span><span>Max {strategy.max_open_trades} open</span><span>Health score {strategy.health_score}</span><span>{formatDate(strategy.created_at)}</span></div></div><button type="button" onClick={() => void deleteStrategy(strategy.id)} className="icon-button shrink-0 text-red-700 hover:bg-red-50 hover:text-red-700" title={`Delete ${strategy.name}`}><Trash2 size={17} aria-hidden="true" /></button></div>)}</div> : <EmptyState icon={Workflow} title="No strategies saved" description="Store a rule set here before evaluating it against verified historical data." />}</div>
      </section>
    </>
  )
}
