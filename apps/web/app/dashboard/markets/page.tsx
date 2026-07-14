'use client'

import { useCallback, useEffect, useRef, useState } from 'react'
import { Activity, CalendarClock, Sparkles, TriangleAlert, Landmark, ShieldAlert, ArrowUpDown, Eye } from 'lucide-react'
import { createChart, type IChartApi, type ISeriesApi, type UTCTimestamp } from 'lightweight-charts'

import { apiRequest, errorMessage, formatNumber } from '../../components/api'
import { PageHeader } from '../../components/page-header'

type BrokerAccount = {
  id: number
  broker: string
  account_id: string
  account_type: string
  balance: number
  currency: string
  is_active: boolean
  connection_state?: string | null
}

type SymbolItem = {
  canonical_symbol: string
  broker_symbol: string
  display_name: string
  category?: string
}

type Candle = { time?: number | string; brokerTime?: string; open: number; high: number; low: number; close: number }
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
type ManualOrderPreview = {
  broker_symbol: string
  direction: string
  bid: number
  ask: number
  spread: number
  observed_price: number
  stop_loss: number
  take_profit?: number | null
  calculated_volume: number
  volume?: number
  risk_amount: number
  effective_risk_percent: number
  required_margin: number
  free_margin_after: number
  equity: number
  balance: number
  account_currency: string
  quote_time?: string | null
  quote_age_seconds?: number | null
  stale_data_warning: boolean
  risk_warnings: string[]
}

const timeframes = ['M5', 'M15', 'M30', 'H1', 'H4', 'D1']
const NEWS_REFRESH_MS = 2 * 60_000
const AI_REFRESH_MS = 5 * 60_000
const updateTime = (date: Date | null) => date ? date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) : 'pending'
const parsedMaxLiveRiskPercent = Number(process.env.NEXT_PUBLIC_MAX_LIVE_RISK_PERCENT || '0.25')
const maxLiveRiskPercent = Number.isFinite(parsedMaxLiveRiskPercent) && parsedMaxLiveRiskPercent > 0 ? parsedMaxLiveRiskPercent : 0.25

