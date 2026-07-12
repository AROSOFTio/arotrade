'use client'

import { useEffect, useState } from 'react'
import { FlaskConical, LineChart, ShieldCheck, ShieldAlert, Landmark } from 'lucide-react'

import { apiRequest, errorMessage, formatNumber } from '../../components/api'
import { EmptyState } from '../../components/empty-state'
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
}

type Strategy = { id: number; name: string; is_active: boolean }

type BacktestResult = {
  id: number
  symbol: string
  timeframe: string
  total_trades: number
  winning_trades: number
  losing_trades: number
  win_rate: number
  profit_factor: number
  max_drawdown: number
  total_profit: number
  risk_reward_ratio: number
  is_safe: boolean
}

const timeframes = ['M15', 'M30', 'H1', 'H4', 'D1']

function daysAgoIso(days: number) {
  const date = new Date()
  date.setDate(date.getDate() - days)
  return date.toISOString()
}

export default function BacktestingPage() {
  const [accounts, setAccounts] = useState<BrokerAccount[]>([])
  const [selectedAccountId, setSelectedAccountId] = useState<number | null>(null)
  const [accountsLoading, setAccountsLoading] = useState(true)

  const [symbols, setSymbols] = useState<SymbolItem[]>([])
  const [strategies, setStrategies] = useState<Strategy[]>([])
  const [strategyId, setStrategyId] = useState('')
  const [selectedSymbol, setSelectedSymbol] = useState('')
  const [timeframe, setTimeframe] = useState('H1')
  const [days, setDays] = useState('90')
  const [balance, setBalance] = useState('10000')
  const [running, setRunning] = useState(false)
  const [result, setResult] = useState<BacktestResult | null>(null)
  const [error, setError] = useState('')

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

  // 2. Fetch strategies
  useEffect(() => {
    apiRequest<Strategy[]>('/strategies').then((items) => {
      setStrategies(items)
      if (items[0]) setStrategyId(String(items[0].id))
    }).catch((requestError) => setError(errorMessage(requestError)))
  }, [])

  // 3. Fetch symbols dynamically from account
  useEffect(() => {
    if (!selectedAccountId) return
    apiRequest<{ symbols: SymbolItem[] }>(`/market/accounts/${selectedAccountId}/symbols`)
      .then((r) => {
        setSymbols(r.symbols)
        if (r.symbols.length > 0) {
          setSelectedSymbol(r.symbols[0].broker_symbol)
        } else {
          setSelectedSymbol('')
        }
      })
      .catch((err) => setError(errorMessage(err)))
  }, [selectedAccountId])

  const runBacktest = async (event: React.FormEvent) => {
    event.preventDefault()
    setError('')
    setResult(null)
    if (!selectedAccountId) {
      setError('Please select an active broker account')
      return
    }
    if (!selectedSymbol) {
      setError('Please select a symbol')
      return
    }
    setRunning(true)
    try {
      const response = await apiRequest<BacktestResult>('/backtest', {
        method: 'POST',
        body: JSON.stringify({
          broker_account_id: selectedAccountId,
          strategy_id: Number(strategyId),
          symbol: selectedSymbol,
          timeframe,
          start_date: daysAgoIso(Number(days)),
          end_date: new Date().toISOString(),
          initial_balance: Number(balance),
        }),
      })
      setResult(response)
    } catch (requestError) {
      setError(errorMessage(requestError))
    } finally {
      setRunning(false)
    }
  }

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
        <PageHeader eyebrow="Research" title="Backtesting" description="Replay a strategy template over real candles." />
        <div className="rounded-lg border border-blue-200 bg-blue-50/50 p-6 text-center">
          <Landmark size={32} className="mx-auto text-blue-500" />
          <h2 className="mt-3 text-sm font-semibold text-slate-900">No active broker accounts connected</h2>
          <p className="mt-1 text-xs text-slate-500">You must connect and deploy an active MT5 broker account to run historical backtests.</p>
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
        eyebrow="Research"
        title="Backtesting"
        description="Replay a strategy template over real historical candles. Losing results are shown honestly — that is the point of backtesting."
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

      <section className="grid gap-6 lg:grid-cols-[380px_minmax(0,1fr)]">
        <form onSubmit={runBacktest} className="card h-fit space-y-4">
          <div className="flex items-center gap-3">
            <span className="flex h-10 w-10 items-center justify-center rounded-lg bg-blue-50 text-[#2563eb]">
              <FlaskConical size={20} aria-hidden="true" />
            </span>
            <h2 className="text-sm font-semibold text-slate-900">Run a backtest</h2>
          </div>

          <div>
            <label htmlFor="bt-strategy" className="label">Strategy</label>
            {strategies.length ? (
              <select id="bt-strategy" className="input-base" value={strategyId} onChange={(e) => setStrategyId(e.target.value)}>
                {strategies.map((strategy) => <option key={strategy.id} value={strategy.id}>{strategy.name}</option>)}
              </select>
            ) : (
              <p className="rounded-md bg-slate-50 px-3 py-3 text-xs leading-5 text-slate-600">
                No strategies yet — create one in the Strategies page first.
              </p>
            )}
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label htmlFor="bt-symbol" className="label">Symbol</label>
              <select id="bt-symbol" className="input-base text-sm" value={selectedSymbol} onChange={(e) => setSelectedSymbol(e.target.value)}>
                {symbols.map((item) => (
                  <option key={item.broker_symbol} value={item.broker_symbol}>
                    {item.canonical_symbol} ({item.broker_symbol})
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label htmlFor="bt-timeframe" className="label">Timeframe</label>
              <select id="bt-timeframe" className="input-base" value={timeframe} onChange={(e) => setTimeframe(e.target.value)}>
                {timeframes.map((item) => <option key={item} value={item}>{item}</option>)}
              </select>
            </div>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label htmlFor="bt-days" className="label">Lookback (days)</label>
              <select id="bt-days" className="input-base" value={days} onChange={(e) => setDays(e.target.value)}>
                <option value="30">30 days</option>
                <option value="90">90 days</option>
                <option value="180">180 days</option>
                <option value="365">1 year</option>
              </select>
            </div>
            <div>
              <label htmlFor="bt-balance" className="label">Starting balance</label>
              <input id="bt-balance" type="number" min="100" step="any" className="input-base" value={balance} onChange={(e) => setBalance(e.target.value)} />
            </div>
          </div>

          <button type="submit" disabled={running || !strategyId || !selectedSymbol} className="btn-primary w-full">
            {running ? 'Running backtest…' : <>Run backtest <LineChart size={16} aria-hidden="true" /></>}
          </button>
          <p className="text-xs leading-5 text-slate-500">
            Data window is limited to the most recent 5,000 candles per timeframe from the selected MT5 broker account.
          </p>
        </form>

        {result ? (
          <div className="card h-fit">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <h2 className="text-base font-bold text-slate-950">{result.symbol} · {result.timeframe}</h2>
              <span className={`inline-flex items-center gap-1.5 rounded-full px-3 py-1 text-xs font-bold ${
                result.is_safe ? 'bg-[#f0fdf4] text-[#15803d]' : 'bg-amber-50 text-amber-700'
              }`}>
                {result.is_safe ? <ShieldCheck size={13} aria-hidden="true" /> : <ShieldAlert size={13} aria-hidden="true" />}
                {result.is_safe ? 'Passed validation' : 'Not validated'}
              </span>
            </div>
            <div className="mt-5 grid gap-3 sm:grid-cols-2">
              <div className={`rounded-lg px-4 py-5 ${result.total_profit >= 0 ? 'bg-[#f0fdf4]' : 'bg-[#fef2f2]'}`}>
                <p className="text-[11px] font-semibold uppercase tracking-wide text-slate-500">Net profit</p>
                <p className={`mt-1 text-3xl font-bold tabular-nums ${result.total_profit >= 0 ? 'text-[#15803d]' : 'text-[#b91c1c]'}`}>
                  {result.total_profit >= 0 ? '+' : ''}{formatNumber(result.total_profit, 2)}
                </p>
              </div>
              <div className="rounded-lg bg-slate-50 px-4 py-5">
                <p className="text-[11px] font-semibold uppercase tracking-wide text-slate-500">Profit factor</p>
                <p className="mt-1 text-3xl font-bold tabular-nums text-slate-950">{result.profit_factor.toFixed(2)}</p>
              </div>
            </div>
            <dl className="mt-4 divide-y divide-slate-100 text-sm">
              <div className="flex justify-between gap-4 py-3">
                <dt className="text-slate-500">Total trades</dt>
                <dd className="font-semibold tabular-nums text-slate-900">
                  {result.total_trades} ({result.winning_trades}W / {result.losing_trades}L)
                </dd>
              </div>
              <div className="flex justify-between gap-4 py-3">
                <dt className="text-slate-500">Win rate</dt>
                <dd className="font-semibold tabular-nums text-slate-900">{result.win_rate.toFixed(1)}%</dd>
              </div>
              <div className="flex justify-between gap-4 py-3">
                <dt className="text-slate-500">Max drawdown</dt>
                <dd className="font-semibold tabular-nums text-[#b91c1c]">{result.max_drawdown.toFixed(1)}%</dd>
              </div>
              <div className="flex justify-between gap-4 py-3">
                <dt className="text-slate-500">Reward : risk per trade</dt>
                <dd className="font-semibold tabular-nums text-slate-900">{result.risk_reward_ratio.toFixed(2)}</dd>
              </div>
            </dl>
            {!result.is_safe && (
              <p className="mt-4 rounded-md border border-amber-200 bg-amber-50 px-3 py-3 text-xs leading-5 text-amber-800">
                Validation requires at least 100 trades and a profit factor of 1.2+.
              </p>
            )}
          </div>
        ) : (
          <div className="card">
            <EmptyState
              icon={LineChart}
              title="No backtest yet"
              description="Pick a strategy, market and lookback period, then run the test against real candles."
            />
          </div>
        )}
      </section>
    </>
  )
}
