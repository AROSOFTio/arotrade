'use client'

import { useEffect, useState } from 'react'
import { useRouter } from 'next/navigation'
import { ArrowUpDown, Bot, BrainCircuit, Clock, Landmark, MessageCircleQuestion, Send, ShieldAlert, Sparkles, TriangleAlert } from 'lucide-react'

import { apiRequest, errorMessage, formatDate } from '../../components/api'
import { PageHeader } from '../../components/page-header'

type BrokerAccount = {
  id: number
  broker: string
  account_id: string
  account_type: string
  is_active: boolean
  connection_state?: string | null
}

type Analysis = {
  id: number
  symbol: string
  timeframe: string
  bias: string
  signal: string
  confidence: number
  entry_min: number
  entry_max: number
  stop_loss: number
  take_profit_1?: number | null
  take_profit_2?: number | null
  take_profit_3?: number | null
  risk_reward: number
  reasoning: string[]
  invalidation: string
  news_warning?: string | null
  risk_warning?: string | null
  created_at: string
  candle_close_time?: string | null
  quote_time?: string | null
  quote_age_seconds?: number | null
  stale_data_warning?: boolean | null
}

type ProviderStatus = {
  id: string
  label: string
  model: string
  configured: boolean
  available: boolean
  status: string
  reason?: string | null
}

type ProviderAnalysis = Omit<Analysis, 'id' | 'created_at'>

type ProviderComparison = {
  provider: ProviderStatus
  status: string
  analysis: ProviderAnalysis | null
  error?: string | null
}

type Consensus = {
  majority_signal: string
  agreement_count: number
  model_count: number
  agreement_percentage: number
  average_confidence: number
  conflicting_opinions: string[]
  minority_opinions: { signal: string; count: number }[]
}

type ComparisonResponse = {
  results: ProviderComparison[]
  consensus: Consensus
}

const timeframes = ['M5', 'M15', 'M30', 'H1', 'H4', 'D1', 'W1']
const CUSTOM_SYMBOL = '__custom__'
const symbolGroups: { label: string; symbols: string[] }[] = [
  { label: 'Forex majors', symbols: ['EURUSD', 'GBPUSD', 'USDJPY', 'USDCHF', 'AUDUSD', 'NZDUSD', 'USDCAD'] },
  { label: 'Forex crosses', symbols: ['EURGBP', 'EURJPY', 'GBPJPY', 'AUDJPY', 'CADJPY', 'CHFJPY', 'EURAUD', 'EURCHF', 'GBPAUD', 'GBPCAD', 'AUDNZD', 'NZDJPY'] },
  { label: 'Metals & energy', symbols: ['XAUUSD', 'XAGUSD', 'XPTUSD', 'USOIL', 'UKOIL', 'NATGAS'] },
  { label: 'Indices', symbols: ['US30', 'US100', 'US500', 'GER40', 'UK100', 'FRA40', 'JPN225', 'AUS200', 'HK50'] },
  { label: 'Crypto', symbols: ['BTCUSD', 'ETHUSD', 'SOLUSD', 'XRPUSD', 'BNBUSD', 'DOGEUSD'] },
]

function signalTone(signal: string) {
  if (signal === 'buy') return 'bg-[#f0fdf4] text-[#15803d] border-[#bbf7d0]'
  if (signal === 'sell') return 'bg-[#fef2f2] text-[#b91c1c] border-[#fecaca]'
  return 'bg-slate-100 text-slate-600 border-slate-200'
}

function biasTone(bias: string) {
  if (bias === 'bullish') return 'text-[#15803d]'
  if (bias === 'bearish') return 'text-[#b91c1c]'
  return 'text-slate-600'
}

function targets(analysis: ProviderAnalysis | Analysis) {
  return [analysis.take_profit_1, analysis.take_profit_2, analysis.take_profit_3].filter(Boolean).join(' / ') || '-'
}

