'use client'

import { useEffect, useState } from 'react'
import { Check, Play, Plus, Search, X, Zap, Sliders, Loader2, Sparkles, RefreshCw, Trash2 } from 'lucide-react'

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

type LiveExecutionStatus = {
  live_trading: {
    user_preference: boolean
    risk_disclosure: boolean
    final_eligibility: boolean
    reasons: string[]
  }
}

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

type ScannerProfile = {
  id: number
  name: string
  execution_mode: 'paper' | 'broker_demo' | 'live'
  broker_account_id?: number | null
  symbols: string[]
  timeframes: string[]
  active_strategy_ids: string[]
  risk_percent: number
  minimum_confidence: number
  minimum_risk_reward: number
  max_spread_points?: number | null
  approval_required: boolean
  scan_enabled: boolean
  maximum_signal_age_minutes: number
  created_at: string
}

export default function SignalsPage() {
  const [activeTab, setActiveTab] = useState<'signals' | 'scanner'>('signals')
  const [signals, setSignals] = useState<Signal[]>([])
  const [form, setForm] = useState<SignalForm>(initialForm)
  const [selectedId, setSelectedId] = useState<number | null>(null)
  const [observedPrice, setObservedPrice] = useState('')
  const [volume, setVolume] = useState('1')
  const [liveExecutionStatus, setLiveExecutionStatus] = useState<LiveExecutionStatus | null>(null)
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

  // Scanner Profile Management State
  const [profiles, setProfiles] = useState<ScannerProfile[]>([])
  const [profilesLoading, setProfilesLoading] = useState(false)
  const [scannerError, setScannerError] = useState('')
  const [scannerMessage, setScannerMessage] = useState('')
  const [scanningProfileId, setScanningProfileId] = useState<number | null>(null)
  const [newProfileForm, setNewProfileForm] = useState({
    name: 'Main Aggressive Scanner',
    broker_account_id: '',
    watched_symbols_str: 'EURUSD, GBPUSD, XAUUSD',
    watched_timeframes_str: 'M15, H1',
    risk_percent: '0.5',
    minimum_confidence: '70',
    minimum_risk_reward: '1.5',
    max_spread_points: '20.0',
    approval_required: true,
  })

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

  const loadScannerProfiles = async () => {
    setProfilesLoading(true)
    try {
      const response = await apiRequest<{ profiles: ScannerProfile[] }>('/scanner/profiles')
      setProfiles(response.profiles)
    } catch (requestError) {
      setScannerError(errorMessage(requestError))
    } finally {
      setProfilesLoading(false)
    }
  }

  useEffect(() => {
    void loadSignals()
    void loadScannerProfiles()
    apiRequest<LiveExecutionStatus>('/auth/me/execution-status').then(setLiveExecutionStatus).catch(() => undefined)
    apiRequest<LiveBrokerAccount[]>('/broker-accounts')
      .then((accounts) => {
        const active = accounts.filter((a) => a.is_active && a.metaapi_account_id)
        setLiveAccounts(active)
        if (active.length > 0) {
          setNewProfileForm((f) => ({ ...f, broker_account_id: String(active[0].id) }))
        }
      })
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
      setMessage('LIVE order submitted to your broker. Check open positions in Trades.')
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

  // Scanner Profile handlers
  const createScannerProfile = async (event: React.FormEvent) => {
    event.preventDefault()
    setScannerError('')
    setScannerMessage('')
    setProfilesLoading(true)
    try {
      const symbols = newProfileForm.watched_symbols_str.split(',').map((s) => s.trim().toUpperCase()).filter(Boolean)
      const timeframes = newProfileForm.watched_timeframes_str.split(',').map((t) => t.trim().toUpperCase()).filter(Boolean)
      const selectedAccount = liveAccounts.find((account) => String(account.id) === newProfileForm.broker_account_id)
      const selectedAccountType = selectedAccount?.account_type.toLowerCase()
      const executionMode = selectedAccountType === 'live' ? 'live' : selectedAccountType === 'demo' ? 'broker_demo' : 'paper'

      const payload = {
        name: newProfileForm.name,
        execution_mode: executionMode,
        broker_account_id: newProfileForm.broker_account_id ? Number(newProfileForm.broker_account_id) : null,
        symbols,
        timeframes,
        active_strategy_ids: [],
        risk_percent: Number(newProfileForm.risk_percent),
        minimum_confidence: Number(newProfileForm.minimum_confidence),
        minimum_risk_reward: Number(newProfileForm.minimum_risk_reward),
        max_spread_points: Number(newProfileForm.max_spread_points),
        approval_required: newProfileForm.approval_required,
      }

      const response = await apiRequest<{ profile: ScannerProfile }>('/scanner/profiles', {
        method: 'POST',
        body: JSON.stringify(payload),
      })
      await apiRequest(`/scanner/profiles/${response.profile.id}/enable`, { method: 'POST' })
      await apiRequest(`/scanner/profiles/${response.profile.id}/scan`, { method: 'POST' })
      setScannerMessage('Scanner profile created, activated, and first scan started.')
      await loadScannerProfiles()
      await loadSignals()
    } catch (requestError) {
      setScannerError(errorMessage(requestError))
    } finally {
      setProfilesLoading(false)
    }
  }

  const toggleScannerProfile = async (id: number, currentEnabled: boolean) => {
    setScannerError('')
    setScannerMessage('')
    const action = currentEnabled ? 'disable' : 'enable'
    try {
      await apiRequest(`/scanner/profiles/${id}/${action}`, { method: 'POST' })
      setScannerMessage(`Scanner profile ${action === 'enable' ? 'activated' : 'deactivated'}.`)
      await loadScannerProfiles()
    } catch (requestError) {
      setScannerError(errorMessage(requestError))
    }
  }

  const deleteScannerProfile = async (id: number) => {
    if (!window.confirm('Delete this scanner profile?')) return
    setScannerError('')
    setScannerMessage('')
    try {
      await apiRequest(`/scanner/profiles/${id}`, { method: 'DELETE' })
      setScannerMessage('Scanner profile deleted.')
      await loadScannerProfiles()
    } catch (requestError) {
      setScannerError(errorMessage(requestError))
    }
  }

  const triggerScan = async (id: number) => {
    setScannerError('')
    setScannerMessage('')
    setScanningProfileId(id)
    try {
      const res: any = await apiRequest(`/scanner/profiles/${id}/scan`, { method: 'POST' })
      setScannerMessage(res.message || `Scan completed. Discovered ${res.signals_discovered} setups.`)
      await loadSignals()
    } catch (requestError) {
      setScannerError(errorMessage(requestError))
    } finally {
      setScanningProfileId(null)
    }
  }

  return (
    <>
      <PageHeader eyebrow="Trading operations" title="Signal desk" description="Configure automated signal scanners or review and execute trade alerts." />
      
      {/* Premium Tab Navigation */}
      <div className="mb-6 flex border-b border-slate-200">
        <button
          type="button"
          onClick={() => { setActiveTab('signals'); setError(''); setMessage(''); }}
          className={`border-b-2 px-5 py-3 text-sm font-semibold transition-colors ${activeTab === 'signals' ? 'border-[#2563eb] text-[#2563eb]' : 'border-transparent text-slate-500 hover:text-slate-900'}`}
        >
          Signal Queue & Simulation
        </button>
        <button
          type="button"
          onClick={() => { setActiveTab('scanner'); setScannerError(''); setScannerMessage(''); }}
          className={`border-b-2 px-5 py-3 text-sm font-semibold transition-colors ${activeTab === 'scanner' ? 'border-[#2563eb] text-[#2563eb]' : 'border-transparent text-slate-500 hover:text-slate-900'}`}
        >
          Automated Market Scanner
        </button>
      </div>

      {activeTab === 'signals' && (
        <>
          {(error || message) && (
            <div className={`mb-5 rounded-md border px-4 py-3 text-sm ${error ? 'border-red-200 bg-red-50 text-red-700' : 'border-emerald-200 bg-emerald-50 text-emerald-700'}`}>
              {error || message}
            </div>
          )}

          <section className="grid gap-6 2xl:grid-cols-[minmax(340px,0.75fr)_minmax(0,1.25fr)]">
            <form onSubmit={createSignal} className="card h-fit">
              <div className="flex items-center gap-2">
                <span className="flex h-9 w-9 items-center justify-center rounded-lg bg-blue-50 text-[#2563eb]">
                  <Plus size={18} aria-hidden="true" />
                </span>
                <div>
                  <h2 className="text-sm font-semibold text-slate-900">New manual signal</h2>
                  <p className="mt-0.5 text-xs text-slate-500">Every entry needs defined risk boundaries.</p>
                </div>
              </div>
              <div className="mt-5 grid gap-4 sm:grid-cols-2 2xl:grid-cols-1">
                <div>
                  <label className="label" htmlFor="symbol">Symbol</label>
                  <input id="symbol" className="input-base" value={form.symbol} onChange={(event) => updateForm('symbol', event.target.value)} required />
                </div>
                <div>
                  <label className="label" htmlFor="timeframe">Timeframe</label>
                  <select id="timeframe" className="input-base" value={form.timeframe} onChange={(event) => updateForm('timeframe', event.target.value)}>
                    {['M1','M5','M15','M30','H1','H4','D1'].map((item) => <option key={item}>{item}</option>)}
                  </select>
                </div>
              </div>
              <fieldset className="mt-4">
                <legend className="label">Direction</legend>
                <div className="grid grid-cols-2 rounded-md border border-slate-300 p-1">
                  <button type="button" onClick={() => updateForm('signal_type', 'buy')} className={`min-h-9 rounded px-3 text-sm font-semibold ${form.signal_type === 'buy' ? 'bg-blue-50 text-[#1d4ed8]' : 'text-slate-500'}`}>Buy</button>
                  <button type="button" onClick={() => updateForm('signal_type', 'sell')} className={`min-h-9 rounded px-3 text-sm font-semibold ${form.signal_type === 'sell' ? 'bg-blue-50 text-[#1d4ed8]' : 'text-slate-500'}`}>Sell</button>
                </div>
              </fieldset>
              <div className="mt-4 grid grid-cols-2 gap-4">
                <div>
                  <label className="label" htmlFor="entry-min">Entry minimum</label>
                  <input id="entry-min" type="number" step="any" className="input-base" value={form.entry_min} onChange={(event) => updateForm('entry_min', event.target.value)} required />
                </div>
                <div>
                  <label className="label" htmlFor="entry-max">Entry maximum</label>
                  <input id="entry-max" type="number" step="any" className="input-base" value={form.entry_max} onChange={(event) => updateForm('entry_max', event.target.value)} required />
                </div>
                <div>
                  <label className="label" htmlFor="stop-loss">Stop loss</label>
                  <input id="stop-loss" type="number" step="any" className="input-base" value={form.stop_loss} onChange={(event) => updateForm('stop_loss', event.target.value)} required />
                </div>
                <div>
                  <label className="label" htmlFor="take-profit">Target</label>
                  <input id="take-profit" type="number" step="any" className="input-base" value={form.take_profit_1} onChange={(event) => updateForm('take_profit_1', event.target.value)} required />
                </div>
              </div>
              <div className="mt-4 grid grid-cols-2 gap-4">
                <div>
                  <label className="label" htmlFor="confidence">Confidence %</label>
                  <input id="confidence" type="number" min="0" max="100" className="input-base" value={form.confidence} onChange={(event) => updateForm('confidence', event.target.value)} required />
                </div>
                <div>
                  <label className="label" htmlFor="valid-until">Valid until</label>
                  <input id="valid-until" type="datetime-local" className="input-base" value={form.valid_until} onChange={(event) => updateForm('valid_until', event.target.value)} />
                </div>
              </div>
              <div className="mt-4"><label className="label" htmlFor="signal-notes">Notes</label><textarea id="signal-notes" className="input-base min-h-20 resize-y" value={form.notes} onChange={(event) => updateForm('notes', event.target.value)} /></div>
              <button type="submit" disabled={submitting} className="btn-primary mt-5 w-full">{submitting ? 'Creating…' : 'Create signal'}</button>
            </form>

            <div className="card overflow-hidden p-0">
              <div className="flex flex-col justify-between gap-3 border-b border-slate-200 px-5 py-4 sm:flex-row sm:items-center">
                <div>
                  <h2 className="text-sm font-semibold text-slate-900">Signal queue</h2>
                  <p className="mt-1 text-xs text-slate-500">Select a signal to review or simulate.</p>
                </div>
                <span className="text-xs font-semibold text-slate-500">{signals.length} total</span>
              </div>
              {loading ? (
                <div className="p-8 text-sm text-slate-500">Loading signals…</div>
              ) : signals.length ? (
                <div className="divide-y divide-slate-100">
                  {signals.map((signal) => (
                    <button
                      type="button"
                      key={signal.id}
                      onClick={() => { setSelectedId(signal.id); setEvaluation(null); setObservedPrice(''); }}
                      className={`grid w-full grid-cols-[minmax(0,1fr)_auto] gap-4 px-5 py-4 text-left transition-colors hover:bg-slate-50 ${selectedId === signal.id ? 'bg-blue-50/60' : ''}`}
                    >
                      <span>
                        <span className="flex items-center gap-2">
                          <strong className="text-sm text-slate-900">{signal.symbol}</strong>
                          <span className={`text-xs font-semibold uppercase ${signal.signal_type === 'buy' ? 'text-emerald-700' : 'text-red-700'}`}>{signal.signal_type}</span>
                        </span>
                        <span className="mt-1 block text-xs text-slate-500">{signal.timeframe} · {formatNumber(signal.entry_min)}–{formatNumber(signal.entry_max)} · {signal.confidence}% confidence</span>
                      </span>
                      <span className="flex flex-col items-end gap-2">
                        <StatusBadge value={signal.status} />
                        <span className="text-xs text-slate-400">{formatDate(signal.created_at)}</span>
                      </span>
                    </button>
                  ))}
                </div>
              ) : (
                <EmptyState icon={Search} title="No signals in the queue" description="Discovered signals will appear here automatically." />
              )}
            </div>
          </section>

          {selectedSignal && (
            <section className="mt-6 grid gap-6 xl:grid-cols-[minmax(0,1fr)_360px]">
              <div className="card">
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div>
                    <p className="text-xs font-semibold uppercase tracking-[0.08em] text-[#2563eb]">Signal #{selectedSignal.id}</p>
                    <h2 className="mt-1 text-lg font-bold text-slate-950">{selectedSignal.symbol} <span className="text-sm font-semibold uppercase text-slate-500">{selectedSignal.signal_type}</span></h2>
                  </div>
                  <StatusBadge value={selectedSignal.status} />
                </div>
                <dl className="mt-5 grid gap-x-6 gap-y-4 sm:grid-cols-3">
                  <div>
                    <dt className="text-xs font-medium text-slate-500">Entry zone</dt>
                    <dd className="mt-1 text-sm font-semibold text-slate-900">{formatNumber(selectedSignal.entry_min)} – {formatNumber(selectedSignal.entry_max)}</dd>
                  </div>
                  <div>
                    <dt className="text-xs font-medium text-slate-500">Stop loss</dt>
                    <dd className="mt-1 text-sm font-semibold text-red-700">{formatNumber(selectedSignal.stop_loss)}</dd>
                  </div>
                  <div>
                    <dt className="text-xs font-medium text-slate-500">Target</dt>
                    <dd className="mt-1 text-sm font-semibold text-emerald-700">{selectedSignal.take_profit_1 ? formatNumber(selectedSignal.take_profit_1) : '—'}</dd>
                  </div>
                  <div>
                    <dt className="text-xs font-medium text-slate-500">Confidence</dt>
                    <dd className="mt-1 text-sm font-semibold text-slate-900">{selectedSignal.confidence}%</dd>
                  </div>
                  <div>
                    <dt className="text-xs font-medium text-slate-500">Valid until</dt>
                    <dd className="mt-1 text-sm font-semibold text-slate-900">{formatDate(selectedSignal.valid_until)}</dd>
                  </div>
                  <div>
                    <dt className="text-xs font-medium text-slate-500">Notes</dt>
                    <dd className="mt-1 text-sm text-slate-700">{selectedSignal.notes || '—'}</dd>
                  </div>
                </dl>
                {selectedSignal.status === 'pending' && (
                  <div className="mt-6 flex flex-wrap gap-2">
                    <button type="button" className="btn-primary" onClick={() => void updateSignalStatus(selectedSignal.id, 'approve')}><Check size={16} aria-hidden="true" />Approve</button>
                    <button type="button" className="btn-danger" onClick={() => void updateSignalStatus(selectedSignal.id, 'reject')}><X size={16} aria-hidden="true" />Reject</button>
                  </div>
                )}
                {selectedSignal.status === 'executed_demo' && <div className="mt-6 rounded-md border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-700">This signal has a paper-trade record. Review it in the ledger.</div>}
              </div>
              <aside className="card">
                <h2 className="text-sm font-semibold text-slate-900">Paper execution check</h2>
                <p className="mt-1 text-xs leading-5 text-slate-500">Use an observed price to test the approved signal against risk gates.</p>
                {selectedSignal.status === 'approved' ? (
                  <>
                    <div className="mt-5">
                      <label className="label" htmlFor="observed-price">Observed price</label>
                      <input id="observed-price" type="number" step="any" value={observedPrice} onChange={(event) => setObservedPrice(event.target.value)} className="input-base" />
                    </div>
                    <div className="mt-4">
                      <label className="label" htmlFor="volume">Paper volume</label>
                      <input id="volume" type="number" min="0" step="any" value={volume} onChange={(event) => setVolume(event.target.value)} className="input-base" />
                    </div>
                    <button type="button" onClick={() => void evaluateSignal()} disabled={!observedPrice} className="btn-secondary mt-5 w-full"><Search size={16} aria-hidden="true" />Evaluate signal</button>
                    {evaluation && (
                      <div className={`mt-4 rounded-md border px-3 py-3 text-sm ${evaluation.eligible ? 'border-emerald-200 bg-emerald-50 text-emerald-700' : 'border-amber-200 bg-amber-50 text-amber-800'}`}>
                        <p className="font-semibold">{evaluation.eligible ? 'Eligible for paper execution' : 'Execution blocked'}</p>
                        {evaluation.calculated_risk_reward !== null && <p className="mt-1 text-xs">Calculated reward:risk {evaluation.calculated_risk_reward.toFixed(2)}:1</p>}
                        {evaluation.reasons.length > 0 && <ul className="mt-2 list-disc space-y-1 pl-4 text-xs">{evaluation.reasons.map((reason) => <li key={reason}>{reason}</li>)}</ul>}
                      </div>
                    )}
                    {evaluation?.eligible && (
                      <button type="button" disabled={submitting} onClick={() => void executePaperTrade()} className="btn-primary mt-4 w-full"><Play size={16} aria-hidden="true" />{submitting ? 'Submitting…' : 'Execute paper trade'}</button>
                    )}

                    <div className="mt-6 border-t border-slate-200 pt-5">
                      <h2 className="flex items-center gap-2 text-sm font-semibold text-slate-900"><Zap size={15} className="text-amber-600" aria-hidden="true" /> Live execution</h2>
                      {!liveExecutionStatus?.live_trading.user_preference ? (
                        <p className="mt-2 rounded-md bg-slate-50 px-3 py-3 text-xs leading-5 text-slate-600">Live trading is off for your account. Enable it in Settings.</p>
                      ) : !liveExecutionStatus.live_trading.risk_disclosure ? (
                        <p className="mt-2 rounded-md bg-slate-50 px-3 py-3 text-xs leading-5 text-slate-600">Live trading still needs your risk confirmation in Settings.</p>
                      ) : !liveExecutionStatus.live_trading.final_eligibility ? (
                        <div className="mt-2 rounded-md bg-slate-50 px-3 py-3 text-xs leading-5 text-slate-600">
                          <p>Live trading is blocked:</p>
                          <ul className="mt-2 list-disc space-y-1 pl-4">
                            {liveExecutionStatus.live_trading.reasons.map((reason) => <li key={reason}>{reason}</li>)}
                          </ul>
                        </div>
                      ) : liveAccounts.length === 0 ? (
                        <p className="mt-2 rounded-md bg-slate-50 px-3 py-3 text-xs leading-5 text-slate-600">No connected broker account. Connect Exness/MT5 in Broker Accounts page.</p>
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
                              <p className="text-xs font-semibold text-amber-800">Send {liveVolume} lots {selectedSignal.signal_type.toUpperCase()} {selectedSignal.symbol} to your broker?</p>
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
                    </div>
                  </>
                ) : (
                  <p className="mt-5 rounded-md bg-slate-50 px-3 py-3 text-sm text-slate-600">Approve this signal before it can be evaluated for paper execution.</p>
                )}
              </aside>
            </section>
          )}
        </>
      )}

      {activeTab === 'scanner' && (
        <>
          {(scannerError || scannerMessage) && (
            <div className={`mb-5 rounded-md border px-4 py-3 text-sm ${scannerError ? 'border-red-200 bg-red-50 text-red-700' : 'border-emerald-200 bg-emerald-50 text-emerald-700'}`}>
              {scannerError || scannerMessage}
            </div>
          )}

          <div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_380px]">
            {/* Active profiles list */}
            <div className="card">
              <h2 className="flex items-center gap-2 text-sm font-semibold text-slate-900">
                <Sliders size={16} className="text-[#2563eb]" />
                Active scan configurations
              </h2>
              <p className="mt-1 text-xs text-slate-500">Profiles run periodically on closed candles to automatically scan and suggest setups.</p>
              
              {profilesLoading && profiles.length === 0 ? (
                <div className="flex items-center gap-2 p-8 text-sm text-slate-500"><Loader2 size={16} className="animate-spin" />Loading scanner configurations…</div>
              ) : profiles.length === 0 ? (
                <div className="mt-6 border border-dashed border-slate-200 rounded-lg p-8 text-center text-sm text-slate-400">No active scanner configurations. Configure a new scanner profile.</div>
              ) : (
                <div className="mt-5 divide-y divide-slate-100">
                  {profiles.map((profile) => (
                    <div key={profile.id} className="py-4 first:pt-0 last:pb-0 flex items-center justify-between gap-4">
                      <div className="min-w-0 flex-1">
                        <div className="flex items-center gap-3">
                          <h3 className="text-sm font-bold text-slate-950">{profile.name}</h3>
                          <span className={`rounded-full px-2 py-0.5 text-[10px] font-bold ${profile.scan_enabled ? 'bg-emerald-50 text-emerald-700' : 'bg-slate-100 text-slate-500'}`}>
                            {profile.scan_enabled ? 'Active' : 'Paused'}
                          </span>
                        </div>
                        <p className="mt-1 text-xs text-slate-500 truncate">
                          <strong>Symbols:</strong> {profile.symbols.join(', ')} / <strong>Timeframes:</strong> {profile.timeframes.join(', ')}
                        </p>
                        <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-[11px] text-slate-400">
                          <span>Mode: {profile.execution_mode === 'broker_demo' ? 'Demo broker' : profile.execution_mode === 'live' ? 'Live broker' : 'Paper'}</span>
                          <span>Risk: {profile.risk_percent}%</span>
                          <span>Min Conf: {profile.minimum_confidence}%</span>
                          <span>Min R:R: {profile.minimum_risk_reward}:1</span>
                          <span>Alert: {profile.approval_required ? 'Review before entry' : 'Auto-approve signal'}</span>
                        </div>
                      </div>
                      <div className="flex items-center gap-2">
                        <button
                          type="button"
                          title={profile.scan_enabled ? "Deactivate" : "Activate"}
                          onClick={() => void toggleScannerProfile(profile.id, profile.scan_enabled)}
                          className={`btn-secondary min-h-8 px-2 py-1 text-xs ${profile.scan_enabled ? 'text-amber-700' : 'text-emerald-700'}`}
                        >
                          {profile.scan_enabled ? 'Pause' : 'Activate'}
                        </button>
                        <button
                          type="button"
                          disabled={scanningProfileId === profile.id}
                          onClick={() => void triggerScan(profile.id)}
                          className="btn-secondary min-h-8 px-2 py-1 text-xs text-[#2563eb] flex items-center gap-1"
                        >
                          {scanningProfileId === profile.id ? <Loader2 size={12} className="animate-spin" /> : <RefreshCw size={12} />}
                          Run Scan
                        </button>
                        <button
                          type="button"
                          onClick={() => void deleteScannerProfile(profile.id)}
                          className="btn-secondary min-h-8 px-2 py-1 text-xs text-red-600 hover:bg-red-50 border-red-200"
                        >
                          <Trash2 size={12} />
                        </button>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>

            {/* Create new profile form */}
            <form onSubmit={createScannerProfile} className="card h-fit">
              <div className="flex items-center gap-2">
                <span className="flex h-9 w-9 items-center justify-center rounded-lg bg-blue-50 text-[#2563eb]">
                  <Sparkles size={18} aria-hidden="true" />
                </span>
                <div>
                  <h2 className="text-sm font-semibold text-slate-900">New scanner configuration</h2>
                  <p className="mt-0.5 text-xs text-slate-500">Configure parameters for candle scanning.</p>
                </div>
              </div>
              <div className="mt-5 grid gap-4">
                <div>
                  <label className="label" htmlFor="profile-name">Configuration Name</label>
                  <input id="profile-name" className="input-base" value={newProfileForm.name} onChange={(e) => setNewProfileForm({...newProfileForm, name: e.target.value})} required />
                </div>
                <div>
                  <label className="label" htmlFor="profile-account">Broker account mapping</label>
                  <select id="profile-account" className="input-base" value={newProfileForm.broker_account_id} onChange={(e) => setNewProfileForm({...newProfileForm, broker_account_id: e.target.value})} required>
                    <option value="">Select account…</option>
                    {liveAccounts.map((account) => (
                      <option key={account.id} value={account.id}>
                        {account.name || account.account_id} · {account.account_type.toUpperCase()}
                      </option>
                    ))}
                  </select>
                </div>
                <div>
                  <label className="label" htmlFor="profile-symbols">Watched symbols (comma separated)</label>
                  <input id="profile-symbols" className="input-base" value={newProfileForm.watched_symbols_str} onChange={(e) => setNewProfileForm({...newProfileForm, watched_symbols_str: e.target.value})} required />
                </div>
                <div>
                  <label className="label" htmlFor="profile-timeframes">Timeframes (comma separated)</label>
                  <input id="profile-timeframes" className="input-base" value={newProfileForm.watched_timeframes_str} onChange={(e) => setNewProfileForm({...newProfileForm, watched_timeframes_str: e.target.value})} required />
                </div>
                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <label className="label" htmlFor="profile-risk">Risk per trade %</label>
                    <input id="profile-risk" type="number" step="0.1" className="input-base" value={newProfileForm.risk_percent} onChange={(e) => setNewProfileForm({...newProfileForm, risk_percent: e.target.value})} required />
                  </div>
                  <div>
                    <label className="label" htmlFor="profile-confidence">Min Confidence %</label>
                    <input id="profile-confidence" type="number" className="input-base" value={newProfileForm.minimum_confidence} onChange={(e) => setNewProfileForm({...newProfileForm, minimum_confidence: e.target.value})} required />
                  </div>
                </div>
                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <label className="label" htmlFor="profile-rr">Min R:R Ratio</label>
                    <input id="profile-rr" type="number" step="0.1" className="input-base" value={newProfileForm.minimum_risk_reward} onChange={(e) => setNewProfileForm({...newProfileForm, minimum_risk_reward: e.target.value})} required />
                  </div>
                  <div>
                    <label className="label" htmlFor="profile-spread">Max Spread (points)</label>
                    <input id="profile-spread" type="number" className="input-base" value={newProfileForm.max_spread_points} onChange={(e) => setNewProfileForm({...newProfileForm, max_spread_points: e.target.value})} required />
                  </div>
                </div>
                
                <label className="mt-2 flex cursor-pointer items-start gap-3 rounded-md border border-slate-200 bg-slate-50 px-3 py-3 text-sm text-slate-700">
                  <input
                    type="checkbox"
                    className="mt-0.5 h-4 w-4 cursor-pointer accent-[#2563eb]"
                    checked={newProfileForm.approval_required}
                    onChange={(e) => setNewProfileForm({...newProfileForm, approval_required: e.target.checked})}
                  />
                  <div>
                    <span className="font-semibold block">Require manual approval</span>
                    <span className="text-xs text-slate-400 block mt-0.5">Keep enabled to receive scanner alerts and decide whether to enter.</span>
                  </div>
                </label>
              </div>
              
              <button type="submit" disabled={profilesLoading} className="btn-primary mt-5 w-full">
                {profilesLoading ? 'Saving…' : 'Configure scanner'}
              </button>
            </form>
          </div>
        </>
      )}
    </>
  )
}
