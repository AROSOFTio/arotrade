'use client'

import { useEffect, useRef, useState } from 'react'
import { Bot, ImagePlus, ShieldAlert, Sparkles, TriangleAlert, X } from 'lucide-react'

import { apiRequest, errorMessage, formatDate } from '../../components/api'
import { PageHeader } from '../../components/page-header'

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
}

const timeframes = ['M5', 'M15', 'M30', 'H1', 'H4', 'D1', 'W1']

const symbolGroups: { label: string; symbols: string[] }[] = [
  { label: 'Forex majors', symbols: ['EURUSD', 'GBPUSD', 'USDJPY', 'USDCHF', 'AUDUSD', 'NZDUSD', 'USDCAD'] },
  { label: 'Forex crosses', symbols: ['EURGBP', 'EURJPY', 'GBPJPY', 'AUDJPY', 'CADJPY', 'CHFJPY', 'EURAUD', 'EURCHF', 'GBPAUD', 'GBPCAD', 'AUDNZD', 'NZDJPY'] },
  { label: 'Metals & energy', symbols: ['XAUUSD', 'XAGUSD', 'XPTUSD', 'USOIL', 'UKOIL', 'NATGAS'] },
  { label: 'Indices', symbols: ['US30', 'US100', 'US500', 'GER40', 'UK100', 'FRA40', 'JPN225', 'AUS200', 'HK50'] },
  { label: 'Crypto', symbols: ['BTCUSD', 'ETHUSD', 'SOLUSD', 'XRPUSD', 'BNBUSD', 'DOGEUSD'] },
  { label: 'Synthetics (Deriv)', symbols: ['V10', 'V25', 'V50', 'V75', 'V100', 'BOOM1000', 'CRASH1000', 'STEP'] },
]

const CUSTOM_SYMBOL = '__custom__'

function signalTone(signal: string) {
  if (signal === 'buy') return 'bg-[#f0fdf4] text-[#15803d]'
  if (signal === 'sell') return 'bg-[#fef2f2] text-[#b91c1c]'
  return 'bg-slate-100 text-slate-600'
}

function biasTone(bias: string) {
  if (bias === 'bullish') return 'text-[#15803d]'
  if (bias === 'bearish') return 'text-[#b91c1c]'
  return 'text-slate-600'
}

