'use client'

import { useEffect, useState } from 'react'
import { Check, Play, Plus, Search, X, Zap } from 'lucide-react'

import { apiRequest, errorMessage, formatDate, formatNumber } from '../../components/api'
import { EmptyState } from '../../components/empty-state'
import { PageHeader } from '../../components/page-header'
import { StatusBadge } from '../../components/status-badge'

type Signal = {
  id: number
  symbol: string
  timeframe: string
  signal_type: 'buy' | 'sell'
  entry_min: number
  entry_max: number
  stop_loss: number
  take_profit_1?: number | null
  risk_reward?: number | null
  confidence: number
  status: string
  notes?: string | null
  created_at: string
  approved_at?: string | null
  valid_until?: string | null
}

type SignalForm = {
  symbol: string
  timeframe: string
  signal_type: 'buy' | 'sell'
  entry_min: string
  entry_max: string
  stop_loss: string
  take_profit_1: string
  confidence: string
  valid_until: string
  notes: string
}

const initialForm: SignalForm = {
  symbol: 'EURUSD',
  timeframe: 'M15',
  signal_type: 'buy',
  entry_min: '',
  entry_max: '',
  stop_loss: '',
  take_profit_1: '',
  confidence: '70',
  valid_until: '',
  notes: '',
}

type LiveUser = { enable_live_trading: boolean; accepted_live_disclaimer: boolean }

type LiveBrokerAccount = {
  id: number
  name?: string | null
  account_id: string
  server?: string | null
  account_type: string
  connection_state?: string | null
  metaapi_account_id?: string | null
  is_active: boolean
}

