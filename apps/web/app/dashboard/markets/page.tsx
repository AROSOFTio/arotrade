'use client'

import { useCallback, useEffect, useRef, useState } from 'react'
import { Activity, CalendarClock, Sparkles, TriangleAlert, Landmark } from 'lucide-react'
import { createChart, type IChartApi, type ISeriesApi, type UTCTimestamp } from 'lightweight-charts'

import { apiRequest, errorMessage, formatNumber } from '../../components/api'
import { PageHeader } from '../../components/page-header'

type BrokerAccount = {
  id: number
  broker: string
  account_id: string
  account_type: string
  is_active: boolean
  connection_state?: string | null
}

type SymbolItem = {
  canonical_symbol: string
  broker_symbol: string
  display_name: string
  category?: string
}

type Candle = { time: number; open: number; high: number; low: number; close: number }
type Price = { symbol: string; price: number; change: number; change_percent: number }
type NewsEvent = { title: string; currency: string; date: string; impact: string; forecast?: string | null; previous?: string | null }
type NewsImpact = { symbol: string; summary: string; key_events?: { title: string; when: string; expectation: string }[] }
type Sotd = {
  symbol: string
  timeframe: string
  bias: string
  signal: string
  confidence: number
  entry_min: number
  entry_max: number
  stop_loss: number
  take_profit_1?: number | null
  reasoning: string[]
}

const timeframes = ['M5', 'M15', 'M30', 'H1', 'H4', 'D1']
const NEWS_REFRESH_MS = 2 * 60_000
const AI_REFRESH_MS = 5 * 60_000
const updateTime = (date: Date | null) => date ? date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) : 'pending'