export default function AIAnalysisPage() {
  const [symbol, setSymbol] = useState('EURUSD')
  const [customSymbol, setCustomSymbol] = useState('')
  const [timeframe, setTimeframe] = useState('H1')
  const [prompt, setPrompt] = useState('')
  const [file, setFile] = useState<File | null>(null)
  const [previewUrl, setPreviewUrl] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [result, setResult] = useState<Analysis | null>(null)
  const [history, setHistory] = useState<Analysis[]>([])
  const fileInputRef = useRef<HTMLInputElement>(null)

  const loadHistory = () => {
    apiRequest<Analysis[]>('/ai/analyses?limit=10').then(setHistory).catch(() => undefined)
  }

  useEffect(loadHistory, [])

  useEffect(() => {
    if (!file) {
      setPreviewUrl(null)
      return
    }
    const url = URL.createObjectURL(file)
    setPreviewUrl(url)
    return () => URL.revokeObjectURL(url)
  }, [file])

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault()
    setError('')
    const effectiveSymbol = symbol === CUSTOM_SYMBOL ? customSymbol.trim() : symbol
    if (!effectiveSymbol) {
      setError('Enter a symbol to analyze')
      return
    }
    setLoading(true)
    setResult(null)
    try {
      let analysis: Analysis
      if (file) {
        const body = new FormData()
        body.append('file', file)
        body.append('symbol', effectiveSymbol)
        body.append('timeframe', timeframe)
        if (prompt) body.append('prompt', prompt)
        analysis = await apiRequest<Analysis>('/ai/analyze-image', { method: 'POST', body })
      } else {
        analysis = await apiRequest<Analysis>('/ai/analyze', {
          method: 'POST',
          body: JSON.stringify({ symbol: effectiveSymbol, timeframe, prompt: prompt || null }),
        })
      }
      setResult(analysis)
      loadHistory()
    } catch (requestError) {
      setError(errorMessage(requestError))
    } finally {
      setLoading(false)
    }
  }

  return (
    <>
      <PageHeader
        eyebrow="Research"
        title="AI analysis"
        description="Upload a chart screenshot for a full technical read, or run a quick market view. Analyses never open trades by themselves."
      />
      <section className="grid gap-6 xl:grid-cols-[420px_minmax(0,1fr)]">
        <form onSubmit={handleSubmit} className="card h-fit space-y-4">
          <div className="flex items-center gap-3">
            <span className="flex h-10 w-10 items-center justify-center rounded-lg bg-blue-50 text-[#2563eb]"><Bot size={20} aria-hidden="true" /></span>
            <div>
              <h2 className="text-sm font-semibold text-slate-900">New analysis</h2>
              <p className="text-xs text-slate-500">Powered by Gemini</p>
            </div>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label htmlFor="symbol" className="label">Symbol</label>
              <select id="symbol" className="input-base" value={symbol} onChange={(e) => setSymbol(e.target.value)}>
                {symbolGroups.map((group) => (
                  <optgroup key={group.label} label={group.label}>
                    {group.symbols.map((item) => <option key={item} value={item}>{item}</option>)}
                  </optgroup>
                ))}
                <option value={CUSTOM_SYMBOL}>Other symbol…</option>
              </select>
            </div>
            <div>
              <label htmlFor="timeframe" className="label">Timeframe</label>
              <select id="timeframe" className="input-base" value={timeframe} onChange={(e) => setTimeframe(e.target.value)}>
                {timeframes.map((tf) => <option key={tf} value={tf}>{tf}</option>)}
              </select>
            </div>
          </div>

          {symbol === CUSTOM_SYMBOL && (
            <div>
              <label htmlFor="custom-symbol" className="label">Custom symbol</label>
              <input id="custom-symbol" className="input-base uppercase" value={customSymbol} onChange={(e) => setCustomSymbol(e.target.value.toUpperCase())} required maxLength={20} placeholder="e.g. USDZAR" />
            </div>
          )}

          <div>
            <span className="label">Chart screenshot (recommended)</span>
            {previewUrl ? (
              <div className="relative overflow-hidden rounded-md border border-slate-200">
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img src={previewUrl} alt="Chart to analyze" className="max-h-56 w-full object-contain bg-slate-50" />
                <button type="button" className="icon-button absolute right-2 top-2 h-8 w-8" onClick={() => { setFile(null); if (fileInputRef.current) fileInputRef.current.value = '' }} title="Remove image">
                  <X size={15} aria-hidden="true" />
                </button>
              </div>
            ) : (
              <button
                type="button"
                onClick={() => fileInputRef.current?.click()}
                className="flex min-h-24 w-full cursor-pointer flex-col items-center justify-center gap-2 rounded-md border border-dashed border-slate-300 bg-slate-50 px-4 py-5 text-sm font-medium text-slate-500 transition-colors hover:border-[#2563eb] hover:text-[#2563eb]"
              >
                <ImagePlus size={22} aria-hidden="true" />
                Click to add a PNG / JPEG chart screenshot
              </button>
            )}
            <input ref={fileInputRef} type="file" accept="image/png,image/jpeg,image/webp" className="hidden" onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
            <p className="mt-1.5 text-xs text-slate-500">Without an image the AI has no live prices, so confidence is capped and levels must be verified.</p>
          </div>

          <div>
            <label htmlFor="prompt" className="label">Question / context (optional)</label>
            <textarea id="prompt" className="input-base min-h-20 resize-y" value={prompt} onChange={(e) => setPrompt(e.target.value)} maxLength={500} placeholder="e.g. Is this a valid break of structure on the H4?" />
          </div>

          {error && <div className="rounded-md border border-red-200 bg-red-50 px-3 py-3 text-sm text-red-700">{error}</div>}

          <button type="submit" disabled={loading} className="btn-primary w-full">
            {loading ? 'Analyzing…' : <>Run AI analysis <Sparkles size={16} aria-hidden="true" /></>}
          </button>
        </form>

        <div className="space-y-6">
          {result ? (
            <div className="card space-y-5">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div>
                  <h2 className="text-lg font-bold text-slate-950">{result.symbol} · {result.timeframe}</h2>
                  <p className="text-sm text-slate-500">Bias: <span className={`font-semibold capitalize ${biasTone(result.bias)}`}>{result.bias}</span></p>
                </div>
                <div className="flex items-center gap-2">
                  <span className={`rounded-full px-3 py-1 text-sm font-bold uppercase ${signalTone(result.signal)}`}>{result.signal}</span>
                  <span className="rounded-full bg-blue-50 px-3 py-1 text-sm font-semibold text-[#1d4ed8]">Confidence {result.confidence}%</span>
                </div>
              </div>

              {(result.entry_min > 0 || result.stop_loss > 0) && (
                <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
                  <div className="rounded-md bg-slate-50 px-3 py-3">
                    <p className="text-[11px] font-semibold uppercase tracking-wide text-slate-500">Entry zone</p>
                    <p className="mt-1 text-sm font-bold tabular-nums text-slate-950">{result.entry_min} – {result.entry_max}</p>
                  </div>
                  <div className="rounded-md bg-slate-50 px-3 py-3">
                    <p className="text-[11px] font-semibold uppercase tracking-wide text-slate-500">Stop loss</p>
                    <p className="mt-1 text-sm font-bold tabular-nums text-[#b91c1c]">{result.stop_loss}</p>
                  </div>
                  <div className="rounded-md bg-slate-50 px-3 py-3">
                    <p className="text-[11px] font-semibold uppercase tracking-wide text-slate-500">Targets</p>
                    <p className="mt-1 text-sm font-bold tabular-nums text-[#15803d]">{[result.take_profit_1, result.take_profit_2, result.take_profit_3].filter(Boolean).join(' / ') || '—'}</p>
                  </div>
                  <div className="rounded-md bg-slate-50 px-3 py-3">
                    <p className="text-[11px] font-semibold uppercase tracking-wide text-slate-500">Reward : risk</p>
                    <p className="mt-1 text-sm font-bold tabular-nums text-slate-950">{result.risk_reward ? result.risk_reward.toFixed(2) : '—'}</p>
                  </div>
                </div>
              )}

              <div>
                <h3 className="text-sm font-semibold text-slate-900">Reasoning</h3>
                <ul className="mt-2 space-y-1.5">
                  {result.reasoning.map((reason, index) => (
                    <li key={index} className="flex gap-2 text-sm leading-6 text-slate-600">
                      <span className="mt-2 h-1.5 w-1.5 shrink-0 rounded-full bg-[#2563eb]" aria-hidden="true" />
                      {reason}
                    </li>
                  ))}
                </ul>
              </div>

              <div className="rounded-md border border-slate-200 bg-slate-50 px-3 py-3 text-sm text-slate-600">
                <span className="font-semibold text-slate-900">Invalidation:</span> {result.invalidation}
              </div>

              {result.news_warning && (
                <div className="flex gap-2 rounded-md border border-amber-200 bg-amber-50 px-3 py-3 text-sm text-amber-800">
                  <TriangleAlert size={17} className="mt-0.5 shrink-0" aria-hidden="true" /> {result.news_warning}
                </div>
              )}
              {result.risk_warning && (
                <div className="flex gap-2 rounded-md border border-red-200 bg-red-50 px-3 py-3 text-sm text-red-700">
                  <ShieldAlert size={17} className="mt-0.5 shrink-0" aria-hidden="true" /> {result.risk_warning}
                </div>
              )}
            </div>
          ) : (
            <div className="card flex min-h-48 flex-col items-center justify-center gap-3 text-center">
              <span className="flex h-12 w-12 items-center justify-center rounded-full bg-blue-50 text-[#2563eb]"><Bot size={24} aria-hidden="true" /></span>
              <div>
                <h2 className="text-sm font-semibold text-slate-900">No analysis yet</h2>
                <p className="mt-1 max-w-sm text-sm leading-6 text-slate-500">Add a chart screenshot and run the analysis — the result appears here with levels, reasoning and warnings.</p>
              </div>
            </div>
          )}

          {history.length > 0 && (
            <div className="card">
              <h2 className="text-sm font-semibold text-slate-900">Recent analyses</h2>
              <div className="mt-3 divide-y divide-slate-100">
                {history.map((item) => (
                  <button key={item.id} type="button" onClick={() => setResult(item)} className="flex w-full cursor-pointer items-center justify-between gap-3 py-2.5 text-left transition-colors hover:bg-slate-50">
                    <span className="text-sm font-semibold text-slate-900">{item.symbol} <span className="font-normal text-slate-500">· {item.timeframe}</span></span>
                    <span className="flex items-center gap-2">
                      <span className={`rounded-full px-2 py-0.5 text-xs font-bold uppercase ${signalTone(item.signal)}`}>{item.signal}</span>
                      <span className="hidden text-xs text-slate-400 sm:block">{formatDate(item.created_at)}</span>
                    </span>
                  </button>
                ))}
              </div>
            </div>
          )}
        </div>
      </section>
    </>
  )
}