export default function SignalsPage() {
  const [signals, setSignals] = useState<Signal[]>([])
  const [form, setForm] = useState<SignalForm>(initialForm)
  const [selectedId, setSelectedId] = useState<number | null>(null)
  const [observedPrice, setObservedPrice] = useState('')
  const [volume, setVolume] = useState('1')
  const [liveUser, setLiveUser] = useState<LiveUser | null>(null)
  const [liveAccounts, setLiveAccounts] = useState<LiveBrokerAccount[]>([])
  const [liveAccountId, setLiveAccountId] = useState('')
  const [liveVolume, setLiveVolume] = useState('0.01')
  const [liveArmed, setLiveArmed] = useState(false)
  const [liveSubmitting, setLiveSubmitting] = useState(false)
  const [evaluation, setEvaluation] = useState<{ eligible: boolean; reasons: string[]; calculated_risk_reward: number | null } | null>(null)
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(true)
  const [submitting, setSubmitting] = useState(false)

  const selectedSignal = signals.find((signal) => signal.id === selectedId) || null

  const loadSignals = async () => {
    setLoading(true)
    try {
      const response = await apiRequest<Signal[]>('/signals')
      setSignals(response)
      setSelectedId((current) => current ?? response[0]?.id ?? null)
    } catch (requestError) {
      setError(errorMessage(requestError))
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    void loadSignals()
    apiRequest<LiveUser>('/auth/me').then(setLiveUser).catch(() => undefined)
    apiRequest<LiveBrokerAccount[]>('/broker-accounts')
      .then((accounts) => setLiveAccounts(accounts.filter((a) => a.is_active && a.metaapi_account_id)))
      .catch(() => undefined)
  }, [])

  const updateForm = (field: keyof SignalForm, value: string) => {
    setForm((current) => ({ ...current, [field]: value }))
  }

  const createSignal = async (event: React.FormEvent) => {
    event.preventDefault()
    setError('')
    setMessage('')
    setSubmitting(true)
    try {
      const response = await apiRequest<Signal>('/signals', {
        method: 'POST',
        body: JSON.stringify({
          symbol: form.symbol.trim().toUpperCase(),
          timeframe: form.timeframe,
          signal_type: form.signal_type,
          entry_min: Number(form.entry_min),
          entry_max: Number(form.entry_max),
          stop_loss: Number(form.stop_loss),
          take_profit_1: form.take_profit_1 ? Number(form.take_profit_1) : null,
          confidence: Number(form.confidence),
          valid_until: form.valid_until ? new Date(form.valid_until).toISOString() : null,
          notes: form.notes || null,
        }),
      })
      setSignals((current) => [response, ...current])
      setSelectedId(response.id)
      setForm(initialForm)
      setMessage('Signal created and awaiting review.')
    } catch (requestError) {
      setError(errorMessage(requestError))
    } finally {
      setSubmitting(false)
    }
  }

  const updateSignalStatus = async (id: number, action: 'approve' | 'reject') => {
    setError('')
    setMessage('')
    try {
      const response = await apiRequest<Signal>(`/signals/${id}/${action}`, { method: 'PUT' })
      setSignals((current) => current.map((signal) => signal.id === id ? response : signal))
      setMessage(action === 'approve' ? 'Signal approved for paper checks.' : 'Signal rejected.')
      setEvaluation(null)
    } catch (requestError) {
      setError(errorMessage(requestError))
    }
  }

  const evaluateSignal = async () => {
    if (!selectedSignal) return
    setError('')
    setMessage('')
    try {
      const response = await apiRequest<{ eligible: boolean; reasons: string[]; calculated_risk_reward: number | null }>(`/signals/${selectedSignal.id}/evaluate`, {
        method: 'POST',
        body: JSON.stringify({ observed_price: Number(observedPrice) }),
      })
      setEvaluation(response)
    } catch (requestError) {
      setError(errorMessage(requestError))
      setEvaluation(null)
    }
  }

  const executeLiveTrade = async () => {
    if (!selectedSignal || !liveAccountId) return
    setError('')
    setMessage('')
    setLiveSubmitting(true)
    try {
      await apiRequest(`/signals/${selectedSignal.id}/execute-live`, {
        method: 'POST',
        body: JSON.stringify({ volume: Number(liveVolume), broker_account_id: Number(liveAccountId) }),
      })
      setMessage('LIVE order submitted to your broker. Check open positions in Trades and in your MT5 app.')
      setLiveArmed(false)
      await loadSignals()
    } catch (requestError) {
      setError(errorMessage(requestError))
    } finally {
      setLiveSubmitting(false)
    }
  }

  const executePaperTrade = async () => {
    if (!selectedSignal) return
    setError('')
    setMessage('')
    setSubmitting(true)
    try {
      await apiRequest(`/signals/${selectedSignal.id}/execute-demo`, {
        method: 'POST',
        body: JSON.stringify({ observed_price: Number(observedPrice), volume: Number(volume) }),
      })
      setMessage('Paper trade filled and recorded in the ledger.')
      setEvaluation(null)
      await loadSignals()
    } catch (requestError) {
      setError(errorMessage(requestError))
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <>
      <PageHeader eyebrow="Signal desk" title="Trading signals" description="Create, approve, evaluate, and simulate signals against the platform safeguards." />
      {(error || message) && <div className={`mb-5 rounded-md border px-4 py-3 text-sm ${error ? 'border-red-200 bg-red-50 text-red-700' : 'border-emerald-200 bg-emerald-50 text-emerald-700'}`}>{error || message}</div>}

      <section className="grid gap-6 2xl:grid-cols-[minmax(340px,0.75fr)_minmax(0,1.25fr)]">
        <form onSubmit={createSignal} className="card h-fit">
          <div className="flex items-center gap-2"><span className="flex h-9 w-9 items-center justify-center rounded-lg bg-blue-50 text-[#2563eb]"><Plus size={18} aria-hidden="true" /></span><div><h2 className="text-sm font-semibold text-slate-900">New signal</h2><p className="mt-0.5 text-xs text-slate-500">Every entry needs defined risk boundaries.</p></div></div>
          <div className="mt-5 grid gap-4 sm:grid-cols-2 2xl:grid-cols-1">
            <div><label className="label" htmlFor="symbol">Symbol</label><input id="symbol" className="input-base" value={form.symbol} onChange={(event) => updateForm('symbol', event.target.value)} required /></div>
            <div><label className="label" htmlFor="timeframe">Timeframe</label><select id="timeframe" className="input-base" value={form.timeframe} onChange={(event) => updateForm('timeframe', event.target.value)}>{['M1','M5','M15','M30','H1','H4','D1'].map((item) => <option key={item}>{item}</option>)}</select></div>
          </div>
          <fieldset className="mt-4"><legend className="label">Direction</legend><div className="grid grid-cols-2 rounded-md border border-slate-300 p-1"><button type="button" onClick={() => updateForm('signal_type', 'buy')} className={`min-h-9 rounded px-3 text-sm font-semibold ${form.signal_type === 'buy' ? 'bg-blue-50 text-[#1d4ed8]' : 'text-slate-500'}`}>Buy</button><button type="button" onClick={() => updateForm('signal_type', 'sell')} className={`min-h-9 rounded px-3 text-sm font-semibold ${form.signal_type === 'sell' ? 'bg-blue-50 text-[#1d4ed8]' : 'text-slate-500'}`}>Sell</button></div></fieldset>
          <div className="mt-4 grid grid-cols-2 gap-4"><div><label className="label" htmlFor="entry-min">Entry minimum</label><input id="entry-min" type="number" step="any" className="input-base" value={form.entry_min} onChange={(event) => updateForm('entry_min', event.target.value)} required /></div><div><label className="label" htmlFor="entry-max">Entry maximum</label><input id="entry-max" type="number" step="any" className="input-base" value={form.entry_max} onChange={(event) => updateForm('entry_max', event.target.value)} required /></div><div><label className="label" htmlFor="stop-loss">Stop loss</label><input id="stop-loss" type="number" step="any" className="input-base" value={form.stop_loss} onChange={(event) => updateForm('stop_loss', event.target.value)} required /></div><div><label className="label" htmlFor="take-profit">Target</label><input id="take-profit" type="number" step="any" className="input-base" value={form.take_profit_1} onChange={(event) => updateForm('take_profit_1', event.target.value)} required /></div></div>
          <div className="mt-4 grid grid-cols-2 gap-4"><div><label className="label" htmlFor="confidence">Confidence %</label><input id="confidence" type="number" min="0" max="100" className="input-base" value={form.confidence} onChange={(event) => updateForm('confidence', event.target.value)} required /></div><div><label className="label" htmlFor="valid-until">Valid until</label><input id="valid-until" type="datetime-local" className="input-base" value={form.valid_until} onChange={(event) => updateForm('valid_until', event.target.value)} /></div></div>
          <div className="mt-4"><label className="label" htmlFor="signal-notes">Notes</label><textarea id="signal-notes" className="input-base min-h-20 resize-y" value={form.notes} onChange={(event) => updateForm('notes', event.target.value)} /></div>
          <button type="submit" disabled={submitting} className="btn-primary mt-5 w-full">{submitting ? 'Creating…' : 'Create signal'}</button>
        </form>

        <div className="card overflow-hidden p-0">
          <div className="flex flex-col justify-between gap-3 border-b border-slate-200 px-5 py-4 sm:flex-row sm:items-center"><div><h2 className="text-sm font-semibold text-slate-900">Signal queue</h2><p className="mt-1 text-xs text-slate-500">Select a signal to review or simulate.</p></div><span className="text-xs font-semibold text-slate-500">{signals.length} total</span></div>
          {loading ? <div className="p-8 text-sm text-slate-500">Loading signals…</div> : signals.length ? <div className="divide-y divide-slate-100">{signals.map((signal) => <button type="button" key={signal.id} onClick={() => { setSelectedId(signal.id); setEvaluation(null); setObservedPrice(''); }} className={`grid w-full grid-cols-[minmax(0,1fr)_auto] gap-4 px-5 py-4 text-left transition-colors hover:bg-slate-50 ${selectedId === signal.id ? 'bg-blue-50/60' : ''}`}><span><span className="flex items-center gap-2"><strong className="text-sm text-slate-900">{signal.symbol}</strong><span className={`text-xs font-semibold uppercase ${signal.signal_type === 'buy' ? 'text-emerald-700' : 'text-red-700'}`}>{signal.signal_type}</span></span><span className="mt-1 block text-xs text-slate-500">{signal.timeframe} · {formatNumber(signal.entry_min)}–{formatNumber(signal.entry_max)} · {signal.confidence}% confidence</span></span><span className="flex flex-col items-end gap-2"><StatusBadge value={signal.status} /><span className="text-xs text-slate-400">{formatDate(signal.created_at)}</span></span></button>)}</div> : <EmptyState icon={Search} title="No signals in the queue" description="Create a structured signal to start the paper-trading review process." />}
        </div>
      </section>

      {selectedSignal && <section className="mt-6 grid gap-6 xl:grid-cols-[minmax(0,1fr)_360px]">
        <div className="card"><div className="flex flex-wrap items-start justify-between gap-3"><div><p className="text-xs font-semibold uppercase tracking-[0.08em] text-[#2563eb]">Signal #{selectedSignal.id}</p><h2 className="mt-1 text-lg font-bold text-slate-950">{selectedSignal.symbol} <span className="text-sm font-semibold uppercase text-slate-500">{selectedSignal.signal_type}</span></h2></div><StatusBadge value={selectedSignal.status} /></div><dl className="mt-5 grid gap-x-6 gap-y-4 sm:grid-cols-3"><div><dt className="text-xs font-medium text-slate-500">Entry zone</dt><dd className="mt-1 text-sm font-semibold text-slate-900">{formatNumber(selectedSignal.entry_min)} – {formatNumber(selectedSignal.entry_max)}</dd></div><div><dt className="text-xs font-medium text-slate-500">Stop loss</dt><dd className="mt-1 text-sm font-semibold text-red-700">{formatNumber(selectedSignal.stop_loss)}</dd></div><div><dt className="text-xs font-medium text-slate-500">Target</dt><dd className="mt-1 text-sm font-semibold text-emerald-700">{selectedSignal.take_profit_1 ? formatNumber(selectedSignal.take_profit_1) : '—'}</dd></div><div><dt className="text-xs font-medium text-slate-500">Confidence</dt><dd className="mt-1 text-sm font-semibold text-slate-900">{selectedSignal.confidence}%</dd></div><div><dt className="text-xs font-medium text-slate-500">Valid until</dt><dd className="mt-1 text-sm font-semibold text-slate-900">{formatDate(selectedSignal.valid_until)}</dd></div><div><dt className="text-xs font-medium text-slate-500">Notes</dt><dd className="mt-1 text-sm text-slate-700">{selectedSignal.notes || '—'}</dd></div></dl>
          {selectedSignal.status === 'pending' && <div className="mt-6 flex flex-wrap gap-2"><button type="button" className="btn-primary" onClick={() => void updateSignalStatus(selectedSignal.id, 'approve')}><Check size={16} aria-hidden="true" />Approve</button><button type="button" className="btn-danger" onClick={() => void updateSignalStatus(selectedSignal.id, 'reject')}><X size={16} aria-hidden="true" />Reject</button></div>}
          {selectedSignal.status === 'executed_demo' && <div className="mt-6 rounded-md border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-700">This signal has a paper-trade record. Review it in the ledger.</div>}
        </div>
        <aside className="card"><h2 className="text-sm font-semibold text-slate-900">Paper execution check</h2><p className="mt-1 text-xs leading-5 text-slate-500">Use an observed price to test the approved signal against risk gates.</p>{selectedSignal.status === 'approved' ? <><div className="mt-5"><label className="label" htmlFor="observed-price">Observed price</label><input id="observed-price" type="number" step="any" value={observedPrice} onChange={(event) => setObservedPrice(event.target.value)} className="input-base" /></div><div className="mt-4"><label className="label" htmlFor="volume">Paper volume</label><input id="volume" type="number" min="0" step="any" value={volume} onChange={(event) => setVolume(event.target.value)} className="input-base" /></div><button type="button" onClick={() => void evaluateSignal()} disabled={!observedPrice} className="btn-secondary mt-5 w-full"><Search size={16} aria-hidden="true" />Evaluate signal</button>{evaluation && <div className={`mt-4 rounded-md border px-3 py-3 text-sm ${evaluation.eligible ? 'border-emerald-200 bg-emerald-50 text-emerald-700' : 'border-amber-200 bg-amber-50 text-amber-800'}`}><p className="font-semibold">{evaluation.eligible ? 'Eligible for paper execution' : 'Execution blocked'}</p>{evaluation.calculated_risk_reward !== null && <p className="mt-1 text-xs">Calculated reward:risk {evaluation.calculated_risk_reward.toFixed(2)}:1</p>}{evaluation.reasons.length > 0 && <ul className="mt-2 list-disc space-y-1 pl-4 text-xs">{evaluation.reasons.map((reason) => <li key={reason}>{reason}</li>)}</ul>}</div>}{evaluation?.eligible && <button type="button" disabled={submitting} onClick={() => void executePaperTrade()} className="btn-primary mt-4 w-full"><Play size={16} aria-hidden="true" />{submitting ? 'Submitting…' : 'Execute paper trade'}</button>}

        <div className="mt-6 border-t border-slate-200 pt-5">
          <h2 className="flex items-center gap-2 text-sm font-semibold text-slate-900"><Zap size={15} className="text-amber-600" aria-hidden="true" /> Live execution</h2>
          {!liveUser?.enable_live_trading ? (
            <p className="mt-2 rounded-md bg-slate-50 px-3 py-3 text-xs leading-5 text-slate-600">Live trading is off for your account. Enable it in Settings to send approved signals to your broker.</p>
          ) : !liveUser.accepted_live_disclaimer ? (
            <p className="mt-2 rounded-md bg-slate-50 px-3 py-3 text-xs leading-5 text-slate-600">Live trading still needs your risk confirmation in Settings before orders can go to your broker.</p>
          ) : liveAccounts.length === 0 ? (
            <p className="mt-2 rounded-md bg-slate-50 px-3 py-3 text-xs leading-5 text-slate-600">No connected broker account. Connect your MT5/Exness account on the Broker accounts page, then deploy it.</p>
          ) : (
            <>
              <div className="mt-3">
                <label className="label" htmlFor="live-account">Broker account</label>
                <select id="live-account" className="input-base" value={liveAccountId} onChange={(event) => { setLiveAccountId(event.target.value); setLiveArmed(false) }}>
                  <option value="">Select account…</option>
                  {liveAccounts.map((account) => (
                    <option key={account.id} value={account.id} disabled={account.connection_state !== 'deployed'}>
                      {(account.name || account.account_id)} · {account.account_type.toUpperCase()} {account.connection_state !== 'deployed' ? '(not deployed)' : ''}
                    </option>
                  ))}
                </select>
              </div>
              <div className="mt-3">
                <label className="label" htmlFor="live-volume">Volume (lots)</label>
                <input id="live-volume" type="number" min="0.01" step="0.01" className="input-base" value={liveVolume} onChange={(event) => { setLiveVolume(event.target.value); setLiveArmed(false) }} />
              </div>
              {liveArmed ? (
                <div className="mt-4 rounded-md border border-amber-200 bg-amber-50 px-3 py-3">
                  <p className="text-xs font-semibold text-amber-800">Send {liveVolume} lots {selectedSignal.signal_type.toUpperCase()} {selectedSignal.symbol} with SL {formatNumber(selectedSignal.stop_loss)} to your broker?</p>
                  <div className="mt-3 flex gap-2">
                    <button type="button" disabled={liveSubmitting} onClick={() => void executeLiveTrade()} className="btn-primary min-h-8 flex-1 bg-amber-600 px-3 py-1 text-xs hover:bg-amber-700">{liveSubmitting ? 'Sending…' : 'Yes, send live order'}</button>
                    <button type="button" onClick={() => setLiveArmed(false)} className="btn-secondary min-h-8 px-3 py-1 text-xs">Cancel</button>
                  </div>
                </div>
              ) : (
                <button type="button" disabled={!liveAccountId || !liveVolume} onClick={() => setLiveArmed(true)} className="btn-secondary mt-4 w-full border-amber-300 text-amber-800 hover:bg-amber-50">
                  <Zap size={15} aria-hidden="true" /> Execute LIVE…
                </button>
              )}
            </>
          )}
        </div></> : <p className="mt-5 rounded-md bg-slate-50 px-3 py-3 text-sm text-slate-600">Approve this signal before it can be evaluated for paper execution.</p>}</aside>
      </section>}
    </>
  )
}