const toChartTimestamp = (candle: Candle): UTCTimestamp | null => {
  const raw = candle.time ?? candle.brokerTime
  if (typeof raw === 'number' && Number.isFinite(raw)) return raw as UTCTimestamp
  if (typeof raw === 'string') {
    const parsed = Date.parse(raw.includes('T') ? raw : raw.replace(' ', 'T') + 'Z')
    if (Number.isFinite(parsed)) return Math.floor(parsed / 1000) as UTCTimestamp
  }
  return null
}

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
  const [chartMessage, setChartMessage] = useState('')
  const [accountsLoading, setAccountsLoading] = useState(true)
  const chartContainerRef = useRef<HTMLDivElement>(null)
  const chartRef = useRef<IChartApi | null>(null)
  const seriesRef = useRef<ISeriesApi<'Candlestick'> | null>(null)

  // Manual Trade Ticket State
  const [tradeDirection, setTradeDirection] = useState<'buy' | 'sell'>('buy')
  const [sizingMode, setSizingMode] = useState<'fixed' | 'risk'>('fixed')
  const [volumeInput, setVolumeInput] = useState('0.1')
  const [riskPercentInput, setRiskPercentInput] = useState(String(maxLiveRiskPercent))
  const [slInput, setSlInput] = useState('')
  const [tpInput, setTpInput] = useState('')
  const [previewData, setPreviewData] = useState<ManualOrderPreview | null>(null)
  const [previewError, setPreviewError] = useState('')
  const [previewLoading, setPreviewLoading] = useState(false)
  const [executionLoading, setExecutionLoading] = useState(false)
  const [executionSuccess, setExecutionSuccess] = useState('')
  const [showConfirmModal, setShowConfirmModal] = useState(false)

  const [quoteAge, setQuoteAge] = useState<number | null>(null)
  const [staleWarning, setStaleWarning] = useState(false)
  const [wsPrice, setWsPrice] = useState<{ bid: number; ask: number; spread: number } | null>(null)

  // Real-time WebSocket quote stream
  useEffect(() => {
    if (!selectedAccountId || !selectedSymbol) return
    const token = localStorage.getItem('access_token')
    if (!token) return

    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    const host = window.location.host
    const wsUrl = `${protocol}//${host}/api/market/accounts/${selectedAccountId}/quotes/ws?token=${token}&symbols=${selectedSymbol.broker_symbol}`
    
    let ws: WebSocket | null = null
    let reconnectTimeout: number | null = null

    function connect() {
      ws = new WebSocket(wsUrl)
      
      ws.onmessage = (event) => {
        try {
          const msg = JSON.parse(event.data)
          if (msg.type === 'quote') {
            const q = msg.data
            setWsPrice({
              bid: q.bid,
              ask: q.ask,
              spread: q.spread,
            })
            setQuoteAge(q.quote_age_seconds)
            setStaleWarning(q.stale_data_warning)
            setPrice({
              symbol: q.symbol,
              price: q.bid,
              change: 0,
              change_percent: 0,
            })
          }
        } catch (e) {
          console.error(e)
        }
      }

      ws.onclose = () => {
        reconnectTimeout = window.setTimeout(connect, 3000)
      }
    }

    connect()

    return () => {
      if (ws) {
        ws.onclose = null
        ws.close()
      }
      if (reconnectTimeout) {
        window.clearTimeout(reconnectTimeout)
      }
    }
  }, [selectedAccountId, selectedSymbol])

  // Auto-populate inputs from query params (e.g. redirected from AI screen)
  useEffect(() => {
    const params = new URLSearchParams(window.location.search)
    const symParam = params.get('symbol')
    const dirParam = params.get('direction')
    const slParam = params.get('sl')
    const tpParam = params.get('tp')

    if (symParam && symbols.length > 0) {
      const found = symbols.find(
        s => s.canonical_symbol.toUpperCase() === symParam.toUpperCase() ||
             s.broker_symbol.toUpperCase() === symParam.toUpperCase()
      )
      if (found) setSelectedSymbol(found)
    }
    if (dirParam === 'buy' || dirParam === 'sell') setTradeDirection(dirParam)
    if (slParam) setSlInput(slParam)
    if (tpParam) setTpInput(tpParam)
  }, [symbols])

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

  useEffect(() => {
    if (!selectedAccountId) return
    apiRequest<BrokerAccount>(`/broker-accounts/${selectedAccountId}/state`)
      .then((updated) => {
        setAccounts((current) => current.map((account) => account.id === updated.id ? updated : account))
      })
      .catch(() => undefined)
  }, [selectedAccountId])

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
        background: { color: dark ? '#2d3033' : '#ffffff' },
        textColor: dark ? '#a1abb1' : '#334155',
      },
      grid: {
        vertLines: { color: dark ? '#3d4246' : '#f1f5f9' },
        horzLines: { color: dark ? '#3d4246' : '#f1f5f9' },
      },
      timeScale: { timeVisible: true, secondsVisible: false, borderColor: dark ? '#4a4f53' : '#e2e8f0' },
      rightPriceScale: { borderColor: dark ? '#4a4f53' : '#e2e8f0' },
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
      const chartData = response.candles
        .map((c) => {
          const time = toChartTimestamp(c)
          return time ? { open: c.open, high: c.high, low: c.low, close: c.close, time } : null
        })
        .filter((c): c is { open: number; high: number; low: number; close: number; time: UTCTimestamp } => Boolean(c))
      seriesRef.current?.setData(chartData)
      chartRef.current?.timeScale().fitContent()
      setChartMessage(chartData.length ? '' : 'No candle data returned for this symbol/timeframe.')
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

  const handlePreview = async () => {
    if (!selectedAccountId || !selectedSymbol || !slInput) {
      setPreviewError('Select account, symbol, and enter a stop loss.')
      return
    }
    setPreviewLoading(true)
    setPreviewError('')
    setPreviewData(null)
    setShowConfirmModal(false)
    try {
      const body: any = {
        broker_account_id: selectedAccountId,
        symbol: selectedSymbol.broker_symbol,
        direction: tradeDirection,
        stop_loss: parseFloat(slInput),
      }
      if (tpInput) {
        body.take_profit = parseFloat(tpInput)
      }
      if (sizingMode === 'fixed') {
        body.volume = parseFloat(volumeInput)
      } else {
        body.risk_percent = parseFloat(riskPercentInput)
      }

      const res = await apiRequest<ManualOrderPreview>('/orders/preview', {
        method: 'POST',
        body: JSON.stringify(body)
      })
      setPreviewData(res)
    } catch (e) {
      setPreviewError(errorMessage(e))
    } finally {
      setPreviewLoading(false)
    }
  }

  const handleExecute = async () => {
    if (!selectedAccountId || !selectedSymbol || !slInput) return
    if ((previewData?.risk_warnings?.length || 0) > 0) {
      setError('Execution blocked by preview risk warnings.')
      setShowConfirmModal(false)
      return
    }
    setExecutionLoading(true)
    setExecutionSuccess('')
    setError('')
    try {
      const body: any = {
        broker_account_id: selectedAccountId,
        symbol: selectedSymbol.broker_symbol,
        direction: tradeDirection,
        stop_loss: parseFloat(slInput),
        idempotency_key: `man_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`,
      }
      if (tpInput) {
        body.take_profit = parseFloat(tpInput)
      }
      if (sizingMode === 'fixed') {
        body.volume = parseFloat(volumeInput)
      } else {
        body.risk_percent = parseFloat(riskPercentInput)
      }

      const res = await apiRequest<any>('/orders/execute', {
        method: 'POST',
        body: JSON.stringify(body)
      })
      setExecutionSuccess(`Order executed successfully! Position ID: ${res.broker_position_id || res.id}`)
      setPreviewData(null)
      setShowConfirmModal(false)
    } catch (e) {
      setError(errorMessage(e))
      setShowConfirmModal(false)
    } finally {
      setExecutionLoading(false)
    }
  }

  const selectedAccount = accounts.find(a => a.id === selectedAccountId)
  const accountCurrency = previewData?.account_currency || selectedAccount?.currency || 'USD'
  const displayedBalance = previewData?.balance ?? selectedAccount?.balance
  const displayedEquity = previewData?.equity
  const displayedFreeMargin = previewData?.free_margin_after
  const previewRiskWarnings = previewData?.risk_warnings ?? []
  const previewHasBlockingRisk = previewRiskWarnings.length > 0

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
          <div className="flex flex-wrap items-center gap-2">
            <span className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-semibold ${
              selectedAccount.account_type === 'live' ? 'bg-[#f0fdf4] text-[#166534] border border-[#bbf7d0]' : 'bg-[#eff6ff] text-[#1e40af] border border-[#bfdbfe]'
            }`}>
              {selectedAccount.account_type === 'live' ? 'LIVE MT5' : 'DEMO MT5'}
            </span>
            <span className="text-xs font-semibold text-slate-600">
              Balance:{' '}
              <span className="tabular-nums text-slate-950">
                {accountCurrency} {formatNumber(displayedBalance ?? 0, 2)}
              </span>
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
          <div className="relative">
            <div ref={chartContainerRef} className="w-full" />
            {chartMessage && (
              <div className="absolute inset-0 flex items-center justify-center px-6 text-center text-sm font-medium text-slate-500">
                {chartMessage}
              </div>
            )}
          </div>
          <p className="border-t border-slate-100 px-5 py-2.5 text-xs text-slate-400">
            MT5 live feed · updates every 30s · quotes every 10s
          </p>
        </div>

        <div className="space-y-6">
          {/* ── Manual Trade Ticket ── */}
          <div className={`card border-2 ${
            selectedAccount?.account_type === 'live'
              ? 'border-amber-400/70 bg-gradient-to-b from-amber-50/40 to-white'
              : 'border-blue-300/60 bg-gradient-to-b from-blue-50/30 to-white'
          }`}>
            <div className="flex items-center justify-between gap-2">
              <h2 className="flex items-center gap-2 text-sm font-semibold text-slate-900">
                <ArrowUpDown size={15} className="text-[#2563eb]" aria-hidden="true" />
                Trade Ticket
              </h2>
              <span className={`rounded-full px-2.5 py-0.5 text-[10px] font-bold uppercase tracking-wide ${
                selectedAccount?.account_type === 'live'
                  ? 'bg-red-100 text-red-700 border border-red-200'
                  : 'bg-blue-100 text-blue-700 border border-blue-200'
              }`}>
                {selectedAccount?.account_type === 'live' ? '🔴 LIVE ORDER' : 'DEMO'}
              </span>
            </div>

            {selectedAccount?.account_type === 'live' && (
              <div className="mt-2 flex items-start gap-2 rounded-md border border-amber-200 bg-amber-50 px-3 py-2">
                <ShieldAlert size={14} className="mt-0.5 shrink-0 text-amber-600" />
                <p className="text-[11px] leading-4 font-semibold text-amber-800">LIVE BROKER — Real financial risk. Verify all levels before executing.</p>
              </div>
            )}

            <div className="mt-3 grid grid-cols-3 gap-2 rounded-md border border-slate-200 bg-slate-50 px-3 py-2 text-[11px]">
              <div>
                <p className="font-semibold uppercase text-slate-500">Balance</p>
                <p className="mt-0.5 font-bold tabular-nums text-slate-950">{accountCurrency} {formatNumber(displayedBalance ?? 0, 2)}</p>
              </div>
              <div>
                <p className="font-semibold uppercase text-slate-500">Equity</p>
                <p className="mt-0.5 font-bold tabular-nums text-slate-950">{displayedEquity != null ? `${accountCurrency} ${formatNumber(displayedEquity, 2)}` : 'Preview'}</p>
              </div>
              <div>
                <p className="font-semibold uppercase text-slate-500">Free after</p>
                <p className="mt-0.5 font-bold tabular-nums text-slate-950">{displayedFreeMargin != null ? `${accountCurrency} ${formatNumber(displayedFreeMargin, 2)}` : 'Preview'}</p>
              </div>
            </div>

            {/* Live Bid / Ask / Spread */}
            <div className="mt-3 grid grid-cols-3 gap-2 text-center">
              <div className="rounded-md bg-[#f0fdf4] px-2 py-2">
                <p className="text-[10px] font-semibold uppercase text-slate-500">Bid</p>
                <p className="mt-0.5 text-sm font-bold tabular-nums text-[#15803d]">
                  {wsPrice ? formatNumber(wsPrice.bid, 5) : price ? formatNumber(price.price, 5) : '—'}
                </p>
              </div>
              <div className="rounded-md bg-[#fef2f2] px-2 py-2">
                <p className="text-[10px] font-semibold uppercase text-slate-500">Ask</p>
                <p className="mt-0.5 text-sm font-bold tabular-nums text-[#b91c1c]">
                  {wsPrice ? formatNumber(wsPrice.ask, 5) : '—'}
                </p>
              </div>
              <div className="rounded-md bg-slate-50 px-2 py-2">
                <p className="text-[10px] font-semibold uppercase text-slate-500">Spread</p>
                <p className="mt-0.5 text-sm font-bold tabular-nums text-slate-700">
                  {wsPrice ? wsPrice.spread.toFixed(1) : '—'}
                </p>
              </div>
            </div>
            {quoteAge !== null && (
              <p className={`mt-1.5 text-[11px] font-medium ${
                staleWarning ? 'text-red-600' : 'text-slate-400'
              }`}>
                {staleWarning ? `⚠ Stale quote (${quoteAge.toFixed(0)}s old) — execution may be rejected` : `Quote age: ${quoteAge.toFixed(0)}s`}
              </p>
            )}

            {/* Direction Toggle */}
            <div className="mt-3 grid grid-cols-2 gap-2">
              <button
                type="button"
                onClick={() => setTradeDirection('buy')}
                className={`rounded-lg py-2 text-xs font-bold uppercase tracking-wide transition-all ${
                  tradeDirection === 'buy'
                    ? 'bg-[#15803d] text-white shadow-md shadow-green-200'
                    : 'bg-slate-100 text-slate-500 hover:bg-green-50 hover:text-[#15803d]'
                }`}
              >
                Buy
              </button>
              <button
                type="button"
                onClick={() => setTradeDirection('sell')}
                className={`rounded-lg py-2 text-xs font-bold uppercase tracking-wide transition-all ${
                  tradeDirection === 'sell'
                    ? 'bg-[#b91c1c] text-white shadow-md shadow-red-200'
                    : 'bg-slate-100 text-slate-500 hover:bg-red-50 hover:text-[#b91c1c]'
                }`}
              >
                Sell
              </button>
            </div>

            {/* Sizing Mode */}
            <div className="mt-3">
              <div className="flex rounded-md border border-slate-200 p-0.5 text-center">
                <button
                  type="button"
                  onClick={() => setSizingMode('fixed')}
                  className={`flex-1 rounded px-2 py-1 text-[11px] font-semibold transition-colors ${
                    sizingMode === 'fixed' ? 'bg-blue-50 text-[#1d4ed8]' : 'text-slate-500 hover:text-slate-800'
                  }`}
                >
                  Fixed Volume
                </button>
                <button
                  type="button"
                  onClick={() => setSizingMode('risk')}
                  className={`flex-1 rounded px-2 py-1 text-[11px] font-semibold transition-colors ${
                    sizingMode === 'risk' ? 'bg-blue-50 text-[#1d4ed8]' : 'text-slate-500 hover:text-slate-800'
                  }`}
                >
                  Risk % Sizing
                </button>
              </div>
              <div className="mt-2">
                {sizingMode === 'fixed' ? (
                  <label className="block">
                    <span className="text-[11px] font-semibold text-slate-600">Volume (lots)</span>
                    <input
                      type="number"
                      step="0.01"
                      min="0.01"
                      className="input-base mt-1 w-full text-sm"
                      value={volumeInput}
                      onChange={(e) => setVolumeInput(e.target.value)}
                    />
                  </label>
                ) : (
                  <label className="block">
                    <span className="text-[11px] font-semibold text-slate-600">Risk %</span>
                    <input
                      type="number"
                      step="0.1"
                      min="0.1"
                      max={maxLiveRiskPercent}
                      className="input-base mt-1 w-full text-sm"
                      value={riskPercentInput}
                      onChange={(e) => setRiskPercentInput(e.target.value)}
                    />
                  </label>
                )}
              </div>
            </div>

            {/* SL / TP */}
            <div className="mt-3 grid grid-cols-2 gap-2">
              <label className="block">
                <span className="text-[11px] font-semibold text-red-600">Stop Loss *</span>
                <input
                  type="number"
                  step="0.00001"
                  className="input-base mt-1 w-full text-sm border-red-200 focus:border-red-400"
                  placeholder="Required"
                  value={slInput}
                  onChange={(e) => setSlInput(e.target.value)}
                />
              </label>
              <label className="block">
                <span className="text-[11px] font-semibold text-[#15803d]">Take Profit</span>
                <input
                  type="number"
                  step="0.00001"
                  className="input-base mt-1 w-full text-sm"
                  placeholder="Optional"
                  value={tpInput}
                  onChange={(e) => setTpInput(e.target.value)}
                />
              </label>
            </div>

            {/* Preview Button */}
            <button
              type="button"
              disabled={previewLoading || !slInput}
              onClick={() => void handlePreview()}
              className="btn-secondary mt-3 w-full gap-2 text-xs"
            >
              <Eye size={14} />
              {previewLoading ? 'Calculating…' : 'Preview Trade'}
            </button>

            {previewError && (
              <p className="mt-2 rounded-md border border-red-200 bg-red-50 px-3 py-2 text-[11px] text-red-700">{previewError}</p>
            )}

            {/* Preview Results */}
            {previewData && (
              <div className="mt-3 rounded-lg border border-blue-200 bg-blue-50/50 p-3">
                <p className="text-[11px] font-bold uppercase text-blue-700 mb-2">Order Preview</p>
                <dl className="grid grid-cols-2 gap-x-4 gap-y-1.5 text-[11px]">
                  <dt className="text-slate-500">Direction</dt>
                  <dd className="font-semibold text-slate-900 text-right">{previewData.direction?.toUpperCase()}</dd>
                  <dt className="text-slate-500">Volume</dt>
                  <dd className="font-semibold text-slate-900 tabular-nums text-right">{previewData.calculated_volume ?? previewData.volume}</dd>
                  <dt className="text-slate-500">Stop Loss</dt>
                  <dd className="font-semibold text-red-700 tabular-nums text-right">{previewData.stop_loss}</dd>
                  {previewData.take_profit && <><dt className="text-slate-500">Take Profit</dt><dd className="font-semibold text-[#15803d] tabular-nums text-right">{previewData.take_profit}</dd></>}
                  {previewData.risk_amount != null && <><dt className="text-slate-500">Risk Amount</dt><dd className="font-semibold text-slate-900 tabular-nums text-right">${previewData.risk_amount?.toFixed(2)}</dd></>}
                  {previewData.required_margin != null && <><dt className="text-slate-500">Margin Required</dt><dd className="font-semibold text-slate-900 tabular-nums text-right">${previewData.required_margin?.toFixed(2)}</dd></>}
                  {previewData.free_margin_after != null && <><dt className="text-slate-500">Free Margin After</dt><dd className="font-semibold text-slate-900 tabular-nums text-right">${previewData.free_margin_after?.toFixed(2)}</dd></>}
                </dl>
                {previewRiskWarnings.length > 0 && (
                  <div className="mt-2 rounded border border-amber-200 bg-amber-50 px-2 py-1.5">
                    {previewRiskWarnings.map((w: string, i: number) => (
                      <p key={i} className="text-[11px] text-amber-700">⚠ {w}</p>
                    ))}
                  </div>
                )}

                {/* Execute Button */}
                {!showConfirmModal ? (
                  <button
                    type="button"
                    disabled={previewHasBlockingRisk}
                    onClick={() => {
                      if (!previewHasBlockingRisk) setShowConfirmModal(true)
                    }}
                    className={`mt-3 w-full rounded-lg py-2.5 text-xs font-bold uppercase tracking-wide text-white transition-all ${
                      previewHasBlockingRisk
                        ? 'bg-slate-300 text-slate-500 shadow-none'
                        : tradeDirection === 'buy'
                        ? 'bg-[#15803d] hover:bg-[#166534] shadow-md shadow-green-200'
                        : 'bg-[#b91c1c] hover:bg-[#991b1b] shadow-md shadow-red-200'
                    }`}
                  >
                    {tradeDirection === 'buy' ? '🟢 Execute BUY Order' : '🔴 Execute SELL Order'}
                  </button>
                ) : (
                  <div className="mt-3 rounded-lg border-2 border-amber-300 bg-amber-50 p-3">
                    <p className="text-xs font-bold text-amber-800">
                      ⚠ Confirm {selectedAccount?.account_type === 'live' ? 'LIVE' : 'DEMO'} {tradeDirection.toUpperCase()} order?
                    </p>
                    <p className="mt-1 text-[11px] text-amber-700">
                      {previewData.calculated_volume ?? previewData.volume} lots {selectedSymbol?.broker_symbol} · SL {previewData.stop_loss}
                    </p>
                    <div className="mt-2 grid grid-cols-2 gap-2">
                      <button
                        type="button"
                        onClick={() => setShowConfirmModal(false)}
                        className="btn-secondary py-1.5 text-xs"
                      >
                        Cancel
                      </button>
                      <button
                        type="button"
                        disabled={executionLoading || previewHasBlockingRisk}
                        onClick={() => void handleExecute()}
                        className={`rounded-lg py-1.5 text-xs font-bold text-white ${
                          previewHasBlockingRisk ? 'bg-slate-300 text-slate-500' : tradeDirection === 'buy' ? 'bg-[#15803d]' : 'bg-[#b91c1c]'
                        }`}
                      >
                        {executionLoading ? 'Sending…' : 'Confirm'}
                      </button>
                    </div>
                  </div>
                )}
              </div>
            )}

            {/* Execution Success */}
            {executionSuccess && (
              <div className="mt-3 rounded-md border border-green-200 bg-green-50 px-3 py-2">
                <p className="text-[11px] font-semibold text-green-800">✓ {executionSuccess}</p>
              </div>
            )}
          </div>
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