export default function AIAnalysisPage() {
  const router = useRouter()
  const [accounts, setAccounts] = useState<BrokerAccount[]>([])
  const [selectedAccountId, setSelectedAccountId] = useState<number | null>(null)
  const [accountsLoading, setAccountsLoading] = useState(true)
  const [providers, setProviders] = useState<ProviderStatus[]>([])
  const [symbol, setSymbol] = useState('EURUSD')
  const [customSymbol, setCustomSymbol] = useState('')
  const [timeframe, setTimeframe] = useState('H1')
  const [prompt, setPrompt] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [result, setResult] = useState<Analysis | null>(null)
  const [comparison, setComparison] = useState<ComparisonResponse | null>(null)
  const [history, setHistory] = useState<Analysis[]>([])
  const [chat, setChat] = useState<{ role: 'user' | 'assistant'; content: string }[]>([])
  const [chatInput, setChatInput] = useState('')
  const [chatLoading, setChatLoading] = useState(false)

  useEffect(() => {
    setAccountsLoading(true)
    apiRequest<BrokerAccount[]>('/broker-accounts')
      .then((r) => {
        const active = r.filter((a) => a.is_active && (a.connection_state === 'deployed' || a.connection_state === 'direct_connected'))
        setAccounts(active)
        if (active.length > 0) {
          const saved = localStorage.getItem('arotrade:selected_account_id')
          const found = active.find((a) => String(a.id) === saved)
          const initial = found ? found.id : active[0].id
          setSelectedAccountId(initial)
          localStorage.setItem('arotrade:selected_account_id', String(initial))
        }
      })
      .catch((err) => setError(errorMessage(err)))
      .finally(() => setAccountsLoading(false))
  }, [])

  useEffect(() => {
    apiRequest<{ providers: ProviderStatus[] }>('/ai/providers')
      .then((response) => setProviders(response.providers))
      .catch(() => setProviders([]))
    apiRequest<Analysis[]>('/ai/analyses?limit=10').then(setHistory).catch(() => undefined)
  }, [])

  const effectiveSymbol = symbol === CUSTOM_SYMBOL ? customSymbol.trim().toUpperCase() : symbol
  const selectedAccount = accounts.find((a) => a.id === selectedAccountId)

  const loadHistory = () => {
    apiRequest<Analysis[]>('/ai/analyses?limit=10').then(setHistory).catch(() => undefined)
  }

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault()
    setError('')
    if (!selectedAccountId) {
      setError('Please select an active broker account')
      return
    }
    if (!effectiveSymbol) {
      setError('Enter a symbol to analyze')
      return
    }
    setLoading(true)
    setResult(null)
    setComparison(null)
    try {
      const body = JSON.stringify({ broker_account_id: selectedAccountId, symbol: effectiveSymbol, timeframe, prompt: prompt || null })
      const [analysis, modelComparison] = await Promise.all([
        apiRequest<Analysis>('/ai/analyze', { method: 'POST', body }),
        apiRequest<ComparisonResponse>('/ai/compare', { method: 'POST', body }),
      ])
      setResult(analysis)
      setComparison(modelComparison)
      setChat([])
      loadHistory()
    } catch (requestError) {
      setError(errorMessage(requestError))
    } finally {
      setLoading(false)
    }
  }

  const askQuestion = async () => {
    if (!result || !chatInput.trim() || chatLoading) return
    const question = chatInput.trim()
    setChatInput('')
    const nextChat = [...chat, { role: 'user' as const, content: question }]
    setChat(nextChat)
    setChatLoading(true)
    try {
      const response = await apiRequest<{ answer: string }>(`/ai/analyses/${result.id}/chat`, {
        method: 'POST',
        body: JSON.stringify({ question, history: chat }),
      })
      setChat([...nextChat, { role: 'assistant', content: response.answer }])
    } catch (requestError) {
      setChat([...nextChat, { role: 'assistant', content: `Sorry - ${errorMessage(requestError)}` }])
    } finally {
      setChatLoading(false)
    }
  }

  if (accountsLoading) {
    return <div className="flex h-64 items-center justify-center text-sm font-medium text-slate-500">Loading MT5 accounts...</div>
  }

  if (accounts.length === 0) {
    return (
      <>
        <PageHeader eyebrow="Research" title="AI analysis" description="Analyze live MT5 market prices." />
        <div className="rounded-lg border border-blue-200 bg-blue-50/50 p-6 text-center">
          <Landmark size={32} className="mx-auto text-blue-500" />
          <h2 className="mt-3 text-sm font-semibold text-slate-900">No active broker accounts connected</h2>
          <p className="mt-1 text-xs text-slate-500">Connect the direct MT5 Expert Advisor bridge to run live market analysis.</p>
          <div className="mt-4"><a href="/dashboard/broker-accounts" className="btn-primary px-4 py-1.5 text-xs font-semibold">Connect Account</a></div>
        </div>
      </>
    )
  }

  return (
    <>
      <PageHeader
        eyebrow="Research"
        title="AI analysis"
        description="Compare multiple AI models on the same live MT5 snapshot. Powered by live MT5 data, deterministic analysis, and graceful provider fallback."
      />

      <div className="mb-6 flex flex-wrap items-center justify-between gap-4 rounded-lg border border-slate-200 bg-white px-5 py-3">
        <div className="flex items-center gap-3">
          <span className="text-xs font-bold uppercase text-slate-500">Selected account</span>
          <select aria-label="Broker Account" className="input-base w-64 text-sm" value={selectedAccountId || ''} onChange={(e) => {
            const id = Number(e.target.value)
            setSelectedAccountId(id)
            localStorage.setItem('arotrade:selected_account_id', String(id))
          }}>
            {accounts.map((a) => <option key={a.id} value={a.id}>{a.broker} ({a.account_type.toUpperCase()} - {a.account_id})</option>)}
          </select>
        </div>
        {selectedAccount && <span className={`inline-flex rounded-full border px-2.5 py-0.5 text-xs font-semibold ${selectedAccount.account_type === 'live' ? 'border-[#bbf7d0] bg-[#f0fdf4] text-[#166534]' : 'border-[#bfdbfe] bg-[#eff6ff] text-[#1e40af]'}`}>{selectedAccount.account_type === 'live' ? 'LIVE MT5' : 'DEMO MT5'}</span>}
      </div>

      <section className="grid gap-6 xl:grid-cols-[420px_minmax(0,1fr)]">
        <form onSubmit={handleSubmit} className="card h-fit space-y-4">
          <div className="flex items-center gap-3">
            <span className="flex h-10 w-10 items-center justify-center rounded-lg bg-blue-50 text-[#2563eb]"><BrainCircuit size={20} aria-hidden="true" /></span>
            <div>
              <h2 className="text-sm font-semibold text-slate-900">Live market analysis</h2>
              <p className="text-xs text-slate-500">MT5 candles plus deterministic indicators</p>
            </div>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label htmlFor="symbol" className="label">Symbol</label>
              <select id="symbol" className="input-base" value={symbol} onChange={(e) => setSymbol(e.target.value)}>
                {symbolGroups.map((group) => <optgroup key={group.label} label={group.label}>{group.symbols.map((item) => <option key={item} value={item}>{item}</option>)}</optgroup>)}
                <option value={CUSTOM_SYMBOL}>Other symbol...</option>
              </select>
            </div>
            <div>
              <label htmlFor="timeframe" className="label">Timeframe</label>
              <select id="timeframe" className="input-base" value={timeframe} onChange={(e) => setTimeframe(e.target.value)}>{timeframes.map((tf) => <option key={tf} value={tf}>{tf}</option>)}</select>
            </div>
          </div>

          {symbol === CUSTOM_SYMBOL && <div><label htmlFor="custom-symbol" className="label">Custom symbol</label><input id="custom-symbol" className="input-base uppercase" value={customSymbol} onChange={(e) => setCustomSymbol(e.target.value.toUpperCase())} required maxLength={20} placeholder="e.g. USDZAR" /></div>}

          <div>
            <label htmlFor="prompt" className="label">Question / context</label>
            <textarea id="prompt" className="input-base min-h-20 resize-y" value={prompt} onChange={(e) => setPrompt(e.target.value)} maxLength={500} placeholder="e.g. Why is gold bullish on M15?" />
          </div>

          {providers.length > 0 && <div className="rounded-lg border border-slate-200 bg-slate-50 p-3">
            <div className="mb-2 text-[11px] font-bold uppercase text-slate-500">AI providers</div>
            <div className="grid grid-cols-2 gap-2">
              {providers.map((provider) => <div key={provider.id} className="rounded-md bg-white px-2.5 py-2 text-xs">
                <div className="font-semibold text-slate-800">{provider.label}</div>
                <div className={provider.available ? 'text-[#15803d]' : 'text-slate-400'}>{provider.available ? provider.model : 'Currently unavailable'}</div>
              </div>)}
            </div>
          </div>}

          {error && <div className="rounded-md border border-red-200 bg-red-50 px-3 py-3 text-sm text-red-700">{error}</div>}
          <button type="submit" disabled={loading} className="btn-primary w-full">{loading ? 'Analyzing...' : <>Compare AI models <Sparkles size={16} aria-hidden="true" /></>}</button>
        </form>

        <div className="space-y-6">
          {comparison && <div className="card space-y-4">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div>
                <h2 className="text-lg font-bold text-slate-950">{effectiveSymbol} - {timeframe}</h2>
                <p className="text-sm text-slate-500">Consensus: <span className="font-semibold uppercase text-slate-900">{comparison.consensus.majority_signal}</span></p>
              </div>
              <div className="grid grid-cols-3 gap-2 text-center text-xs">
                <div className="rounded-md bg-slate-50 px-3 py-2"><div className="font-bold text-slate-950">{comparison.consensus.agreement_count}/{comparison.consensus.model_count}</div><div className="text-slate-500">agree</div></div>
                <div className="rounded-md bg-slate-50 px-3 py-2"><div className="font-bold text-slate-950">{comparison.consensus.agreement_percentage}%</div><div className="text-slate-500">agreement</div></div>
                <div className="rounded-md bg-slate-50 px-3 py-2"><div className="font-bold text-slate-950">{comparison.consensus.average_confidence}%</div><div className="text-slate-500">confidence</div></div>
              </div>
            </div>
            {comparison.consensus.conflicting_opinions.length > 0 && <div className="flex gap-2 rounded-md border border-amber-200 bg-amber-50 px-3 py-3 text-sm text-amber-800"><TriangleAlert size={17} className="mt-0.5 shrink-0" />Disagreement from {comparison.consensus.conflicting_opinions.join(', ')}.</div>}
            <div className="grid gap-3 lg:grid-cols-2">
              {comparison.results.map((item) => <div key={item.provider.id} className="rounded-lg border border-slate-200 bg-white p-4">
                <div className="mb-3 flex items-center justify-between gap-2">
                  <div><h3 className="text-sm font-bold text-slate-950">{item.provider.label}</h3><p className="text-xs text-slate-500">{item.provider.model}</p></div>
                  {item.analysis ? <span className={`rounded-full border px-2.5 py-1 text-xs font-bold uppercase ${signalTone(item.analysis.signal)}`}>{item.analysis.signal}</span> : <span className="rounded-full bg-slate-100 px-2.5 py-1 text-xs font-semibold text-slate-500">Currently unavailable</span>}
                </div>
                {item.analysis ? <>
                  <div className="mb-3 flex items-center gap-3 text-sm"><span className={`font-semibold capitalize ${biasTone(item.analysis.bias)}`}>{item.analysis.bias}</span><span className="text-slate-500">Confidence {item.analysis.confidence}%</span></div>
                  <ul className="space-y-1.5">{item.analysis.reasoning.map((reason, index) => <li key={index} className="text-sm leading-6 text-slate-600">{reason}</li>)}</ul>
                </> : <p className="text-sm text-slate-500">{item.error || item.provider.reason || 'Provider is not configured.'}</p>}
              </div>)}
            </div>
          </div>}

          {result && <div className="card space-y-5">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div><h2 className="text-lg font-bold text-slate-950">Saved primary analysis</h2><p className="text-sm text-slate-500">Bias: <span className={`font-semibold capitalize ${biasTone(result.bias)}`}>{result.bias}</span></p></div>
              <div className="flex items-center gap-2"><span className={`rounded-full border px-3 py-1 text-sm font-bold uppercase ${signalTone(result.signal)}`}>{result.signal}</span><span className="rounded-full bg-blue-50 px-3 py-1 text-sm font-semibold text-[#1d4ed8]">Confidence {result.confidence}%</span></div>
            </div>
            <div className="rounded-lg border border-slate-200 bg-slate-50/60 p-3">
              <div className="mb-2 flex items-center gap-2"><Clock size={13} className="text-slate-400" /><span className="text-[11px] font-bold uppercase text-slate-500">Data freshness</span></div>
              <div className="grid grid-cols-2 gap-3 text-[11px] sm:grid-cols-4"><div><div className="text-slate-400">Created</div><div className="font-semibold text-slate-700">{formatDate(result.created_at)}</div></div>{result.quote_age_seconds != null && <div><div className="text-slate-400">Quote age</div><div className={result.stale_data_warning ? 'font-semibold text-red-600' : 'font-semibold text-slate-700'}>{result.quote_age_seconds.toFixed(0)}s</div></div>}</div>
            </div>
            {(result.entry_min > 0 || result.stop_loss > 0) && <><div className="grid grid-cols-2 gap-3 sm:grid-cols-4"><div className="rounded-md bg-slate-50 px-3 py-3"><p className="text-[11px] font-semibold uppercase text-slate-500">Entry zone</p><p className="mt-1 text-sm font-bold tabular-nums text-slate-950">{result.entry_min} - {result.entry_max}</p></div><div className="rounded-md bg-slate-50 px-3 py-3"><p className="text-[11px] font-semibold uppercase text-slate-500">Stop loss</p><p className="mt-1 text-sm font-bold tabular-nums text-[#b91c1c]">{result.stop_loss}</p></div><div className="rounded-md bg-slate-50 px-3 py-3"><p className="text-[11px] font-semibold uppercase text-slate-500">Targets</p><p className="mt-1 text-sm font-bold tabular-nums text-[#15803d]">{targets(result)}</p></div><div className="rounded-md bg-slate-50 px-3 py-3"><p className="text-[11px] font-semibold uppercase text-slate-500">Reward : risk</p><p className="mt-1 text-sm font-bold tabular-nums text-slate-950">{result.risk_reward ? result.risk_reward.toFixed(2) : '-'}</p></div></div><button type="button" onClick={() => router.push(`/dashboard/markets?${new URLSearchParams({ symbol: result.symbol, direction: result.signal === 'buy' || result.signal === 'sell' ? result.signal : 'buy', sl: String(result.stop_loss), ...(result.take_profit_1 ? { tp: String(result.take_profit_1) } : {}) }).toString()}`)} className="flex w-full items-center justify-center gap-2 rounded-lg border-2 border-blue-200 bg-blue-50/50 py-2.5 text-xs font-bold text-[#1d4ed8] hover:bg-blue-100"><ArrowUpDown size={14} />Use levels in trade ticket</button></>}
            <div><h3 className="text-sm font-semibold text-slate-900">Reasoning</h3><ul className="mt-2 space-y-1.5">{result.reasoning.map((reason, index) => <li key={index} className="flex gap-2 text-sm leading-6 text-slate-600"><span className="mt-2 h-1.5 w-1.5 shrink-0 rounded-full bg-[#2563eb]" />{reason}</li>)}</ul></div>
            <div className="rounded-md border border-slate-200 bg-slate-50 px-3 py-3 text-sm text-slate-600"><span className="font-semibold text-slate-900">Invalidation:</span> {result.invalidation}</div>
            {result.risk_warning && <div className="flex gap-2 rounded-md border border-red-200 bg-red-50 px-3 py-3 text-sm text-red-700"><ShieldAlert size={17} className="mt-0.5 shrink-0" />{result.risk_warning}</div>}
            <div className="border-t border-slate-200 pt-4"><h3 className="flex items-center gap-2 text-sm font-semibold text-slate-900"><MessageCircleQuestion size={16} className="text-[#2563eb]" />Ask about this analysis</h3>{chat.length > 0 && <div className="mt-3 max-h-72 space-y-2 overflow-y-auto">{chat.map((message, index) => <div key={index} className={`rounded-md px-3 py-2.5 text-sm leading-6 ${message.role === 'user' ? 'ml-8 bg-blue-50 text-slate-800' : 'mr-8 bg-slate-50 text-slate-700'}`}>{message.content}</div>)}{chatLoading && <div className="mr-8 rounded-md bg-slate-50 px-3 py-2.5 text-sm text-slate-400">Thinking...</div>}</div>}<div className="mt-3 flex gap-2"><input value={chatInput} onChange={(e) => setChatInput(e.target.value)} onKeyDown={(e) => { if (e.key === 'Enter') { e.preventDefault(); void askQuestion() } }} className="input-base" placeholder="e.g. Why did one provider disagree?" maxLength={500} aria-label="Ask a question about this analysis" /><button type="button" onClick={() => void askQuestion()} disabled={chatLoading || !chatInput.trim()} className="btn-primary shrink-0 px-3" title="Send question" aria-label="Send question"><Send size={16} /></button></div></div>
          </div>}

          {!result && !comparison && <div className="card flex min-h-48 flex-col items-center justify-center gap-3 text-center"><span className="flex h-12 w-12 items-center justify-center rounded-full bg-blue-50 text-[#2563eb]"><Bot size={24} /></span><div><h2 className="text-sm font-semibold text-slate-900">No analysis yet</h2><p className="mt-1 max-w-sm text-sm leading-6 text-slate-500">Pick a symbol and compare configured providers on the live MT5 feed.</p></div></div>}

          {history.length > 0 && <div className="card"><h2 className="text-sm font-semibold text-slate-900">Recent analyses</h2><div className="mt-3 divide-y divide-slate-100">{history.map((item) => <button key={item.id} type="button" onClick={() => { setResult(item); setComparison(null); setChat([]) }} className="flex w-full cursor-pointer items-center justify-between gap-3 py-2.5 text-left hover:bg-slate-50"><span className="text-sm font-semibold text-slate-900">{item.symbol} <span className="font-normal text-slate-500">- {item.timeframe}</span></span><span className="flex items-center gap-2"><span className={`rounded-full border px-2 py-0.5 text-xs font-bold uppercase ${signalTone(item.signal)}`}>{item.signal}</span><span className="hidden text-xs text-slate-400 sm:block">{formatDate(item.created_at)}</span></span></button>)}</div></div>}
        </div>
      </section>
    </>
  )
}