export default function MarketsPage() {
  const [accounts, setAccounts] = useState<BrokerAccount[]>([])
  const [selectedAccountId, setSelectedAccountId] = useState<number | null>(null)
  const [symbols, setSymbols] = useState<SymbolItem[]>([])
  const [selectedSymbol, setSelectedSymbol] = useState<SymbolItem | null>(null)
  const [timeframe, setTimeframe] = useState('H1')
  const [price, setPrice] = useState<Price | null>(null)
  const [news, setNews] = useState<NewsEvent[]>([])
  const [impact, setImpact] = useState<NewsImpact | null>(null)
  const [impactLoading, setImpactLoading] = useState(false)
  const [sotd, setSotd] = useState<Sotd | null>(null)
  const [sotdLoading, setSotdLoading] = useState(false)
  const [newsUpdatedAt, setNewsUpdatedAt] = useState<Date | null>(null)
  const [impactUpdatedAt, setImpactUpdatedAt] = useState<Date | null>(null)
  const [sotdUpdatedAt, setSotdUpdatedAt] = useState<Date | null>(null)
  const [error, setError] = useState('')
  const [accountsLoading, setAccountsLoading] = useState(true)
  const chartContainerRef = useRef<HTMLDivElement>(null)
  const chartRef = useRef<IChartApi | null>(null)
  const seriesRef = useRef<ISeriesApi<'Candlestick'> | null>(null)

  // 1. Fetch broker accounts
  useEffect(() => {
    setAccountsLoading(true)
    apiRequest<BrokerAccount[]>('/broker-accounts')
      .then((r) => {
        const active = r.filter(a => a.is_active && a.connection_state === 'deployed')
        setAccounts(active)
        if (active.length > 0) {
          const saved = localStorage.getItem('arotrade:selected_account_id')
          const found = active.find(a => String(a.id) === saved)
          const initial = found ? found.id : active[0].id
          setSelectedAccountId(initial)
          localStorage.setItem('arotrade:selected_account_id', String(initial))
        }
      })
      .catch((err) => setError(errorMessage(err)))
      .finally(() => setAccountsLoading(false))
  }, [])

  // 2. Fetch symbols once account is selected
  useEffect(() => {
    if (!selectedAccountId) return
    apiRequest<{ symbols: SymbolItem[] }>(`/market/accounts/${selectedAccountId}/symbols`)
      .then((r) => {
        setSymbols(r.symbols)
        if (r.symbols.length > 0) {
          setSelectedSymbol(r.symbols[0])
        } else {
          setSelectedSymbol(null)
        }
      })
      .catch((err) => setError(errorMessage(err)))
  }, [selectedAccountId])

  // Chart lifecycle
  useEffect(() => {
    const container = chartContainerRef.current
    if (!container) return

    const themeOptions = (dark: boolean) => ({
      layout: {
        background: { color: dark ? '#101828' : '#ffffff' },
        textColor: dark ? '#94a3b8' : '#334155',
      },
      grid: {
        vertLines: { color: dark ? '#182238' : '#f1f5f9' },
        horzLines: { color: dark ? '#182238' : '#f1f5f9' },
      },
      timeScale: { timeVisible: true, secondsVisible: false, borderColor: dark ? '#1e293f' : '#e2e8f0' },
      rightPriceScale: { borderColor: dark ? '#1e293f' : '#e2e8f0' },
    })

    const isDark = () => document.documentElement.classList.contains('dark')
    const chartHeight = () => (window.innerWidth < 640 ? 300 : 420)

    const chart = createChart(container, {
      height: chartHeight(),
      crosshair: { mode: 0 },
      ...themeOptions(isDark()),
    })
    const series = chart.addCandlestickSeries({
      upColor: '#22c55e', downColor: '#ef4444', borderVisible: false,
      wickUpColor: '#22c55e', wickDownColor: '#ef4444',
    })
    chartRef.current = chart
    seriesRef.current = series

    const onResize = () => chart.applyOptions({ width: container.clientWidth, height: chartHeight() })
    const onTheme = () => chart.applyOptions(themeOptions(isDark()))
    onResize()
    window.addEventListener('resize', onResize)
    window.addEventListener('themechange', onTheme)
    return () => {
      window.removeEventListener('resize', onResize)
      window.removeEventListener('themechange', onTheme)
      chart.remove()
      chartRef.current = null
      seriesRef.current = null
    }
  }, [])

  const loadCandles = useCallback(async () => {
    if (!selectedAccountId || !selectedSymbol) return
    try {
      const response = await apiRequest<{ candles: Candle[] }>(
        `/market/accounts/${selectedAccountId}/symbols/${selectedSymbol.broker_symbol}/candles?timeframe=${timeframe}&count=300`
      )
      seriesRef.current?.setData(response.candles.map((c) => ({ ...c, time: c.time as UTCTimestamp })))
      chartRef.current?.timeScale().fitContent()
      setError('')
    } catch (requestError) {
      setError(errorMessage(requestError))
    }
  }, [selectedAccountId, selectedSymbol, timeframe])

  const loadPrice = useCallback(() => {
    if (!selectedAccountId || !selectedSymbol) return
    apiRequest<{ bid: number; ask: number; spread: number }>(
      `/market/accounts/${selectedAccountId}/symbols/${selectedSymbol.broker_symbol}/quote`
    )
      .then((q) => {
        setPrice({
          symbol: selectedSymbol.canonical_symbol,
          price: q.bid,
          change: 0,
          change_percent: 0
        })
      })
      .catch(() => undefined)
  }, [selectedAccountId, selectedSymbol])

  const loadNews = useCallback(() => {
    if (!selectedSymbol) return
    apiRequest<{ events: NewsEvent[] }>(`/market/news?symbol=${selectedSymbol.canonical_symbol}`)
      .then((r) => {
        setNews(r.events)
        setNewsUpdatedAt(new Date())
      })
      .catch(() => setNews([]))
  }, [selectedSymbol])

  useEffect(() => {
    if (!selectedAccountId || !selectedSymbol) return
    void loadCandles()
    loadPrice()
    setImpact(null)
    loadNews()
    const priceInterval = window.setInterval(loadPrice, 10000)
    const candleInterval = window.setInterval(() => void loadCandles(), 30000)
    const newsInterval = window.setInterval(loadNews, NEWS_REFRESH_MS)
    return () => {
      window.clearInterval(priceInterval)
      window.clearInterval(candleInterval)
      window.clearInterval(newsInterval)
    }
  }, [loadCandles, loadPrice, loadNews, selectedAccountId, selectedSymbol])

  const analyzeNews = useCallback(async () => {
    if (!selectedSymbol) return
    setImpactLoading(true)
    try {
      setImpact(
        await apiRequest<NewsImpact>('/market/news/analyze', {
          method: 'POST',
          body: JSON.stringify({ symbol: selectedSymbol.canonical_symbol })
        })
      )
      setImpactUpdatedAt(new Date())
    } catch (requestError) {
      setError(errorMessage(requestError))
    } finally {
      setImpactLoading(false)
    }
  }, [selectedSymbol])

  const loadSotd = useCallback(async (refresh = false) => {
    setSotdLoading(true)
    try {
      setSotd(await apiRequest<Sotd>(`/ai/signal-of-the-day${refresh ? '?refresh=true' : ''}`))
      setSotdUpdatedAt(new Date())
    } catch (requestError) {
      setError(errorMessage(requestError))
    } finally {
      setSotdLoading(false)
    }
  }, [])

  useEffect(() => {
    void loadSotd()
    const interval = window.setInterval(() => void loadSotd(true), AI_REFRESH_MS)
    return () => window.clearInterval(interval)
  }, [loadSotd])

  useEffect(() => {
    if (!selectedSymbol) return
    setImpact(null)
    void analyzeNews()
    const interval = window.setInterval(() => void analyzeNews(), AI_REFRESH_MS)
    return () => window.clearInterval(interval)
  }, [analyzeNews, selectedSymbol])

  const handleAccountChange = (val: string) => {
    const id = Number(val)
    setSelectedAccountId(id)
    localStorage.setItem('arotrade:selected_account_id', String(id))
  }

  const selectedAccount = accounts.find(a => a.id === selectedAccountId)

  if (accountsLoading) {
    return (
      <div className="flex h-64 items-center justify-center">
        <div className="text-sm font-medium text-slate-500">Loading MT5 Accounts...</div>
      </div>
    )
  }

  if (accounts.length === 0) {
    return (
      <>
        <PageHeader eyebrow="Live data" title="Markets" description="Real-time charts and prices." />
        <div className="rounded-lg border border-blue-200 bg-blue-50/50 p-6 text-center">
          <Landmark size={32} className="mx-auto text-blue-500" />
          <h2 className="mt-3 text-sm font-semibold text-slate-900">No active broker accounts connected</h2>
          <p className="mt-1 text-xs text-slate-500">You must connect and deploy an active MT5 broker account to load real-time market data.</p>
          <div className="mt-4">
            <a href="/dashboard/broker-accounts" className="btn-primary py-1.5 px-4 text-xs font-semibold">Connect Account</a>
          </div>
        </div>
      </>
    )
  }

  return (
    <>
      <PageHeader
        eyebrow="Live data"
        title="Markets"
        description="Real-time charts and prices, upcoming economic events with AI impact analysis, and the AI's pick of the day."
      />
      {error && <div className="mb-5 rounded-md border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">{error}</div>}

      <div className="mb-6 flex flex-wrap items-center justify-between gap-4 rounded-lg border border-slate-200 bg-white px-5 py-3">
        <div className="flex items-center gap-3">
          <span className="text-xs font-bold text-slate-500 uppercase">Selected Account:</span>
          <select
            aria-label="Broker Account"
            className="input-base w-64 text-sm"
            value={selectedAccountId || ''}
            onChange={(e) => handleAccountChange(e.target.value)}
          >
            {accounts.map((a) => (
              <option key={a.id} value={a.id}>
                {a.broker} ({a.account_type.toUpperCase()} · {a.account_id})
              </option>
            ))}
          </select>
        </div>
        {selectedAccount && (
          <div className="flex items-center gap-2">
            <span className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-semibold ${
              selectedAccount.account_type === 'live' ? 'bg-[#f0fdf4] text-[#166534] border border-[#bbf7d0]' : 'bg-[#eff6ff] text-[#1e40af] border border-[#bfdbfe]'
            }`}>
              {selectedAccount.account_type === 'live' ? 'LIVE MT5' : 'DEMO MT5'}
            </span>
          </div>
        )}
      </div>

      <section className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_360px]">
        <div className="card p-0">
          <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-200 px-5 py-4">
            <div className="flex items-center gap-3">
              <select
                aria-label="Symbol"
                className="input-base w-48 text-sm"
                value={selectedSymbol ? JSON.stringify(selectedSymbol) : ''}
                onChange={(e) => setSelectedSymbol(JSON.parse(e.target.value))}
              >
                {symbols.map((s) => (
                  <option key={s.broker_symbol} value={JSON.stringify(s)}>
                    {s.canonical_symbol} ({s.broker_symbol})
                  </option>
                ))}
              </select>
              <div className="flex rounded-md border border-slate-200 p-0.5">
                {timeframes.map((tf) => (
                  <button
                    key={tf}
                    type="button"
                    onClick={() => setTimeframe(tf)}
                    className={`min-h-8 rounded px-2.5 text-xs font-semibold ${
                      timeframe === tf ? 'bg-blue-50 text-[#1d4ed8]' : 'text-slate-500 hover:text-slate-900'
                    }`}
                  >
                    {tf}
                  </button>
                ))}
              </div>
            </div>
            {price && (
              <div className="text-right">
                <p className="text-lg font-bold tabular-nums text-slate-950">{formatNumber(price.price, 5)}</p>
                <p className="text-xs font-semibold tabular-nums text-[#15803d]">
                  LIVE QUOTE
                </p>
              </div>
            )}
          </div>
          <div ref={chartContainerRef} className="w-full" />
          <p className="border-t border-slate-100 px-5 py-2.5 text-xs text-slate-400">
            MT5 live feed · updates every 30s · quotes every 10s
          </p>
        </div>

        <div className="space-y-6">
          <div className="card">
            <div className="flex items-center justify-between gap-3">
              <h2 className="flex items-center gap-2 text-sm font-semibold text-slate-900">
                <Sparkles size={15} className="text-[#2563eb]" aria-hidden="true" /> Signal of the day
              </h2>
              <button
                type="button"
                disabled={sotdLoading}
                onClick={() => void loadSotd(Boolean(sotd))}
                className="btn-secondary min-h-8 px-3 py-1 text-xs"
              >
                {sotdLoading ? 'Working…' : sotd ? 'Refresh' : 'Reveal'}
              </button>
            </div>
            {sotd ? (
              <div className="mt-4">
                <div className="flex items-center justify-between">
                  <p className="text-base font-bold text-slate-950">{sotd.symbol} · {sotd.timeframe}</p>
                  <span className={`rounded-full px-2.5 py-1 text-xs font-bold uppercase ${
                    sotd.signal === 'buy' ? 'bg-[#f0fdf4] text-[#15803d]' : sotd.signal === 'sell' ? 'bg-[#fef2f2] text-[#b91c1c]' : 'bg-slate-100 text-slate-600'
                  }`}>
                    {sotd.signal} · {sotd.confidence}%
                  </span>
                </div>
                <dl className="mt-3 grid grid-cols-3 gap-2 text-center">
                  <div className="rounded-md bg-slate-50 px-2 py-2">
                    <dt className="text-[10px] font-semibold uppercase text-slate-500">Entry</dt>
                    <dd className="mt-0.5 text-xs font-bold tabular-nums text-slate-900">
                      {formatNumber(sotd.entry_min, 5)}–{formatNumber(sotd.entry_max, 5)}
                    </dd>
                  </div>
                  <div className="rounded-md bg-slate-50 px-2 py-2">
                    <dt className="text-[10px] font-semibold uppercase text-slate-500">Stop</dt>
                    <dd className="mt-0.5 text-xs font-bold tabular-nums text-[#b91c1c]">
                      {formatNumber(sotd.stop_loss, 5)}
                    </dd>
                  </div>
                  <div className="rounded-md bg-slate-50 px-2 py-2">
                    <dt className="text-[10px] font-semibold uppercase text-slate-500">Target</dt>
                    <dd className="mt-0.5 text-xs font-bold tabular-nums text-[#15803d]">
                      {sotd.take_profit_1 ? formatNumber(sotd.take_profit_1, 5) : '—'}
                    </dd>
                  </div>
                </dl>
                {sotd.reasoning?.[1] && <p className="mt-3 text-xs leading-5 text-slate-600">{sotd.reasoning.slice(1, 3).join(' ')}</p>}
                <p className="mt-3 text-[11px] text-slate-400">
                  Last update: {updateTime(sotdUpdatedAt)}.
                </p>
              </div>
            ) : (
              <p className="mt-3 text-xs leading-5 text-slate-500">
                Loading AI pick of the day...
              </p>
            )}
          </div>

          <div className="card">
            <div className="flex items-center justify-between gap-3">
              <h2 className="flex items-center gap-2 text-sm font-semibold text-slate-900">
                <CalendarClock size={15} className="text-[#2563eb]" aria-hidden="true" /> News IQ · {selectedSymbol?.canonical_symbol}
              </h2>
              <button
                type="button"
                disabled={impactLoading}
                onClick={() => void analyzeNews()}
                className="btn-secondary min-h-8 px-3 py-1 text-xs"
              >
                {impactLoading ? 'Analyzing…' : 'AI impact'}
              </button>
            </div>
            <p className="mt-2 text-[11px] text-slate-400">
              Last news: {updateTime(newsUpdatedAt)}. Last AI: {updateTime(impactUpdatedAt)}.
            </p>
            {impact && (
              <div className="mt-3 rounded-md border border-blue-100 bg-blue-50/60 px-3 py-3">
                <p className="text-xs leading-5 text-slate-700">{impact.summary}</p>
              </div>
            )}
            <div className="mt-3 max-h-64 space-y-2 overflow-y-auto">
              {news.length === 0 ? (
                <p className="text-xs text-slate-500">No high/medium-impact events in the next 7 days for this market.</p>
              ) : (
                news.map((event, index) => (
                  <div key={`${event.title}-${index}`} className="flex items-start gap-2 rounded-md border border-slate-100 px-3 py-2">
                    {event.impact === 'High' ? (
                      <TriangleAlert size={14} className="mt-0.5 shrink-0 text-[#b91c1c]" aria-hidden="true" />
                    ) : (
                      <Activity size={14} className="mt-0.5 shrink-0 text-amber-600" aria-hidden="true" />
                    )}
                    <div className="min-w-0">
                      <p className="truncate text-xs font-semibold text-slate-900">{event.currency} · {event.title}</p>
                      <p className="text-[11px] text-slate-500">
                        {new Date(event.date).toLocaleString()} {event.forecast ? `· forecast ${event.forecast}` : ''}
                      </p>
                    </div>
                  </div>
                ))
              )}
            </div>
          </div>
        </div>
      </section>
    </>
  )
}
